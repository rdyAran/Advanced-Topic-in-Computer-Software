"""Groq provider (OpenAI-compatible API, very fast inference).

Uses strict JSON-schema structured output (constrained decoding) on models that support it
(openai/gpt-oss-120b, openai/gpt-oss-20b, qwen/qwen3.8-27b — see console.groq.com/docs/structured-outputs),
and falls back to JSON-object mode + schema in the prompt for other models.
Standard library only (urllib) — no extra dependency.

Free-tier note: ~8K tokens/minute -> roughly 4-5 extractions per minute. Fine for hybrid mode
(only uncertain messages reach the LLM); use --sleep 15 when evaluating.
"""
import json, os, time, logging, urllib.request, urllib.error
from floodcommon.schemas import Extraction
from .providers import SYSTEM_PROMPT

log = logging.getLogger(__name__)
API = "https://api.groq.com/openai/v1/chat/completions"
STRICT_MODELS = ("openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b")


def to_strict_schema(model) -> dict:
    """Pydantic schema -> OpenAI/Groq strict schema: $refs inlined, every key required, nullable via anyOf, no defaults."""
    root = model.model_json_schema()
    from floodcommon.schemas import LLM_HIDDEN
    root["properties"] = {k: v for k, v in root["properties"].items() if k not in LLM_HIDDEN}
    defs = root.get("$defs", {})

    def conv(node: dict) -> dict:
        if "$ref" in node:
            return conv(defs[node["$ref"].split("/")[-1]])
        if "anyOf" in node:
            out = {"anyOf": [conv(o) if o.get("type") != "null" else {"type": "null"} for o in node["anyOf"]]}
        else:
            out = {"type": node["type"]}
            if "enum" in node: out["enum"] = node["enum"]
            if node["type"] == "array": out["items"] = conv(node["items"])
            if node["type"] == "object":
                out["properties"] = {k: conv(v) for k, v in node["properties"].items()}
                out["required"] = list(node["properties"])
                out["additionalProperties"] = False
        if "description" in node: out["description"] = node["description"]
        return out
    return conv(root)


class GroqProvider:
    name = "groq"
    RETRYABLE = ("429", "500", "502", "503", "504", "timed out", "Timeout", "EMPTY_RESPONSE", "rate_limit")

    def __init__(self, api_key: str | None = None, model: str | None = None, interactive: bool = True, timeout: float = 60):
        self.key = api_key or os.environ["GROQ_API_KEY"]
        self.model = model or os.getenv("GROQ_MODEL") or "openai/gpt-oss-120b"
        self.interactive, self.timeout = interactive, timeout
        self.backups, self.last_model, self.last_latency = [], None, None
        self.strict = self.model in STRICT_MODELS
        self.send_reasoning = self.model.startswith("openai/gpt-oss")
        self.schema = to_strict_schema(Extraction)

    # --- HTTP (kept in one method so tests can replace it) ---
    def _post(self, payload: dict) -> dict:
        req = urllib.request.Request(API, data=json.dumps(payload).encode(), method="POST", headers={
            "Authorization": f"Bearer {self.key}", "Content-Type": "application/json", "User-Agent": "floodlink/0.4"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:400]
            raise RuntimeError(f"{e.code} {body}") from None

    def _payload(self, text: str, mode: str = "strict") -> dict:
        """mode: "strict" (constrained JSON schema) | "strict_think" (same, more reasoning) | "object" (JSON mode + schema in prompt)"""
        p = {"model": self.model, "temperature": 0, "messages": [
            {"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}]}
        if mode.startswith("strict") and self.strict:
            p["response_format"] = {"type": "json_schema", "json_schema": {"name": "extraction", "strict": True, "schema": self.schema}}
        else:   # JSON-object mode only guarantees valid JSON -> put the schema in the prompt, validate ourselves
            p["response_format"] = {"type": "json_object"}
            p["messages"][0]["content"] += ("\nตอบเป็น JSON object ตาม schema นี้เท่านั้น ใส่ครบทุก key (ไม่รู้ให้เป็น null หรือ []):\n"
                                            + json.dumps(self.schema, ensure_ascii=False))
        if self.send_reasoning:
            p["reasoning_effort"] = "medium" if mode == "strict_think" else "low"
        return p

    def _call(self, text: str, mode: str = "strict") -> Extraction:
        t0 = time.time()
        try:
            data = self._post(self._payload(text, mode))
        except RuntimeError as e:
            msg = str(e)
            if msg.startswith("400") and self.send_reasoning and "reasoning_effort" in msg:
                self.send_reasoning = False; return self._call(text, mode)
            if msg.startswith("400") and self.strict and "not supported" in msg and ("json_schema" in msg or "response_format" in msg):
                log.warning("Groq model %s rejected strict schema; using JSON-object mode", self.model)
                self.strict = False; return self._call(text, "object")
            raise
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
        if not content:
            raise RuntimeError(f"EMPTY_RESPONSE from {self.model}")
        try:
            e = Extraction.model_validate_json(content)
        except Exception as err:   # JSON-object mode can return a near-miss -> treat like a parse failure
            raise RuntimeError(f"PARSE_FAILED local validation: {str(err)[:150]}") from None
        self.last_latency = round(time.time() - t0, 1)
        self.last_model = self.model
        return e

    @staticmethod
    def _is_parse_failure(msg: str) -> bool:
        return any(k in msg for k in ("Parsing failed", "failed_generation", "json_validate_failed", "PARSE_FAILED", "EMPTY_RESPONSE"))

    def extract(self, text: str) -> Extraction:
        """Parse failures -> next output mode right away; rate limits / 5xx -> wait and retry same mode."""
        modes = ["strict", "strict_think", "object", "object"] if self.strict else ["object", "object", "object"]
        waits = [2, 5] if self.interactive else [10, 20, 40, 60]          # free tier = tokens/minute -> wait it out
        last, mi, wi, tries = None, 0, 0, 0
        while mi < len(modes) and tries < 10:
            tries += 1
            try:
                return self._call(text, modes[mi])
            except Exception as e:
                last, msg = e, str(e)
                log.warning("Groq error [model=%s mode=%s] (try %d): %s", self.model, modes[mi], tries, msg[:200])
                if self._is_parse_failure(msg):
                    mi += 1                     # model produced bad JSON -> change output mode
                elif any(k in msg for k in self.RETRYABLE) and wi < len(waits):
                    time.sleep(waits[wi]); wi += 1
                else:
                    break
        raise RuntimeError(f"Groq failed [model={self.model}]: {str(last)[:300]}")

    def split_cases(self, text: str) -> list[str]:
        from .splitter import SPLIT_PROMPT
        schema = {"type": "object", "properties": {"cases": {"type": "array", "items": {"type": "string"}}},
                  "required": ["cases"], "additionalProperties": False}
        p = {"model": self.model, "temperature": 0, "messages": [{"role": "system", "content": SPLIT_PROMPT}, {"role": "user", "content": text}],
             "response_format": {"type": "json_schema", "json_schema": {"name": "cases", "strict": True, "schema": schema}} if self.strict
             else {"type": "json_object"}}
        if self.send_reasoning:
            p["reasoning_effort"] = "low"
        data = self._post(p)
        return json.loads((data.get("choices") or [{}])[0].get("message", {}).get("content") or "{}").get("cases", [])

    def complete_json(self, system: str, user: str) -> dict:
        p = {"model": self.model, "temperature": 0, "response_format": {"type": "json_object"},
             "messages": [{"role": "system", "content": system + "\nตอบเป็น JSON เท่านั้น"}, {"role": "user", "content": user}]}
        if self.send_reasoning:
            p["reasoning_effort"] = "low"
        data = self._post(p)
        return json.loads((data.get("choices") or [{}])[0].get("message", {}).get("content") or "{}")

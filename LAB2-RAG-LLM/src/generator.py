"""
generator.py
------------
Call an LLM to generate the answer. Supports 3 providers via plain HTTP
(Python standard library only — no extra SDK to install):

  - gemini : Google AI Studio  (free API key: https://aistudio.google.com/apikey)
  - openai : OpenAI API
  - ollama : local model       (https://ollama.com -> `ollama pull qwen2.5:7b`)
"""

import json
import time
import urllib.error
import urllib.request


class LLMError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


RETRY_STATUS = {429, 500, 502, 503, 504}   # busy / rate-limited -> worth retrying


def _post_json(url, payload, headers, timeout):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:400]
        raise LLMError(f"HTTP {e.code}: {body}", status=e.code) from e
    except urllib.error.URLError as e:
        raise LLMError(f"Cannot connect to {url}: {e.reason}") from e


class Generator:
    def __init__(self, provider, model, temperature=0.2, max_tokens=800, timeout=60,
                 gemini_api_key="", openai_api_key="", ollama_url="http://localhost:11434",
                 fallback_models=None, max_retries=3):
        self.provider = provider.lower()
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.gemini_api_key = gemini_api_key
        self.openai_api_key = openai_api_key
        self.ollama_url = ollama_url.rstrip("/")
        self.fallback_models = [m for m in (fallback_models or []) if m and m != model]
        self.max_retries = max_retries

        if self.provider == "gemini" and not gemini_api_key:
            raise LLMError("GEMINI_API_KEY is not set (put it in the .env file)")
        if self.provider == "openai" and not openai_api_key:
            raise LLMError("OPENAI_API_KEY is not set (put it in the .env file)")
        if self.provider not in ("gemini", "openai", "ollama"):
            raise LLMError(f"Unknown LLM_PROVIDER: {provider}")

    @classmethod
    def from_config(cls, cfg):
        return cls(
            provider=cfg.LLM_PROVIDER,
            model=cfg.LLM_MODELS[cfg.LLM_PROVIDER],
            temperature=cfg.LLM_TEMPERATURE,
            max_tokens=cfg.LLM_MAX_TOKENS,
            timeout=cfg.LLM_TIMEOUT,
            gemini_api_key=cfg.GEMINI_API_KEY,
            openai_api_key=cfg.OPENAI_API_KEY,
            ollama_url=cfg.OLLAMA_URL,
            fallback_models=cfg.LLM_FALLBACK_MODELS.get(cfg.LLM_PROVIDER, []),
            max_retries=cfg.LLM_MAX_RETRIES,
        )

    def generate(self, prompt, system=None, temperature=None):
        """
        Try the main model; on 429/503 (busy) wait and retry (2s, 4s, 8s ...).
        If it is still busy, try each model in LLM_FALLBACK_MODELS.
        """
        t = self.temperature if temperature is None else temperature
        call = {"gemini": self._gemini, "openai": self._openai, "ollama": self._ollama}[self.provider]
        main_model = self.model
        last_error = None
        try:
            for model in [main_model] + self.fallback_models:
                self.model = model
                for attempt in range(1, self.max_retries + 1):
                    try:
                        return call(prompt, system, t)
                    except LLMError as e:
                        last_error = e
                        if e.status not in RETRY_STATUS:
                            raise
                        if attempt < self.max_retries:
                            wait = 2 ** attempt
                            print(f"[generator] {model} busy (HTTP {e.status}), "
                                  f"retry {attempt}/{self.max_retries - 1} in {wait}s ...")
                            time.sleep(wait)
                if model != (self.fallback_models or [main_model])[-1]:
                    print(f"[generator] {model} still busy -> trying fallback model")
            raise last_error
        finally:
            self.model = main_model

    # ---------------- providers ----------------
    def _gemini(self, prompt, system, t):
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{self.model}:generateContent")
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": t, "maxOutputTokens": self.max_tokens},
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        data = _post_json(url, payload, {"x-goog-api-key": self.gemini_api_key}, self.timeout)
        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts).strip()
        except (KeyError, IndexError):
            raise LLMError(f"Unexpected Gemini response: {str(data)[:300]}")

    def _openai(self, prompt, system, t):
        messages = ([{"role": "system", "content": system}] if system else []) + \
                   [{"role": "user", "content": prompt}]
        payload = {"model": self.model, "messages": messages,
                   "temperature": t, "max_tokens": self.max_tokens}
        data = _post_json("https://api.openai.com/v1/chat/completions", payload,
                          {"Authorization": f"Bearer {self.openai_api_key}"}, self.timeout)
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError):
            raise LLMError(f"Unexpected OpenAI response: {str(data)[:300]}")

    def _ollama(self, prompt, system, t):
        messages = ([{"role": "system", "content": system}] if system else []) + \
                   [{"role": "user", "content": prompt}]
        payload = {"model": self.model, "messages": messages, "stream": False,
                   "options": {"temperature": t, "num_predict": self.max_tokens}}
        data = _post_json(f"{self.ollama_url}/api/chat", payload, {}, self.timeout)
        try:
            return data["message"]["content"].strip()
        except KeyError:
            raise LLMError(f"Unexpected Ollama response: {str(data)[:300]}")

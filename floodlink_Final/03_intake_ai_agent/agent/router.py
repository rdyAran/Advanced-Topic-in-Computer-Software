"""Intake Agent — decides WHO reads each message.

strategy="hybrid" (default):
    1. our own model reads it first      (~5 ms, offline, never rate-limited)
    2. if it is unsure / may be red / wording looks unfamiliar -> escalate to the LLM chain (teacher LLMs)
    3. the LLM chain tries providers in order (LLM_PROVIDERS, default "gemini,groq"); a provider that just failed
       is skipped for a cool-down period (circuit breaker), so one outage doesn't slow every message
    4. the LLM's answer is logged as a new training example -> retrain -> our model improves (distillation loop)
    5. if every LLM is down, keep our model's answer  (a request for help is never lost)
Other strategies: "own" | "llm" (chain only) | "gemini" | "groq" | "rules"
"""
import json, os, re, logging, threading, time
from pathlib import Path
from floodcommon.schemas import Extraction
from floodcommon.triage import normalize_area
from .providers import GeminiProvider, RulesProvider

log = logging.getLogger(__name__)
TEACHER_LOG = Path(os.getenv("TEACHER_LOG", Path(__file__).resolve().parents[2] / "04_flood_nlp_model" / "data" / "teacher_labels.jsonl"))
_lock = threading.Lock()

# generic vocabulary (single health/help words, not phrases) used by the out-of-distribution guard
HEALTH_CUES = re.compile(r"ป่วย|พิการ|เจ็บ|เลือด|แผล|ไต|หัวใจ|ท้อง|คลอด|ลุก|หายใจ|หมดสติ|ไข้|ชัก|อัมพ|โรค|ผ่าตัด|ออกซิเจน|"
                         r"เดินไม่|บอด|หัก|บวม|ซึม|ฟอก|ติดเชื้อ|sick|injur|bleed|pregnan|disab|blind")
HELP_CUES = re.compile(r"ช่วยด้วย|ด่วน|ติดอยู่|ยังไม่มีใคร|ยังไม่ได้รับ|รอ(?:เรือ|ความช่วย)|เด็ก\s*\d|อายุ\s*\d|น้ำถึง|น้ำขึ้น|"
                       r"หลังคา|ชั้น\s*2|ชั้นสอง|help|sos", re.I)


LLM_STRATEGIES = ("llm", "gemini", "groq")
KEYS = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY"}


def _make(name: str, interactive: bool):
    if not os.getenv(KEYS[name]):
        return None
    try:
        if name == "gemini":
            p = GeminiProvider(interactive=interactive)
        else:
            from .groq import GroqProvider
            p = GroqProvider(interactive=interactive)
        p.name = name
        return p
    except Exception as e:
        log.error("%s unavailable at startup: %s", name, e)
        return None


class LLMChain:
    """Try each LLM provider in order; skip one that failed recently (circuit breaker)."""

    def __init__(self, providers: list, cooldown: float = 60):
        self.providers, self.cooldown = providers, cooldown
        self.down_until = {p.name: 0.0 for p in providers}
        self.model = " → ".join(f"{p.name}:{p.model}" for p in providers)
        self.last_model = None

    def extract(self, text: str) -> Extraction:
        errors = []
        live = [p for p in self.providers if time.time() >= self.down_until[p.name]] or self.providers
        for p in live:
            try:
                e = p.extract(text)
                self.last_model = f"{p.name} ({getattr(p, 'last_model', None) or p.model})"
                return e
            except Exception as err:
                self.down_until[p.name] = time.time() + self.cooldown
                errors.append(f"{p.name}: {str(err)[:160]}")
                log.warning("LLM %s failed, trying next provider", p.name)
        raise RuntimeError(" | ".join(errors) or "no LLM provider configured")

    def complete_json(self, system: str, user: str) -> dict:
        errors = []
        for p in [p for p in self.providers if time.time() >= self.down_until[p.name]] or self.providers:
            if not hasattr(p, "complete_json"):
                continue
            try:
                return p.complete_json(system, user)
            except Exception as err:
                self.down_until[p.name] = time.time() + self.cooldown
                errors.append(f"{p.name}: {str(err)[:120]}")
        raise RuntimeError(" | ".join(errors) or "no LLM available")

    def split_cases(self, text: str) -> list[str]:
        errors = []
        for p in [p for p in self.providers if time.time() >= self.down_until[p.name]] or self.providers:
            if not hasattr(p, "split_cases"):
                continue
            try:
                return p.split_cases(text)
            except Exception as err:
                self.down_until[p.name] = time.time() + self.cooldown
                errors.append(f"{p.name}: {str(err)[:120]}")
        raise RuntimeError(" | ".join(errors) or "no LLM can split")


def _build_llm(strategy: str, interactive: bool):
    names = [strategy] if strategy in ("gemini", "groq") else \
        [n.strip() for n in os.getenv("LLM_PROVIDERS", "gemini,groq").split(",") if n.strip() in KEYS]
    providers = [p for p in (_make(n, interactive) for n in names) if p is not None]
    if not providers:
        return None
    return LLMChain(providers, cooldown=60 if interactive else 0)


class IntakeAgent:
    def __init__(self, strategy: str | None = None, threshold: float | None = None, own=None, llm=None,
                 interactive: bool = True, fallback: bool = True, log_teacher: bool = True):
        self.strategy = (strategy or os.getenv("AGENT_STRATEGY") or "hybrid").lower()
        self.threshold = threshold if threshold is not None else float(os.getenv("ESCALATE_THRESHOLD", "0.5"))
        self.fallback, self.log_teacher = fallback, log_teacher
        self.own = own
        if self.own is None and self.strategy in ("hybrid", "own"):
            from .own_model import load_own_model
            self.own = load_own_model()
        self.llm = llm if llm is not None else (_build_llm(self.strategy, interactive) if self.strategy in ("hybrid",) + LLM_STRATEGIES else None)
        self.rules = RulesProvider()
        self.last = {}

    def describe(self) -> dict:
        return {"strategy": self.strategy, "threshold": self.threshold,
                "own_model": getattr(self.own, "version", None), "own_model_kind": getattr(self.own, "kind", None),
                "llm": getattr(self.llm, "model", None)}

    def split(self, text: str) -> dict:
        """One submitted text -> list of case texts (rules first, LLM only if needed)."""
        from .splitter import split_cases
        return split_cases(text, self.llm)

    def run(self, text: str) -> Extraction:
        t0 = time.time()
        info = {"provider_used": None, "confidence": None, "escalated": False, "escalation_reason": None, "ai_error": None}
        e = None
        if self.strategy == "rules":
            e, info["provider_used"] = self.rules.extract(text), "rules"
        elif self.strategy in LLM_STRATEGIES:
            e = self._llm(text, info)
        else:  # own / hybrid
            e, conf = self.own.predict(text)
            info["provider_used"], info["confidence"] = f"own_model ({self.own.version})", round(conf["overall"], 3)
            if conf.get("rule_hits"):
                info["rule_hits"] = conf["rule_hits"]
            reason = self._needs_escalation(e, conf, text)
            if self.strategy == "hybrid" and reason:
                info["escalated"], info["escalation_reason"] = True, reason
                llm_e = self._llm(text, info, quiet=True)
                if llm_e is not None:
                    self._log_teacher(text, llm_e)
                    # a critical word our model found ("ทารก", "ตัวซีด") must survive the LLM's answer
                    if (e.priority_hint_reason or "").startswith("พบคำวิกฤต") and llm_e.message_type.value == "help_request":
                        llm_e.priority_hint, llm_e.priority_hint_reason = e.priority_hint, e.priority_hint_reason
                    e = llm_e
        if e is None:
            raise RuntimeError(info["ai_error"] or "no provider available")
        e.area = normalize_area(e.area, e.street, e.landmark, text) or e.area
        info["latency_ms"] = round((time.time() - t0) * 1000)
        self.last = info
        return e

    # --- helpers ---
    def _needs_escalation(self, e: Extraction, conf: dict, text: str = "") -> str | None:
        if conf["overall"] < self.threshold:
            return f"ความมั่นใจต่ำ ({conf['overall']:.2f} < {self.threshold})"
        is_help = e.message_type.value == "help_request"
        if is_help and 0.2 < conf.get("red_flags_max_prob", 0) < 0.5:
            return "อาจเป็นเคสแดงที่โมเดลไม่แน่ใจ"
        # Out-of-distribution guard: a small model is often *confidently* wrong on wording it never saw.
        # Generic health words but no vulnerable group found -> let the LLM read it.
        if is_help and not e.flags and HEALTH_CUES.search(text):
            return "มีคำเกี่ยวกับสุขภาพ แต่โมเดลไม่พบกลุ่มเปราะบาง"
        # Never silently drop a request: non-help label but the text still asks for help.
        if not is_help and HELP_CUES.search(text):
            return "จัดเป็นข้อความประเภทอื่น แต่มีสัญญาณขอความช่วยเหลือ"
        return None

    def _llm(self, text: str, info: dict, quiet: bool = False):
        if self.llm is None:
            info["ai_error"] = "ไม่มี API key ของ LLM (GEMINI_API_KEY / GROQ_API_KEY)"
            if self.strategy in LLM_STRATEGIES and self.fallback:
                info["provider_used"] = "rules (fallback)"
                return self.rules.extract(text)
            return None
        try:
            e = self.llm.extract(text)
            last = getattr(self.llm, "last_model", None) or self.llm.model
            info["provider_used"] = last if isinstance(self.llm, LLMChain) else f"llm ({last})"
            return e
        except Exception as err:
            info["ai_error"] = str(err)[:300]
            log.error("LLM failed: %s", err)
            if self.strategy in LLM_STRATEGIES and self.fallback:
                info["provider_used"] = "rules (fallback)"
                return self.rules.extract(text)
            if self.strategy in LLM_STRATEGIES:
                raise
            return None   # hybrid keeps own-model answer

    def _log_teacher(self, text: str, e: Extraction):
        """The LLM's answer becomes a training example for our model (see 04_flood_nlp_model/train.py --extra)."""
        if not self.log_teacher:
            return
        row = {"text": text, "message_type": e.message_type.value, "flags": [f.value for f in e.flags],
               "needs": [n.value for n in e.needs], "water_level": e.water_level.value if e.water_level else None,
               "source": f"teacher:{getattr(self.llm, 'last_model', None)}"}
        try:
            with _lock, open(TEACHER_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception as err:
            log.warning("cannot write teacher log: %s", err)

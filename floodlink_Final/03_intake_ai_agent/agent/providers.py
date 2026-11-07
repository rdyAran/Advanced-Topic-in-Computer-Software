"""LLM + baseline providers.

  * GeminiProvider - teacher LLM (structured JSON output, fast fail-over between models)
  * RulesProvider  - keyword baseline = the "before AI" comparison in evaluation
Our own trained model lives in own_model.py; the routing logic in router.py.
"""
import json, os, re, time, logging
from floodcommon.schemas import Extraction, MessageType, WaterLevel, Flag, Need
from floodcommon.triage import normalize_area

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """คุณคือเจ้าหน้าที่คัดแยกข้อความขอความช่วยเหลือช่วงน้ำท่วมในหาดใหญ่ จ.สงขลา
อ่านข้อความ 1 ข้อความ แล้วดึงข้อมูลออกมาตาม schema

กติกา:
1. ดึงเฉพาะข้อมูลที่ข้อความระบุ ห้ามเดา ถ้าไม่ระบุให้เป็น null หรือ list ว่าง
2. message_type:
   - help_request = ขอความช่วยเหลือ (รวมกรณีญาติหรือคนอื่นแจ้งแทน หรือแชร์ต่อ)
   - hazard_report = ทีมกู้ภัยหรือคนแจ้งจุดอันตราย เช่น รถจมใต้น้ำ น้ำเชี่ยว สายไฟขาด งู
   - status_update_resolved = แจ้งว่าได้รับความช่วยเหลือแล้ว ไม่ต้องแชร์ต่อ
   - donation_offer = เสนอบริจาค เสนอเรือ หรือเสนอตัวช่วย
   - irrelevant = ให้กำลังใจ บ่น หรือไม่มีข้อมูลที่ใช้งานได้
3. adults = จำนวนผู้ใหญ่ รวมผู้สูงอายุ แต่ไม่รวมเด็ก ถ้าข้อความบอกจำนวนรวม (เช่น "อยู่กัน 5 คน" และมีเด็ก 1 คน) ให้ลบจำนวนเด็กออก
4. children_ages เป็นปี: 9 เดือน = 0.75, 6 เดือน = 0.5, "เด็กแรกเกิด" = 0.1
5. elderly_ages = อายุของคนที่อายุ 60 ปีขึ้นไปที่ระบุตัวเลข
5.1 ถ้าบอกเป็นจำนวนคน ไม่ได้บอกอายุ (เช่น "เด็ก 12" "ผู้สูงอายุ 5" ในแบบฟอร์ม "จำนวนคน: ผู้ใหญ่ 1 เด็ก 12 ผู้สูงอายุ 5")
    ให้ใส่ children_count / elderly_count และ adults = ผู้ใหญ่ + ผู้สูงอายุ (ตัวอย่างนี้ adults=6, children_count=12, elderly_count=5)
5.2 building_floors = ที่พักมีกี่ชั้น (บ้านชั้นเดียว=1, บ้าน 2 ชั้น=2, ตึก/คอนโด 3 ชั้นขึ้นไป=3) — "น้ำถึงชั้น 2" คือระดับน้ำ ไม่ใช่จำนวนชั้นของบ้าน
6. flags: bedridden=ติดเตียง/ช่วยเหลือตัวเองไม่ได้, dialysis=ฟอกไต/ล้างไต, heart=โรคหัวใจ, pregnant=ตั้งครรภ์/คนท้อง,
   in_labor=เจ็บท้องคลอด/น้ำเดิน, injured=บาดเจ็บ/เลือดออก/กระดูกหัก, disabled_blind=ตาบอด/หูหนวก/ผู้พิการ,
   wheelchair=นั่งวีลแชร์/เดินไม่ได้/เดินลำบาก, sick_now=ป่วยอยู่ตอนนี้ (ไข้สูง ชัก หายใจลำบาก หมดสติ ตัวซีด),
   chronic_illness=มีโรคประจำตัว (เบาหวาน ความดัน หอบหืด ฯลฯ), cannot_swim=ว่ายน้ำไม่เป็น
7. water_level: knee=เข่า, waist=เอว, chest=อก/เกือบมิดหัว, floor1=มิดชั้น 1/ชั้นล่างจม/บ้านชั้นเดียวจม,
   floor2=ถึงชั้น 2, roof=อยู่บนหลังคา
8. needs: food=อาหาร, water=น้ำดื่ม, milk=นมเด็ก, medicine=ยา, evacuation=ขอเรือ/อพยพ, power=แบตหมด/ไม่มีไฟชาร์จ,
   medical=ต้องการแพทย์/รถพยาบาล/ออกซิเจน
   lost_contact = true ถ้าญาติบอกว่าติดต่อไม่ได้แล้ว แบตหมด หรือขาดการติดต่อ
9. ข้อความอาจสะกดผิด ไม่เว้นวรรค หรือเป็นภาษาพูด เช่น "นำ้"="น้ำ", "ชวย"="ช่วย" ให้ตีความตามความหมาย
10. summary = สรุป 1 บรรทัดสำหรับเจ้าหน้าที่ เช่น "5 คน มีผู้ป่วยฟอกไต น้ำถึงชั้น 2 ขอเรือ"
"""


def to_gemini_schema(model) -> dict:
    """Pydantic JSON schema -> Gemini response_schema dict (no defaults/titles, $refs inlined, nullable)."""
    root = model.model_json_schema()
    defs = root.get("$defs", {})
    from floodcommon.schemas import LLM_HIDDEN
    root["properties"] = {k: v for k, v in root["properties"].items() if k not in LLM_HIDDEN}

    def conv(node: dict) -> dict:
        if "$ref" in node:
            return conv(defs[node["$ref"].split("/")[-1]])
        if "anyOf" in node:  # Optional[X] -> X + nullable
            opts = [o for o in node["anyOf"] if o.get("type") != "null"]
            out = conv(opts[0]); out["nullable"] = True
            if "description" in node: out["description"] = node["description"]
            return out
        out = {"type": node["type"].upper()}
        if "description" in node: out["description"] = node["description"]
        if "enum" in node: out["enum"] = node["enum"]
        if node["type"] == "array": out["items"] = conv(node["items"])
        if node["type"] == "object":
            out["properties"] = {k: conv(v) for k, v in node["properties"].items()}
            out["required"] = list(node["properties"])  # always return every key (null/[] when absent)
        return out
    return conv(root)


def _gen(model: str) -> float:
    m = re.search(r"gemini-(\d+(?:\.\d+)?)", model)
    return float(m.group(1)) if m else 0.0


class GeminiProvider:
    """interactive=True (API/web): fail over fast -> try backup models immediately, short waits, 60s timeout.
    interactive=False (evaluation): be patient with rate limits so scores aren't polluted by fallbacks."""
    RETRYABLE = ("429", "RESOURCE_EXHAUSTED", "500", "503", "UNAVAILABLE", "DEADLINE", "timed out", "Timeout", "EMPTY_RESPONSE")

    def __init__(self, api_key: str | None = None, model: str | None = None, interactive: bool = True):
        from google import genai  # imported lazily so rules mode needs no SDK
        from google.genai import types
        try:
            self.client = genai.Client(api_key=api_key or os.environ["GEMINI_API_KEY"],
                                       http_options=types.HttpOptions(timeout=60_000))
        except Exception:
            self.client = genai.Client(api_key=api_key or os.environ["GEMINI_API_KEY"])
        self.interactive = interactive
        self.no_thinking_cfg: set[str] = set()   # models that reject the low-thinking setting
        self.last_model, self.last_latency = None, None
        self.pinned = bool(model or os.getenv("GEMINI_MODEL"))
        ranked = self.rank_models()
        self.model = model or os.getenv("GEMINI_MODEL") or (ranked[0] if ranked else "gemini-flash-latest")
        self.backups = [m for m in ranked if m != self.model][:2]   # used when the main model is busy
        log.info("Gemini model: %s | backups: %s", self.model, self.backups)

    def rank_models(self) -> list[str]:
        """Usable text 'flash' models, best first (stable > preview, newer > older, full > lite)."""
        import re as _re
        try:
            names = [m.name.replace("models/", "") for m in self.client.models.list()]
        except Exception as e:
            log.warning("cannot list models (%s)", e)
            return []
        bad = ("image", "tts", "audio", "live", "thinking", "embedding")
        cands = [n for n in names if "flash" in n and not any(x in n for x in bad)]
        def key(n):
            v = _re.search(r"gemini-(\d+(?:\.\d+)?)", n)
            return ("preview" not in n and "exp" not in n, float(v.group(1)) if v else 0.0, "lite" not in n, -len(n))
        return sorted(cands, key=key, reverse=True)

    def pick_model(self) -> str:
        r = self.rank_models()
        return r[0] if r else "gemini-flash-latest"

    def _thinking(self, model: str):
        """Lowest thinking setting the SDK/model accepts (Gemini 3.x: thinking_level, 2.x: thinking_budget)."""
        from google.genai import types
        if model in self.no_thinking_cfg or not hasattr(types, "ThinkingConfig"):
            return None
        try:
            if _gen(model) >= 3:
                return types.ThinkingConfig(thinking_level="low")
            return types.ThinkingConfig(thinking_budget=0)
        except Exception:
            return None

    def _call(self, model: str, text: str) -> Extraction:
        from google.genai import types
        kw = dict(system_instruction=SYSTEM_PROMPT, response_mime_type="application/json",
                  response_schema=to_gemini_schema(Extraction), temperature=0)
        th = self._thinking(model)
        if th is not None:
            kw["thinking_config"] = th
        t0 = time.time()
        try:
            resp = self.client.models.generate_content(model=model, contents=text, config=types.GenerateContentConfig(**kw))
        except Exception as e:
            if th is not None and "thinking" in str(e).lower():   # model rejects this thinking setting
                log.warning("model %s rejected thinking config; disabling it", model)
                self.no_thinking_cfg.add(model)
                kw.pop("thinking_config")
                resp = self.client.models.generate_content(model=model, contents=text, config=types.GenerateContentConfig(**kw))
            else:
                raise
        self.last_latency = round(time.time() - t0, 1)
        log.info("Gemini %s answered in %ss", model, self.last_latency)
        if not resp.text:   # model answered with no text (blocked / only "thinking" / glitch)
            reason = None
            try:
                reason = resp.candidates[0].finish_reason
            except Exception:
                pass
            if th is not None:
                self.no_thinking_cfg.add(model)   # next try on this model without the thinking setting
            raise RuntimeError(f"EMPTY_RESPONSE from {model} (finish_reason={reason})")
        return Extraction.model_validate_json(resp.text)

    def extract(self, text: str) -> Extraction:
        if self.interactive:   # main model, then each backup, ~1s apart
            plan = [(self.model, 0)] + [(m, 1) for m in self.backups] + [(self.model, 2)]
        else:                  # same model, exponential back-off, then backups
            plan = [(self.model, 0)] + [(self.model, 2 ** i * 5) for i in range(4)] + [(m, 5) for m in self.backups]
        last = None
        for i, (model, wait) in enumerate(plan):
            if wait:
                time.sleep(wait)
            try:
                ext = self._call(model, text)
                if model != self.model:
                    log.info("served by backup model %s", model)
                self.last_model = model
                return ext
            except Exception as e:
                last, msg = e, str(e)
                log.warning("Gemini error [model=%s] (try %d): %s", model, i + 1, msg[:300])
                if ("NOT_FOUND" in msg or "404" in msg) and model != self.model:
                    if model in self.backups:
                        self.backups.remove(model)      # retired backup -> drop it, try the next one
                    continue
                if ("NOT_FOUND" in msg or "404" in msg) and not self.pinned and model == self.model:
                    ranked = [m for m in self.rank_models() if m != model]   # model retired -> promote next one
                    if ranked:
                        self.model, self.backups = ranked[0], ranked[1:3]
                        log.warning("model %s retired, switching to %s", model, self.model)
                        try:
                            return self._call(self.model, text)
                        except Exception as e2:
                            last, msg = e2, str(e2)
                if not any(k in msg for k in self.RETRYABLE) or "PerDay" in msg:
                    break       # bad key / bad schema / daily quota used up -> retrying won't help
        raise RuntimeError(f"Gemini failed [model={self.model}]: {str(last)[:400]}")


def _gemini_split(self, text: str) -> list[str]:
    from google.genai import types
    from .splitter import SPLIT_PROMPT
    cfg = types.GenerateContentConfig(system_instruction=SPLIT_PROMPT, response_mime_type="application/json", temperature=0,
                                      response_schema={"type": "OBJECT", "properties": {"cases": {"type": "ARRAY", "items": {"type": "STRING"}}}, "required": ["cases"]})
    th = self._thinking(self.model)
    if th is not None:
        cfg.thinking_config = th
    r = self.client.models.generate_content(model=self.model, contents=text, config=cfg)
    return json.loads(r.text or "{}").get("cases", [])


GeminiProvider.split_cases = _gemini_split


def _gemini_json(self, system: str, user: str) -> dict:
    from google.genai import types
    cfg = types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json", temperature=0)
    th = self._thinking(self.model)
    if th is not None:
        cfg.thinking_config = th
    r = self.client.models.generate_content(model=self.model, contents=user, config=cfg)
    return json.loads(r.text or "{}")


GeminiProvider.complete_json = _gemini_json


class RulesProvider:
    """Keyword baseline. Intentionally simple - represents the non-AI approach."""
    WATER = [(WaterLevel.roof, ["หลังคา"]), (WaterLevel.floor2, ["ชั้น2", "ชั้น 2"]),
             (WaterLevel.floor1, ["ชั้น1", "ชั้น 1", "ชั้นล่าง", "ชั้นเดียวจม"]), (WaterLevel.chest, ["อก", "มิดหัว"]),
             (WaterLevel.waist, ["เอว"]), (WaterLevel.knee, ["เข่า"])]
    FLAGS = {Flag.bedridden: ["ติดเตียง"], Flag.dialysis: ["ฟอกไต", "ป่วยไต"], Flag.heart: ["หัวใจ"],
             Flag.pregnant: ["ท้อง", "ตั้งครรภ์"], Flag.injured: ["ขาหัก", "บาด", "เลือดออก", "บาดเจ็บ"],
             Flag.disabled_blind: ["ตาบอด"], Flag.wheelchair: ["วีลแชร์", "เดินไม่ได้"]}
    NEEDS = {Need.food: ["อาหาร", "มาม่า"], Need.water: ["น้ำดื่ม", "น้ำกิน"], Need.milk: ["นม"],
             Need.medicine: ["ยา"], Need.evacuation: ["เรือ", "อพยพ"], Need.power: ["แบต", "ชาร์จ"]}

    def extract(self, text: str) -> Extraction:
        t = text.replace("นำ้", "น้ำ").replace("ชวย", "ช่วย")
        has = lambda words: any(w in t for w in words)
        if has(["รับแล้ว", "ได้รับความช่วยเหลือแล้ว", "ไม่ต้องแชร์"]):
            mtype = MessageType.status_update_resolved
        elif has(["ห้ามเข้า", "จุดอันตราย", "ทีมเรือแจ้ง", "รายงาน", "ระวัง", "สายไฟ"]):
            mtype = MessageType.hazard_report
        elif has(["บริจาค", "พร้อมไปช่วย", "จะส่งไป", "ขอส่ง", "ข้าวกล่อง"]):
            mtype = MessageType.donation_offer
        elif has(["ช่วย", "ติด", "ด่วน", "น้ำ", "ขอเรือ"]) and len(t) > 25:
            mtype = MessageType.help_request
        else:
            mtype = MessageType.irrelevant

        children = []
        for n, unit in re.findall(r"เด็ก\s*(\d+)\s*(เดือน|ขวบ)", t):
            children.append(round(int(n) / 12, 2) if unit == "เดือน" else float(n))
        elderly = [int(a) for a in re.findall(r"อายุ\s*(\d+)", t) if int(a) >= 60]
        m = re.search(r"ผู้ใหญ่\s*(\d+)", t) or re.search(r"(?:อยู่กัน|รวม)\s*(\d+)\s*คน", t)
        adults = int(m.group(1)) if m else None
        if m and not t[m.start():m.start() + 7].startswith("ผู้ใหญ่"):
            adults = max(adults - len(children), 0)
        d = re.search(r"ติด(?:มา|อยู่)?\s*(\d+)\s*วัน", t)
        c = re.search(r"0\d{1,2}-?[\dx]{3}-?\d{4}", t)
        water = next((lvl for lvl, kws in self.WATER if has(kws)), None)
        street = re.search(r"(ซ\.\S+(?:\s\d+)?|ซอย\S+|ถ\.\S+)", t)
        return Extraction(
            message_type=mtype, area=normalize_area(t), street=street.group(1) if street else None,
            adults=adults, children_ages=children, elderly_ages=elderly,
            flags=[f for f, kws in self.FLAGS.items() if has(kws)], water_level=water,
            days_trapped=int(d.group(1)) if d else None,
            needs=[n for n, kws in self.NEEDS.items() if has(kws)],
            contact=c.group(0) if c else None, summary=t[:80],
        )

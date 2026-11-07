"""Draft-label data/to_label.csv with Groq (teacher), following LABEL_GUIDE.md. Resumable, never crashes on one bad batch.

  python label_groq.py --limit 30              # try a small batch first, check data/labels.jsonl
  python label_groq.py                          # label everything; stops cleanly at the daily limit -> run again later
  python label_groq.py --list-models           # which models your key can use (names change over time)
  python label_groq.py --models openai/gpt-oss-120b,<another model>   # switch model automatically when one hits its daily quota

  python label_groq.py --shard 2/2 --models gemini-<name>   # Gemini (name from --list-models), uses GEMINI_API_KEY

Needs GROQ_API_KEY and/or GEMINI_API_KEY in the project .env (never paste keys in chat).
"""
import argparse, csv, json, os, re, sys, time, urllib.error, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV = HERE.parents[1] / ".env"
if ENV.exists():
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())

TYPES = ["help_request", "status_update_resolved", "hazard_report", "donation_offer", "irrelevant"]
FLAGS = ["bedridden", "wheelchair", "disabled_blind", "dialysis", "heart", "pregnant", "in_labor", "injured",
         "chronic_illness", "sick_now", "cannot_swim"]
NEEDS = ["evacuation", "food", "water", "milk", "medicine", "power", "medical"]
WATER = ["knee", "waist", "chest", "floor1", "floor2", "roof"]
PRIO = ["red", "orange", "yellow", "green", "none"]
REPORTER = ["self", "relative_or_friend", "third_party", "unknown"]

# Compact version of LABEL_GUIDE.md (the full guide is for humans; sending it every call burns the per-minute token quota)
SYSTEM = """ติดป้ายข้อความ Facebook ช่วงน้ำท่วมหาดใหญ่ (พ.ย. 2568) ตามข้อความเท่านั้น ห้ามเดา ไม่รู้ = null หรือ []
<NAME> <URL> และตัวเลขบางตัวถูกปิด/สุ่มเพื่อความเป็นส่วนตัว ไม่ต้องสนใจ
message_type: help_request (ขอช่วยตัวเอง/คนอื่น รวมถึงตามหาคนที่ติดต่อไม่ได้) | status_update_resolved (ได้รับการช่วย/ปลอดภัยแล้ว) | hazard_report (แจ้งจุดอันตราย) | donation_offer (เสนอเรือ/ของ/แรง/ที่พัก) | irrelevant (ให้กำลังใจ ถามข่าว ความเห็น ประกาศเบอร์หน่วยงาน)
 ข้อความผสมที่มีการขอช่วย = help_request; "ช่วยเพื่อนด้วย" ไม่มีรายละเอียด = help_request + insufficient_info=true
flags: bedridden(ติดเตียง/อัมพาต) wheelchair(รถเข็น/เดินลำบาก) disabled_blind(พิการ/ตาบอด) dialysis(ฟอกไต/ล้างไต) heart(โรคหัวใจ) pregnant(ตั้งครรภ์) in_labor(ปวดท้องจะคลอด/น้ำเดิน) injured(บาดเจ็บ/เลือดออก) chronic_illness(โรคประจำตัว ความดัน เบาหวาน อัลไซเมอร์) sick_now(ป่วยตอนนี้ ไข้สูง หายใจลำบาก ขาดยาอาการแย่) cannot_swim(ว่ายน้ำไม่เป็น)
needs: evacuation food water milk medicine power(แบต/ไฟ) medical(ต้องการหมอ/ไปรพ.)
water_level: knee waist chest floor1(มิดชั้น1) floor2(ถึงชั้น2) roof(บนหลังคา/จะมิดหลังคา) | null
adults=ผู้ใหญ่รวมผู้สูงอายุ ไม่รวมเด็ก; children_ages เป็นปี (6 เดือน=0.5); บอกจำนวนแต่ไม่บอกอายุ -> children_count / elderly_count; elderly_ages = อายุ>=60
reporter: self | relative_or_friend | third_party | unknown ; lost_contact = ผู้แจ้งติดต่อคนในบ้านไม่ได้
priority (เฉพาะ help_request ไม่งั้น none):
 red = ฟอกไต หัวใจ บาดเจ็บ in_labor sick_now รุนแรง ทารก<1ปี บนหลังคา/น้ำจะมิด ติดเตียง+น้ำถึงชั้น2 ท้อง+น้ำมิดชั้น1
 orange = ติดเตียง พิการ ตั้งครรภ์ ผู้สูงอายุ70+ เด็ก<6ปี น้ำถึงชั้น2 ติดต่อไม่ได้+มีกลุ่มเปราะบาง
 yellow = ติดค้าง ขาดอาหาร/น้ำ/ยา ติด>=2วัน น้ำถึงเอว/มิดชั้น1 ; green = ต้องการของ ไม่เร่งด่วน
กฎเพิ่ม (จากการตรวจชุดทดสอบ):
 - "ติดอยู่ชั้น 2" / "อยู่ชั้น 2" = คนอยู่ชั้น 2 ไม่ใช่ระดับน้ำ; water_level=floor2 เฉพาะเมื่อบอกว่าน้ำถึง/จะถึงชั้น 2
 - "ทารก" "เด็กแรกเกิด" "X เดือน" = children_ages<1 -> red ; "เด็กเล็ก" = เด็ก<6 -> อย่างน้อย orange
 - เด็กมีไข้/ตัวซีด, คนแก่ "ไม่ไหวแล้ว"/เป็นลม/หมดสติ, ไม่ได้ฟอกไต, ล้ม/กระดูกหัก -> flag ที่ตรง + red
 - ติดต่อไม่ได้อย่างเดียว = yellow; ติดต่อไม่ได้ + เด็กเล็ก/ผู้สูงอายุ/ผู้ป่วย = orange
 - help_request ทุกข้อความต้องมีสี (red/orange/yellow/green) ห้ามใส่ none
 - insufficient_info=true เฉพาะเมื่อ "ไม่มีตำแหน่งเลย" หรือ "ไม่รู้ว่าเกิดอะไร"; มีบ้านเลขที่/ซอย/ชื่ออาคาร = false
 - "ฝากเคสนี้" "ฝากน้อง/เพื่อนด้วย" "ช่วยไปส่งอาหาร" = help_request (ไม่ใช่ irrelevant/donation_offer)
 - คอมเมนต์ใต้คลิปที่แค่แสดงความรู้สึก/ขอบคุณ = irrelevant ; ประกาศเบอร์หน่วยงาน = irrelevant
person_names = ชื่อคนที่ยังเหลือในข้อความ (เอาไว้ปิด)
ตอบ JSON เดียว: {"items":[{...}]} ครบทุก id ตามลำดับ ทุก item มีคีย์:
id message_type flags needs water_level adults children_ages children_count elderly_ages elderly_count days_trapped lost_contact reporter n_cases area has_contact insufficient_info priority priority_reason(สั้น) person_names confidence(0-1)"""

RID = re.compile(r"R\d{5}")

# ---- auto "irrelevant" labels without an LLM: ONLY short cheer/emotion comments with no hint of a request/offer/question
SUSPECT = re.compile(r"ช่วย|ข่วย|ช้วย|ฝาก|🆘|\bsos\b|เรือ|\d+\s*ลำ|เจ็[ทต]|สกี|บริจา|ส่งให้|ส่งไป|รับ(?:ของ|บริจาค)|เขต\s*\d|ซอย|ซ\.|ถนน|ถ\.|แถว|หมู่|ม\.\d|"
                     r"ดู(?:ให้|หน่อย|ด้วย)|ไปดู|ยังไม่(?:มี|ได้)|เข้าไม่ถึง|ไม่มีใคร|ติดต่อ|อายุ|\d|คน(?:แก่|ชรา|ป่วย)|ผู้สูงอายุ|เด็ก(?!ๆ)|ยาย|"
                     r"เพื่อน|ญาติ|ด่วน|อดข้าว|อดอาหาร|อดตาย|หิว|ไม่ไหว|จะตาย|มีคน|ติดอยู่|ติดค้าง|ท่วม|น้ำขึ้น|อพยพ|พิกัด|เคส|"
                     r"ที่ไหน|ไหนคะ|ไหนครับ|ได้ไหม|ได้มั้ย|ได้ไม๊|\?|ไลฟ์|ลิ้ง|ลิงก์|<URL>|มาม่า|อาหาร|น้ำดื่ม|ยา(?:ประจำ|รักษา)|ไฟ(?:ดับ|รั่ว)|แบต", re.I)
CHEER = re.compile(r"สู้|กำลังใจ|สุดยอด|ปลอดภัย|ฮีโร่|เก่ง|ขอบคุณ|ขอบพระคุณ|สาธุ|อนุโมทนา|บุญ|คุ้มครอง|สงสาร|น้ำตา|บีบหัวใจ|หดหู่|ใจจะขาด|เยี่ยม|ที่สุด|"
                   r"น่ารัก|เอ็นดู|ร้องไห้|เศร้า|รอดแล้ว|^[\W_]*$")
def auto_ok(t: str) -> bool:
    """Short cheer/emotion comment with no sign of a request/offer/question -> safe to label 'irrelevant' without an LLM."""
    return len(t) < 60 and bool(CHEER.search(t)) and not SUSPECT.search(t)


def recheck_auto(folder: Path, texts: dict) -> int:
    """Remove earlier auto-labels that the stricter rule no longer trusts, so the LLM labels them (backup kept as .bak)."""
    removed = 0
    for fp in folder.glob("labels*.jsonl"):
        lines = fp.read_text(encoding="utf-8").splitlines()
        keep = []
        for l in lines:
            try:
                d = json.loads(l)
            except json.JSONDecodeError:
                continue
            if d.get("label_model") == "rule:chatter" and not auto_ok(texts.get(d["id"], "")):
                removed += 1; continue
            keep.append(l)
        if len(keep) != len(lines):
            bak = fp.with_suffix(".jsonl.bak")
            if not bak.exists():
                bak.write_text("\n".join(lines) + "\n", encoding="utf-8")
            fp.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
    return removed


def _as_list(v) -> list:
    """LLMs sometimes send 85 or "85, 90" or "dialysis" where a list is expected."""
    if v is None or v == "":
        return []
    if isinstance(v, (list, tuple)):
        return list(v)
    if isinstance(v, str):
        return [x.strip() for x in re.split(r"[,|;/]", v) if x.strip()]
    return [v]


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, str):
        m = re.search(r"\d+(?:\.\d+)?", v)
        v = float(m.group(0)) if m else None
        if v is None:
            return None
    if isinstance(v, (int, float)) and v >= 0 and v == v:            # v == v drops NaN
        return int(v) if float(v).is_integer() else float(v)
    return None


def clean(it: dict) -> dict | None:
    """Keep only valid values. An item without a valid message_type is rejected (retried later), never guessed."""
    if not isinstance(it, dict) or it.get("message_type") not in TYPES:
        return None
    pick = lambda v, ok: v if isinstance(v, str) and v in ok else None
    enum_list = lambda v, ok: sorted({x for x in _as_list(v) if isinstance(x, str) and x in ok})
    nums = lambda v, lo, hi: [n for n in (_num(x) for x in _as_list(v)) if n is not None and lo <= n <= hi]
    m = RID.search(str(it.get("id", "")))
    area = it.get("area")
    return {
        "id": m.group(0) if m else str(it.get("id")), "message_type": it["message_type"],
        "flags": enum_list(it.get("flags"), FLAGS), "needs": enum_list(it.get("needs"), NEEDS),
        "water_level": pick(it.get("water_level"), WATER), "adults": _num(it.get("adults")),
        "children_ages": nums(it.get("children_ages"), 0, 17.99), "children_count": _num(it.get("children_count")),
        "elderly_ages": nums(it.get("elderly_ages"), 55, 110), "elderly_count": _num(it.get("elderly_count")),
        "days_trapped": _num(it.get("days_trapped")),
        "lost_contact": it.get("lost_contact") in (True, "true", "True", 1, "1", "yes"),
        "reporter": pick(it.get("reporter"), REPORTER) or "unknown",
        "n_cases": _num(it.get("n_cases")) or 1, "area": area if isinstance(area, str) else None,
        "has_contact": it.get("has_contact") in (True, "true", "True", 1, "1", "yes"),
        "insufficient_info": it.get("insufficient_info") in (True, "true", "True", 1, "1", "yes"),
        "priority": pick(it.get("priority"), PRIO) or "none", "priority_reason": str(it.get("priority_reason") or "")[:200],
        "person_names": [n for n in _as_list(it.get("person_names")) if isinstance(n, str) and 1 < len(n) < 40],
        "confidence": _num(it.get("confidence")),
    }


def safe_clean(it) -> dict | None:
    try:
        return clean(it)
    except Exception as e:                                           # one weird item must never stop the whole run
        print(f"  ข้าม 1 รายการที่รูปแบบเสีย ({e.__class__.__name__})")
        return None


class DailyLimit(Exception):
    pass


class ModelGone(Exception):
    pass


def _secs(v: str | None) -> float | None:
    """'7.66s' / '1m2.5s' / '350ms' / '12' -> seconds"""
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        pass
    total = 0.0
    for num, unit in re.findall(r"([\d.]+)(ms|h|m|s)", v):
        total += float(num) * {"ms": .001, "s": 1, "m": 60, "h": 3600}[unit]
    return total or None


def _parse_json(text: str) -> dict:
    text = re.sub(r"<think>[\s\S]*?</think>", "", text or "")     # some models prepend their reasoning
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text or "")
        return json.loads(m.group(0)) if m else {}


GROQ_URL = "https://api.groq.com/openai/v1"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai"        # Gemini's OpenAI-compatible API


def is_gemini(model: str) -> bool:
    return model.lower().startswith(("gemini", "models/gemini"))


def provider(model: str) -> tuple[str, str]:
    """(base url, api key) for a model name. gemini-* -> Google, everything else -> Groq."""
    if is_gemini(model):
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            sys.exit("ไม่พบ GEMINI_API_KEY ใน .env")
        return GEMINI_URL, key
    if not (os.getenv("GROQ_API_KEY") or os.getenv("GEMINI_API_KEY")):
        sys.exit("ไม่พบ GROQ_API_KEY หรือ GEMINI_API_KEY ใน .env")
    return GROQ_URL, os.environ["GROQ_API_KEY"]


def _gemini_retry(msg: str) -> float | None:
    m = re.search(r'retryDelay"?\s*:\s*"?([\d.]+)s', msg)             # Gemini puts the wait in the error body
    return float(m.group(1)) if m else None


class Labeler:
    def __init__(self, model: str, effort: str, verbose: bool = True):
        self.model, self.effort, self.verbose = model, effort, verbose
        self.wait_until = 0.0
        self.max_batch = 99                 # shrinks automatically if this model's per-minute quota is small
        self.shown_429 = False

    def _post(self, body: dict) -> tuple[dict, dict]:
        delay = self.wait_until - time.time()
        if delay > 0:
            time.sleep(delay)
        base, key = provider(self.model)
        req = urllib.request.Request(base + "/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {key}",
                                              "Content-Type": "application/json", "User-Agent": "floodlink-labeler"})
        with urllib.request.urlopen(req, timeout=180) as r:
            data, h = json.loads(r.read()), r.headers
        # pace ourselves: if the minute's token budget is nearly used, wait for it to refill
        try:
            if int(h.get("x-ratelimit-remaining-tokens", 10 ** 9)) < 4000:
                self.wait_until = time.time() + (_secs(h.get("x-ratelimit-reset-tokens")) or 10)
        except ValueError:
            pass
        return data, h

    def _request(self, batch: list[dict], json_mode: bool) -> list[dict]:
        user = "\n\n".join(f"### id={r['row_id']}\n{r['text'][:1200]}" for r in batch)
        gem = is_gemini(self.model)
        per_item = 600 if self.model.startswith("openai/gpt-oss") else 800 if gem else 350   # thinking models need room
        body = {"model": self.model.replace("models/", ""), "temperature": 0,
                ("max_tokens" if gem else "max_completion_tokens"): per_item * len(batch) + (2000 if gem else 800),
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if self.model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = self.effort
        elif "qwen3" in self.model:
            body["reasoning_effort"] = "none"                  # labelling doesn't need long thinking; saves tokens
        elif gem:
            body["reasoning_effort"] = "low"
        for attempt in range(6):
            try:
                data, _ = self._post(body)
                items = _parse_json(data["choices"][0]["message"].get("content") or "").get("items", [])
                out = [c for c in (safe_clean(i) for i in items) if c] if isinstance(items, list) else []
                if len(out) == len(batch) and not any(o["id"] in {r["row_id"] for r in batch} for o in out):
                    for o, r in zip(out, batch):          # model mangled the ids but kept the order
                        o["id"] = r["row_id"]
                return out
            except urllib.error.HTTPError as e:
                msg = e.read().decode(errors="ignore")
                if e.code == 429 and re.search(r"per day|TPD|RPD|PerDay|per_day|daily", msg, re.I):
                    raise DailyLimit(msg[:250])
                if e.code == 400 and "response_format" in msg and "response_format" in body:
                    body.pop("response_format"); continue      # provider doesn't support JSON mode -> plain text, we parse it
                if e.code in (401, 403):
                    raise ModelGone(f"คีย์ใช้ไม่ได้หรือไม่มีสิทธิ์ ({e.code}) — เช็กคีย์ใน .env: {msg[:150]}")
                if e.code in (404,) or "model_decommissioned" in msg or "model_not_found" in msg:
                    raise ModelGone(msg[:200])
                if "context_length_exceeded" in msg:
                    raise ModelGone("โมเดลนี้รับข้อความยาวไม่พอ (context เล็กเกินไป) — เลือกโมเดลที่ context >= 32000")
                if e.code == 400 and ("reasoning" in msg) and any(k in body for k in ("reasoning_effort", "reasoning_format")):
                    body.pop("reasoning_effort", None); body.pop("reasoning_format", None); continue   # model doesn't support it
                if e.code == 429 and re.search(r"[Rr]equest too large|Requested\s*\d+", msg):
                    # one request is bigger than this model's whole per-minute quota -> waiting won't help, send less
                    if len(batch) > 1:
                        self.max_batch = max(1, len(batch) // 2)
                        print(f"  คำขอใหญ่เกินโควตาต่อนาทีของ {self.model} -> ลดเหลือทีละ {self.max_batch} ข้อความ")
                        return None
                    tk = "max_tokens" if "max_tokens" in body else "max_completion_tokens"
                    if body[tk] > 900:
                        body[tk] = 900; continue
                    print(f"  ข้อความนี้ยาวเกินโควตาของโมเดลนี้: {msg[:160]}"); return []
                if e.code == 429 or e.code >= 500:
                    if e.code == 429 and not self.shown_429:
                        self.shown_429 = True; print(f"  (429 จาก {'Gemini' if is_gemini(self.model) else 'Groq'}: {msg[:220]})")
                    wait = max(_secs(e.headers.get("retry-after")) or 0, _gemini_retry(msg) or 0, _secs(e.headers.get("x-ratelimit-reset-tokens")) or 0,
                               _secs(e.headers.get("x-ratelimit-reset-requests")) or 0) or 2 ** attempt * 3
                    wait = max(wait, 2 + attempt * 2)             # never hammer the API with 0-second retries
                    if self.verbose:
                        print(f"  {e.code} รอ {wait:.0f}s")
                    time.sleep(min(wait + 1, 90)); continue
                if e.code == 400 and ("json_validate_failed" in msg or "max_completion_tokens" in msg or "output" in msg):
                    return None                            # caller splits the batch / turns JSON mode off
                print(f"  {e.code}: {msg[:200]}"); return []
            except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError, KeyError) as e:
                print(f"  ลองใหม่ ({e.__class__.__name__})"); time.sleep(5)
        return []

    def label(self, batch: list[dict]) -> list[dict]:
        """Label a batch; on a JSON failure split it in half, and for a single message retry without JSON mode."""
        if len(batch) > self.max_batch:
            out = []
            for i in range(0, len(batch), self.max_batch):
                out += self.label(batch[i:i + self.max_batch])
            return out
        res = self._request(batch, json_mode=True)
        if res is not None:
            return res
        if len(batch) > 1:
            mid = len(batch) // 2
            return self.label(batch[:mid]) + self.label(batch[mid:])
        if self.max_batch < 99 and len(batch) == 1:
            res = self._request(batch, json_mode=True)       # just shrunk for quota reasons: try once more in JSON mode
            if res is not None:
                return res
        res = self._request(batch, json_mode=False)
        return res or []


SKIP = re.compile(r"whisper|tts|playai|guard|orpheus|compound|prompt-guard|distil", re.I)


def _get_models(base: str, key: str) -> list[dict]:
    req = urllib.request.Request(base + "/models", headers={"Authorization": f"Bearer {key}", "User-Agent": "floodlink-labeler"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read()).get("data", [])


def list_models():
    """Which models each configured key can use (model names change — e.g. llama-3.3-70b was retired in 2026)."""
    if os.getenv("GROQ_API_KEY"):
        try:
            data = _get_models(GROQ_URL, os.environ["GROQ_API_KEY"])
            chat = sorted((m for m in data if not SKIP.search(m.get("id", "")) and m.get("active", True)), key=lambda m: m["id"])
            size = lambda m: float((re.search(r"(\d+(?:\.\d+)?)b\b", m["id"].lower()) or [0, 0])[1])
            ok = [m for m in chat if (m.get("context_window") or 0) >= 32000 and size(m) >= 20]
            print("Groq — เหมาะกับการติดป้าย (ใหญ่ >= 20b และ context >= 32k):")
            for m in ok:
                print(f"  ✓ {m['id']:48s} context {m.get('context_window', '?')}")
            rest = [m["id"] for m in chat if m not in ok]
            if rest:
                print("  ไม่แนะนำ:", ", ".join(rest))
        except Exception as e:
            print("Groq: ดึงรายชื่อไม่ได้", e)
    if os.getenv("GEMINI_API_KEY"):
        try:
            data = _get_models(GEMINI_URL, os.environ["GEMINI_API_KEY"])
            ids = sorted({m["id"].replace("models/", "") for m in data if "gemini" in m.get("id", "")
                          and not re.search(r"embed|tts|image|live|audio|veo|imagen|native|robotics|computer", m["id"])})
            print("\nGemini — โมเดลที่คีย์นี้ใช้ได้ (แนะนำตัวที่มีคำว่า flash: เร็วและถูก, ไม่ใช่ -lite/-preview ถ้ามีตัวเลือกอื่น):")
            for i in ids:
                print(f"  ✓ {i}")
        except Exception as e:
            print("Gemini: ดึงรายชื่อไม่ได้", e)
    print("\nใช้: python label_groq.py --shard 2/2 --models <ชื่อโมเดล>")


def all_done(folder: Path) -> set:
    """Row ids labelled in ANY labels*.jsonl (single run or parallel shards)."""
    ids = set()
    for fp in folder.glob("labels*.jsonl"):
        for line in open(fp, encoding="utf-8"):
            if line.strip():
                try:
                    ids.add(json.loads(line)["id"])
                except (json.JSONDecodeError, KeyError):
                    pass                                      # a half-written last line after Ctrl+C
    return ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(HERE / "data" / "to_label.csv"))
    ap.add_argument("--out", default=str(HERE / "data" / "labels.jsonl"))
    ap.add_argument("--models", "--model", default=os.getenv("LABEL_MODELS", "openai/gpt-oss-120b"),
                    help="comma-separated; the next one is used when a model hits its daily quota")
    ap.add_argument("--effort", default="low", choices=["low", "medium", "high"])
    ap.add_argument("--batch", type=int, default=6)
    ap.add_argument("--no-auto-chatter", action="store_true", help="send short cheer/chatter to the LLM too")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--reset-failures", action="store_true", help="forget failure counts (e.g. after trying a wrong model)")
    ap.add_argument("--list-models", action="store_true", help="show the chat models this API key can use, then exit")
    ap.add_argument("--shard", default="", help='run 2 windows in parallel with different models: "1/2" and "2/2"')
    ap.add_argument("--max-fail", type=int, default=2, help="skip a message after it failed this many times")
    a = ap.parse_args()
    if not (os.getenv("GROQ_API_KEY") or os.getenv("GEMINI_API_KEY")):
        sys.exit("ไม่พบ GROQ_API_KEY หรือ GEMINI_API_KEY ใน .env")

    if a.list_models:
        list_models(); return
    rows = list(csv.DictReader(open(a.input, encoding="utf-8-sig")))
    out = Path(a.out)
    k = n_sh = None
    if a.shard:
        k, n_sh = (int(x) for x in a.shard.split("/"))
        if out.name == "labels.jsonl":                     # each window writes its own file (no clashes)
            out = out.with_name(f"labels_{k}of{n_sh}.jsonl")
    fail_file = out.with_name(out.stem + ".failures.json")
    if a.reset_failures and fail_file.exists():
        fail_file.unlink(); print("ล้างจำนวนครั้งที่ล้มเหลวแล้ว")
    n_fix = recheck_auto(out.parent, {r["row_id"]: r["text"] for r in rows})
    if n_fix:
        print(f"ตรวจป้ายอัตโนมัติรอบใหม่: {n_fix} ข้อความที่อาจเป็นการขอความช่วยเหลือ/เสนอช่วย จะส่งให้ LLM ติดป้ายแทน (สำรองไฟล์เดิมเป็น .bak)")
    done = all_done(out.parent)
    fails = json.loads(fail_file.read_text()) if fail_file.exists() else {}
    todo = [r for r in rows if r["row_id"] not in done]
    if k:
        todo = [r for r in todo if int(r["row_id"][1:]) % n_sh == k - 1]
    if not a.no_auto_chatter:          # "สู้ๆค่ะ", "ขอให้ปลอดภัย" -> irrelevant without spending tokens
        auto = [r for r in todo if auto_ok(r["text"])]
        with open(out, "a", encoding="utf-8") as f:
            for r in auto:
                f.write(json.dumps(clean({"id": r["row_id"], "message_type": "irrelevant", "priority": "none", "confidence": 0.9})
                                   | {"label_model": "rule:chatter"}, ensure_ascii=False) + "\n")
        todo = [r for r in todo if r not in auto]
        if auto:
            print(f"ติดป้ายข้อความให้กำลังใจสั้น ๆ อัตโนมัติ {len(auto)} ข้อความ (irrelevant)")
    skipped = [r for r in todo if fails.get(r["row_id"], 0) >= a.max_fail]
    todo = [r for r in todo if fails.get(r["row_id"], 0) < a.max_fail]
    if a.limit:
        todo = todo[:a.limit]
    models = [m.strip() for m in a.models.split(",") if m.strip()]
    print(f"ทั้งหมด {len(rows)} | ติดป้ายแล้ว {len(done)} | รอบนี้ {len(todo)} | ข้ามเพราะล้มเหลวซ้ำ {len(skipped)} | models {models}")

    t0, n, mi = time.time(), 0, 0
    lab = Labeler(models[0], a.effort)
    with open(out, "a", encoding="utf-8") as f:
        i = 0
        while i < len(todo):
            batch = todo[i:i + a.batch]
            try:
                items = lab.label(batch)
            except (DailyLimit, ModelGone) as e:
                kind = "โควตารายวันหมด" if isinstance(e, DailyLimit) else "ใช้โมเดลนี้ไม่ได้"
                mi += 1
                if mi >= len(models):
                    print(f"\n{kind} ({lab.model}) และไม่มีโมเดลสำรองเหลือ — ได้ {n} ข้อความในรอบนี้ รันคำสั่งเดิมอีกครั้งพรุ่งนี้\n{e}")
                    break
                print(f"\n{kind}: {lab.model} -> เปลี่ยนเป็น {models[mi]}")
                lab = Labeler(models[mi], a.effort); continue          # retry the same batch with the next model
            got = set()
            for it in items:
                if it["id"] in {r["row_id"] for r in batch} and it["id"] not in got:
                    it["label_model"] = lab.model
                    f.write(json.dumps(it, ensure_ascii=False) + "\n"); n += 1; got.add(it["id"])
            f.flush()
            for r in batch:
                if r["row_id"] not in got:
                    fails[r["row_id"]] = fails.get(r["row_id"], 0) + 1
            fail_file.write_text(json.dumps(fails))
            miss = len(batch) - len(got)
            rate = n / max(time.time() - t0, 1) * 60
            left = len(todo) - i - len(batch)
            eta = f" | เหลือ ~{left / rate:.0f} นาที" if rate > 0 else ""
            print(f"[{i + len(batch)}/{len(todo)}] +{len(got)}{f' (ขาด {miss})' if miss else ''} | {lab.model.split('/')[-1]} | ~{rate:.1f} ข้อความ/นาที{eta}")
            i += a.batch
    total = len(all_done(out.parent))
    print(f"\nรอบนี้ได้ {n} ข้อความ | รวมติดป้ายแล้ว {total}/{len(rows)} ({total / len(rows):.0%}) -> {out.name}")
    if total < len(rows):
        print("ยังไม่ครบ: รันคำสั่งเดิมอีกครั้ง (ทำต่อจากที่ค้าง)")


if __name__ == "__main__":
    main()

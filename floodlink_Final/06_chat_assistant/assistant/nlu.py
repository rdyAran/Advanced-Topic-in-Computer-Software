"""Understand a chat message: intent + slots.  Rules first (fast, offline); LLM only when the rules are unsure."""
import re
from floodcommon.triage import normalize_area
from floodcommon.location import extract_location

INTENTS = ["emergency", "request_help", "donate", "volunteer", "find_shelter", "find_distribution",
           "find_medical", "case_status", "my_status", "safe_now", "needs_overview", "info", "greeting", "thanks"]

ITEMS = [("water", r"น้ำดื่ม|น้ำเปล่า|น้ำขวด|drinking water|\bwater\b"), ("milk", r"นมเด็ก|นมผง|นมกล่อง|นม(?=\s|\d|$)|\bmilk\b|formula"),
         ("food", r"อาหาร|ข้าวกล่อง|ข้าวสาร|มาม่า|บะหมี่|ปลากระป๋อง|ถุงยังชีพ|food"), ("medicine", r"ยา(?!ย|ว|ก)|เวชภัณฑ์|medicine"),
         ("hygiene", r"ผ้าอ้อม|แพมเพิส|ผ้าอนามัย|สบู่|ยาสีฟัน|กระดาษทิชชู|ถุงขยะ|hygiene"), ("clothes", r"เสื้อผ้า|ผ้าห่ม|clothes"),
         ("power", r"พาวเวอร์แบงค์|power ?bank|ไฟฉาย|ถ่าน|เครื่องปั่นไฟ"), ("sandbags", r"กระสอบทราย|ถุงทราย|sandbag"),
         ("boat", r"เรือ|เจ็ตสกี|ชูชีพ|boat")]
QTY = re.compile(r"(\d[\d,]*)\s*(แพ็ค|แพค|ลัง|โหล|ขวด|กล่อง|ชุด|ถุง|ชิ้น|ลำ|ตัว|กิโล|กก\.?|packs?|boxes?)", re.I)
CASE_ID = re.compile(r"\bC-[0-9A-F]{6}\b", re.I)

R = {
    "emergency": re.compile(r"(?<!รถ)(?<!รถยนต์)(?<!มอไซค์)(?<!บ้าน)จมน้ำ(?!.{0,6}(?:รถ|บ้าน|ของ))|หมดสติ|ไม่หายใจ|หายใจไม่ออก|ชัก|เลือดออกมาก|เลือดไม่หยุด|จะคลอด|น้ำคร่ำ|ถูกไฟดูด|ไฟช็อต|ถูกงูกัด|"
                           r"กำลังจะตาย|ช่วยด่วนที่สุด|drowning|unconscious|not breathing"),
    "donate": re.compile(r"บริจาค|อยากส่งของ|จะเอาของไป|เอาไปวาง|ไปวางไว้|ไปไว้(?:ที่)?ไหน|ไปส่ง(?:ที่)?ไหน|ส่ง(?:ไป)?ที่ไหนดี|"
                         r"(?:มี|ได้)[^ขอ\n]{0,25}\d+\s*(?:แพ็ค|แพค|ลัง|โหล|กล่อง|ชุด|ถุง)|อยากให้ของ|donate", re.I),
    "volunteer": re.compile(r"อาสา|อยากช่วย|ไปช่วยได้|มีเรือ|มีรถยกสูง|มีเจ็ตสกี|ช่วยขนของ|ลงพื้นที่|volunteer", re.I),
    "find_shelter": re.compile(r"ศูนย์พักพิง|ศูนย์อพยพ|ที่พักชั่วคราว|อพยพไป(?:ที่)?ไหน|นอนที่ไหน|ที่พักพิง|shelter", re.I),
    "find_distribution": re.compile(r"(?:รับ|แจก)(?:ของ|ข้าว|อาหาร|ถุงยังชีพ|น้ำ).{0,15}(?:ที่ไหน|ตรงไหน|จุดไหน)|จุดแจก|ไปรับ(?:ของ|ข้าว)", re.I),
    "find_medical": re.compile(r"หมอ|โรงพยาบาล|ปฐมพยาบาล|ทำแผล|หน่วยแพทย์|clinic|hospital", re.I),
    "needs_overview": re.compile(r"(?:ที่ไหน|พื้นที่ไหน|ตรงไหน|จุดไหน).{0,12}(?:ขาด|ต้องการ|ยังไม่มี)|ขาดอะไร|ต้องการอะไรบ้าง", re.I),
    "request_help": re.compile(r"ช่วยด้วย|ขอความช่วยเหลือ|ติดอยู่|ติดค้าง|ออกไม่ได้|ขอเรือ|มารับ|น้ำ(?:ถึง|ท่วม|ขึ้น)|ไม่มี(?:อะไร)?กิน|"
                               r"ติดเตียง|ฟอกไต|ผู้ป่วย|แจ้งแทน|help me|rescue", re.I),
    "safe_now": re.compile(r"ปลอดภัยแล้ว|ไม่ต้องมา(?:แล้ว|รับ)?|ออกมาได้แล้ว|ได้รับการช่วยเหลือแล้ว|มีคน(?:มา)?(?:รับ|ช่วย)แล้ว|"
                           r"(?:อพยพ|ย้าย)(?:ออกมา|ไป)?(?:ได้)?แล้ว|ยกเลิก(?:เคส|คำขอ)?|ทีมมาถึงแล้ว"),
    "my_status": re.compile(r"ถึงไหนแล้ว|สถานะ|(?:ทีม|เรือ|คน)(?:จะ)?(?:มา)?(?:ถึง)?(?:ยัง|หรือยัง|เมื่อไหร่|กี่โมง)|เมื่อไหร่จะมา|มายัง|"
                            r"เคส(?:ของ)?(?:ฉัน|ผม|หนู|เรา)|รอนาน|ยังไม่มีใครมา|ใครรับเคส"),
    "new_case": re.compile(r"อีกบ้าน|บ้านอื่น|แจ้งใหม่|อีกเคส|เคสใหม่|อีกครอบครัว|บ้านข้าง ?ๆ?|อีกหลัง"),
    "thanks": re.compile(r"^(?:ขอบคุณ|ขอบใจ|thank|ok|โอเค|รับทราบ)", re.I),
    "greeting": re.compile(r"^(?:สวัสดี|หวัดดี|hello|hi|ทำอะไรได้บ้าง|เมนู|ช่วยอะไรได้บ้าง)", re.I),
}


def slots(text: str, lat=None, lng=None) -> dict:
    items = [k for k, rx in ITEMS if re.search(rx, text, re.I)]
    q = QTY.search(text)
    loc = extract_location(text)
    if loc["precision"] == "exact":
        lat, lng = loc["lat"], loc["lng"]
    return {"items": items, "qty": int(q.group(1).replace(",", "")) if q else None, "unit": q.group(2) if q else None,
            "area": normalize_area(text), "lat": lat, "lng": lng, "case_id": (CASE_ID.search(text).group(0).upper() if CASE_ID.search(text) else None)}


def rule_intent(text: str) -> tuple[str | None, float]:
    t = text.strip()
    if CASE_ID.search(t):
        return "case_status", 0.95
    if R["greeting"].search(t) and len(t) < 30:
        return "greeting", 0.9
    if R["thanks"].search(t) and len(t) < 25:
        return "thanks", 0.9
    if R["emergency"].search(t):
        return "emergency", 0.9
    if R["safe_now"].search(t) and not re.search(r"ยังไม่ปลอดภัย|ไม่ปลอดภัย", t):
        return "safe_now", 0.8
    if R["my_status"].search(t):
        return "my_status", 0.8
    if R["donate"].search(t) and not re.search(r"^ขอ|ขอ(?:น้ำ|อาหาร|นม|ยา|ของ)|ต้องการ(?:น้ำ|อาหาร)", t):
        return "donate", 0.85
    if R["volunteer"].search(t) and not R["request_help"].search(t):
        return "volunteer", 0.8
    for name in ("find_shelter", "find_distribution", "needs_overview", "find_medical"):
        if R[name].search(t):
            return name, 0.75
    if R["request_help"].search(t):
        return "request_help", 0.7
    if re.search(r"\?|อย่างไร|ยังไง|ทำไง|ไหม|อะไร|ควร|เบอร์", t):
        return "info", 0.5
    return None, 0.0


LLM_SYSTEM = """จัดประเภทข้อความที่ผู้ใช้พิมพ์ถึงแชทบอทช่วยเหลือผู้ประสบภัยน้ำท่วม ตอบ JSON {"intent": ..., "confidence": 0-1}
intent ต้องเป็นหนึ่งใน:
emergency = มีคนอยู่ในอันตรายถึงชีวิตตอนนี้ (จมน้ำ หมดสติ บาดเจ็บหนัก จะคลอด)
request_help = ผู้ประสบภัย/ญาติ ขอความช่วยเหลือ อพยพ อาหาร ยา
donate = มีของจะบริจาค ถามว่าควรส่งที่ไหน
volunteer = อยากเป็นอาสา มีเรือ/รถ/แรงงานจะไปช่วย
find_shelter = ถามหาศูนย์พักพิง/ที่อพยพ
find_distribution = ผู้ประสบภัยถามว่าไปรับของ/อาหารได้ที่ไหน
find_medical = ถามหาหน่วยแพทย์/ปฐมพยาบาล
case_status = ถามสถานะเคสโดยบอกเลขเคส
my_status = ถามความคืบหน้าเคสของตัวเอง ("ทีมมายัง" "ถึงไหนแล้ว") ไม่มีเลขเคส
safe_now = บอกว่าปลอดภัยแล้ว/ไม่ต้องมาแล้ว/มีคนมารับแล้ว
thanks = ขอบคุณ/รับทราบ
needs_overview = ถามว่าพื้นที่ไหนขาดอะไร
info = คำถามความรู้ทั่วไป (เบอร์โทร วิธีเตรียมตัว ความปลอดภัย สุขภาพ)
greeting = ทักทาย"""


def understand(text: str, lat=None, lng=None, llm_json=None) -> dict:
    intent, conf = rule_intent(text)
    source = "rules"
    if (intent is None or conf < 0.6) and llm_json is not None:
        try:
            r = llm_json(LLM_SYSTEM, text)
            if r.get("intent") in INTENTS:
                intent, conf, source = r["intent"], float(r.get("confidence", 0.7)), "llm"
        except Exception:
            pass
    return {"intent": intent or "info", "confidence": conf, "source": source, **slots(text, lat, lng)}


# a message that carries case details (used to add information to the case this chat already created)
INFO_CUES = re.compile(r"0\d[\d\s-]{7,}|บ้านเลขที่|เลขที่|ซ\.|ซอย|ถ\.|ถนน|หมู่|ใกล้|ตรงข้าม|หลัง(?!คา)|ข้าง|พิกัด|maps|\d+\.\d{3,}\s*,|"
                       r"เข่า|เอว|อก|ชั้น|หลังคา|ผู้ใหญ่|เด็ก|ขวบ|อายุ|\d+\s*คน|ติดเตียง|ฟอกไต|ป่วย|ตั้งครรภ์|ท้อง|บาดเจ็บ|"
                       r"แบต|เรือ|อาหาร|น้ำดื่ม|นม|ยา(?!ย)|ติดต่อ|โทร|เบอร์|ตำแหน่ง")


def looks_like_info(text: str) -> bool:
    return bool(INFO_CUES.search(text))

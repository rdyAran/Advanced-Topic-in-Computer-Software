"""Deterministic rules on top of LLM extraction.

Design choice: the LLM only *extracts facts*; the colour is computed here by fixed,
auditable rules (aligned with the red/orange/yellow/green scheme used by ปภ.).
Officers can always see *why* a case got its colour, and can override it.
"""
import re
from floodcommon.schemas import Extraction, Flag, WaterLevel

WATER_SEVERITY = {WaterLevel.knee: 0, WaterLevel.waist: 1, WaterLevel.chest: 2,
                  WaterLevel.floor1: 3, WaterLevel.floor2: 4, WaterLevel.roof: 5}
PRIORITY_RANK = {"red": 0, "orange": 1, "yellow": 2, "green": 3}
REQUIRED_FIELDS = ["area", "people_count", "water_level", "contact"]

# Approximate area centroids in Hat Yai (demo gazetteer). Extend with real data later.
GAZETTEER = {
    "เขต 8 หาดใหญ่": (7.0040, 100.4790, ["เขต8", "เขต 8", "zone8", "khet8"]),
    "คอหงส์": (7.0080, 100.4980, ["คอหงส์", "สังทิศ", "ม.อ.", "khohong", "kohong"]),
    "ถนนครูจีน": (7.0150, 100.4620, ["ครูจีน", "พฤกษาวิว", "kruchin", "khruchin"]),
    "ถนนเพชรเกษม": (7.0010, 100.4700, ["เพชรเกษม", "กอบกาญจน์", "กอบการ", "phetkasem", "petchkasem"]),
    "คลองแห": (7.0300, 100.4850, ["คลองแห", "khlonghae", "klonghae"]),
    "คลองเตย หาดใหญ่": (6.9950, 100.4830, ["คลองเตย", "ร.1", "ราษฎร์อุทิศ", "khlongtoei"]),
    "บ้านพรุ": (6.9550, 100.4780, ["บ้านพรุ", "กาญจนวนิช", "แม็คโคร", "banphru"]),
    "ควนลัง": (7.0050, 100.4350, ["ควนลัง", "khuanlang"]),
    "ทุ่งเสา": (6.9900, 100.4400, ["ทุ่งเสา", "อู่ตะเภา", "thungsao"]),
    "น้ำน้อย": (7.0400, 100.4600, ["น้ำน้อย", "namnoi"]),
}


def normalize_area(*texts: str | None) -> str | None:
    blob = "".join(t for t in texts if t).replace(" ", "").lower()
    for name, (_, _, aliases) in GAZETTEER.items():
        if any(a.replace(" ", "") in blob for a in aliases):
            return name
    return None


def geocode(area: str | None):
    if area in GAZETTEER:
        lat, lng, _ = GAZETTEER[area]
        return lat, lng
    return None, None


def _rule_priority(e: Extraction) -> tuple[str, str]:
    f = set(e.flags)
    sev = WATER_SEVERITY.get(e.water_level, -1) if e.water_level else -1
    if Flag.dialysis in f: return "red", "ผู้ป่วยฟอกไต"
    if Flag.heart in f: return "red", "ผู้ป่วยโรคหัวใจ"
    if Flag.injured in f: return "red", "มีผู้บาดเจ็บ"
    if Flag.in_labor in f: return "red", "กำลังจะคลอด"
    if Flag.sick_now in f: return "red", "มีผู้ป่วยอาการหนักตอนนี้"
    if any(a < 1 for a in e.children_ages): return "red", "ทารกอายุต่ำกว่า 1 ปี"
    if sev >= 5: return "red", "อยู่บนหลังคา / น้ำจะมิดหลังคา"
    floors = getattr(e, "building_floors", None)
    if floors == 1 and sev >= 2: return "red", "บ้านชั้นเดียว น้ำถึงอก/มิดชั้น 1 — ไม่มีชั้นบนให้หนี"
    if Flag.bedridden in f and sev >= 4: return "red", "ผู้ป่วยติดเตียง + น้ำถึงชั้น 2/หลังคา"
    if Flag.pregnant in f and sev >= 3: return "red", "หญิงตั้งครรภ์ + น้ำท่วมมิดชั้น 1 ขึ้นไป"
    if Flag.bedridden in f: return "orange", "ผู้ป่วยติดเตียง"
    if floors == 1 and sev >= 1: return "orange", "บ้านชั้นเดียว น้ำถึงเอว — ถ้าน้ำขึ้นอีกจะไม่มีที่หนี"
    if f & {Flag.disabled_blind, Flag.wheelchair, Flag.pregnant}: return "orange", "ผู้พิการ/เดินลำบาก/หญิงตั้งครรภ์"
    if any(a >= 70 for a in e.elderly_ages): return "orange", "ผู้สูงอายุ 70+"
    if any(a < 6 for a in e.children_ages): return "orange", "เด็กเล็กต่ำกว่า 6 ปี"
    total = people_total(e) or 0
    kids_no_age = bool(getattr(e, "children_count", None)) and not e.children_ages
    old_no_age = bool(getattr(e, "elderly_count", None)) and not e.elderly_ages
    if total >= 10 and sev >= 1: return "orange", f"คนจำนวนมาก ({total} คน) + น้ำถึงเอวขึ้นไป — ต้องใช้เรือหลายรอบ"
    if kids_no_age and sev >= 2: return "orange", "มีเด็ก (ไม่ทราบอายุ) + น้ำถึงอกขึ้นไป"
    if old_no_age and sev >= 2: return "orange", "มีผู้สูงอายุ (ไม่ทราบอายุ) + น้ำถึงอกขึ้นไป"
    if (e.days_trapped or 0) >= 4: return "orange", f"ติดค้างนาน {e.days_trapped} วัน"
    if sev >= 4: return "orange", "น้ำถึงชั้น 2"
    if e.lost_contact and (e.elderly_ages or e.children_ages or f): return "orange", "ขาดการติดต่อ + มีกลุ่มเปราะบาง"
    if kids_no_age or old_no_age: return "yellow", "มีเด็กหรือผู้สูงอายุ (ไม่ทราบอายุ)"
    if sev >= 2 or (e.days_trapped or 0) >= 2 or {"food", "water", "medicine"} & {n.value for n in e.needs}:
        return "yellow", "ติดค้าง/ขาดอาหาร น้ำ หรือยา"
    if e.lost_contact: return "yellow", "ขาดการติดต่อ"
    return "green", "ต้องการสิ่งของ ไม่เร่งด่วน"


def priority(e: Extraction) -> tuple[str, str]:
    """Colour by fixed rules on the extracted facts; our own model may only make it MORE urgent (priority_hint),
    and the reason then says so, so an officer always sees why."""
    color, reason = _rule_priority(e)
    hint = e.priority_hint
    if hint in PRIORITY_RANK and PRIORITY_RANK[hint] < PRIORITY_RANK[color]:
        return hint, "AI: " + (e.priority_hint_reason or "โมเดลประเมินจากข้อความ")
    return color, reason


def nearest_area(lat, lng, max_km: float = 6.0) -> str | None:
    """Area name for a GPS point (closest gazetteer centre within max_km) — so a pin from a map link gets an area."""
    if lat is None or lng is None:
        return None
    import math
    best, dist = None, max_km
    for name, (a_lat, a_lng, _) in GAZETTEER.items():
        d = 111.2 * math.hypot(lat - a_lat, (lng - a_lng) * math.cos(math.radians(lat)))
        if d < dist:
            best, dist = name, d
    return best


def people_total(x) -> int | None:
    """Everyone in the house: adults (which include the elderly) + children. Counts ("เด็ก 12") and listed ages both count."""
    g = (lambda k: x.get(k)) if isinstance(x, dict) else (lambda k: getattr(x, k, None))
    kids = max(len(g("children_ages") or []), g("children_count") or 0)
    adults = g("adults")
    if adults is None:
        adults = max(len(g("elderly_ages") or []), g("elderly_count") or 0)
    total = (adults or 0) + kids
    return total or None


def missing_fields(e: Extraction, has_location: bool = False) -> list[str]:
    """has_location: the message carried GPS coordinates or a Google Maps link — that IS the location."""
    have = {
        "area": bool(e.area) or has_location,
        "people_count": e.adults is not None or bool(people_total(e)),
        "water_level": e.water_level is not None,
        "contact": bool(e.contact),
    }
    return [k for k in REQUIRED_FIELDS if not have[k]]


FOLLOWUP_QUESTIONS = {
    "area": "ช่วยบอกตำแหน่งเพิ่ม เช่น ซอย ถนน หรือจุดสังเกตใกล้บ้าน (หรือส่งพิกัดจาก Google Maps)",
    "people_count": "ในบ้านมีกี่คน มีผู้สูงอายุ เด็ก หรือผู้ป่วยไหม",
    "water_level": "ตอนนี้น้ำสูงระดับไหน (เข่า/เอว/อก/ชั้น 1/ชั้น 2/หลังคา)",
    "contact": "ขอเบอร์ติดต่อกลับ และแบตโทรศัพท์เหลือประมาณเท่าไหร่",
}


def followup_message(missing: list[str]) -> str | None:
    if not missing:
        return None
    return "ได้รับเรื่องแล้ว เพื่อให้ทีมไปถึงเร็วขึ้น รบกวนตอบเพิ่ม:\n" + "\n".join(f"- {FOLLOWUP_QUESTIONS[m]}" for m in missing)


_EMPTY_FIELD = re.compile(r"^\s*[^:：\n]{1,40}[:：]\s*(?:\(\s*แบตเหลือ\s*%?\s*\)|วัน|%|-|ผู้ใหญ่\s*เด็ก\s*ผู้สูงอายุ)?\s*$")


def clean_form_text(text: str) -> str:
    """Drop the blank lines of the web-form template ('เบอร์ติดต่อ: (แบตเหลือ %)', 'ติดมาแล้ว: วัน') before the AI reads
    the message — they are not information and make the model less sure. The original text is stored unchanged."""
    lines = [re.sub(r"\(\s*แบตเหลือ\s*%\s*\)", "", l) for l in (text or "").split("\n")]
    out = [l for l in lines if not _EMPTY_FIELD.match(l)]
    return "\n".join(out).strip() or text


_FORM_WATER = [(r"หลังคา", WaterLevel.roof), (r"ถึงชั้น\s*2\s*แล้ว|ท่วมชั้น\s*2(?!\S*ยังไม่)", WaterLevel.floor2),
               (r"มิดชั้น\s*1|ชั้นล่าง|ท่วมชั้น\s*1", WaterLevel.floor1), (r"อก", WaterLevel.chest), (r"เอว", WaterLevel.waist),
               (r"เข่า", WaterLevel.knee)]


def form_water(text: str):
    """The water level picked on the web form ("ระดับน้ำ: น้ำมิดชั้น 1 ยังไม่ถึงชั้น 2") is an explicit answer — read it
    with fixed rules so "ยังไม่ถึงชั้น 2" is never taken as floor 2. None when the message has no such line."""
    m = re.search(r"^\s*ระดับน้ำ\s*[:：]\s*(.+)$", text or "", re.M)
    if not m:
        return None
    for rx, level in _FORM_WATER:
        if re.search(rx, m.group(1)):
            return level
    return None

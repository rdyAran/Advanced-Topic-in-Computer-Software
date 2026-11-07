"""Text normalisation + entity extraction (numbers, ages, people, contact, place).

The ML model (model.py) decides *categories* (message type, water level, flags, needs);
this module pulls out *values*. Handles Thai number words ("แปดสิบห้า" -> 85), English, typos.
"""
import re

_D = {"หนึ่ง": 1, "เอ็ด": 1, "สอง": 2, "ยี่": 2, "สาม": 3, "สี่": 4, "ห้า": 5, "หก": 6, "เจ็ด": 7, "แปด": 8, "เก้า": 9}
_UNIT_AFTER = r"(?=\s|$|,|คน|ขวบ|เดือน|วัน|ปี|คืน|อาทิตย์|สัปดาห์|ชีวิต|ลำ|ทั้งคู่)"
_NUMWORD = re.compile(r"(?:(หนึ่ง|สอง|ยี่|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า)?สิบ(เอ็ด|สอง|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า)?|(หนึ่ง|สอง|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า))" + _UNIT_AFTER)


def _numword(m: re.Match) -> str:
    tens, unit, single = m.group(1), m.group(2), m.group(3)
    if single:
        return str(_D[single])
    return str((_D[tens] if tens else 1) * 10 + (_D[unit] if unit else 0))


def normalize(text: str) -> str:
    t = text.replace("นำ้", "น้ำ").replace("ชวย", "ช่วย").replace("ม่าย", "ไม่")
    t = re.sub(r"([\u0E00-\u0E7F])\1{2,}", r"\1", t)   # ด่วนนนน -> ด่วน (Thai only; keeps 08x-xxx-1234)
    t = _NUMWORD.sub(_numword, t)               # ห้าคน -> 5คน, เก้าสิบ -> 90
    return t


CHILD_WORDS = r"(?:เด็ก|ลูก|หลาน|ทารก|baby|kid|น้อง|เพิ่งคลอด|คลอดได้|เพิ่งเกิด|newborn)"
OLD_KIN = r"(?:อายุ|ยาย|ตา|ปู่|ย่า|แม่|พ่อ|ลุง|ป้า|น้า|คนแก่|grandma|grandpa|grandmother|grandfather)"


def _ages(t: str):
    kids, olds, used = [], [], set()
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(ขวบ|เดือน|months?|อาทิตย์|สัปดาห์|weeks?|days? old|วัน|years? old|yo|y/o|ปี)", t):
        n, unit = float(m.group(1)), m.group(2)
        before = t[max(0, m.start() - 14):m.start()]
        if re.search(r"ท้อง|ครรภ์|pregnant", before):        # "ท้อง 8 เดือน" = pregnancy, not a baby
            used.add(m.start()); continue
        if unit in ("ขวบ",) or (unit.startswith("year") and n < 15) or (unit in ("ปี", "yo", "y/o") and n < 15 and re.search(CHILD_WORDS, before)):
            kids.append(n); used.add(m.start())
        elif unit in ("เดือน", "month", "months") and (re.search(CHILD_WORDS, before) or n < 12):
            kids.append(round(n / 12, 2)); used.add(m.start())
        elif unit in ("อาทิตย์", "สัปดาห์", "week", "weeks"):
            if re.search(CHILD_WORDS, before):
                kids.append(round(n / 52, 2)); used.add(m.start())
        elif unit in ("วัน", "day old", "days old"):          # "ลูกเพิ่งเกิดได้ 10 วัน" (but not "ติดมา 3 วัน")
            if re.search(r"เกิด|คลอด|ทารก|newborn|ลูกอ่อน", before) and n <= 60:
                kids.append(round(n / 365, 2)); used.add(m.start())
        elif n >= 60:
            olds.append(int(n)); used.add(m.start())
    for m in re.finditer(OLD_KIN + r"\s*(\d{2})(?!\d)", t):    # "ยายอายุ 85", "ตา90"
        if m.start(1) not in used and int(m.group(1)) >= 60:
            olds.append(int(m.group(1))); used.add(m.start(1))
    if not kids and re.search(r"แรกเกิด|เพิ่งคลอด|newborn", t):
        kids.append(0.05)
    return sorted(kids), sorted(set(olds))


_NOT_AGE = r"(?!\s*(?:ขวบ|เดือน|ปี|วัน|อาทิตย์|สัปดาห์|weeks?|months?|years?|yo|\d|\.\d))"
KID_COUNT = re.compile(r"(?:เด็ก(?:เล็ก)?|ลูก|หลาน)\s*(\d{1,3})\s*(คน)?" + _NOT_AGE)
OLD_COUNT = re.compile(r"(?:ผู้สูงอายุ|ผู้สูงวัย|คนแก่|คนชรา)\s*(\d{1,2})\s*(คน)?" + _NOT_AGE)
PEOPLE_LINE = re.compile(r"จำนวนคน|ผู้ใหญ่\s*\d|ผู้สูงอายุ\s*\d{1,2}(?!\d)|เด็ก\s*\d+\s*คน")


def _counts(t: str):
    """'เด็ก 12 ผู้สูงอายุ 5' (a head count, e.g. from the web form) vs 'เด็ก 5 ขวบ' (an age).
    A bare number counts as people only with 'คน', or on a line that is clearly a head count, or when it is too big to be an age."""
    kids = olds = None
    for line in t.split("\n"):
        ctx = bool(PEOPLE_LINE.search(line))
        for m in KID_COUNT.finditer(line):
            n = int(m.group(1))
            if m.group(2) or ctx or n > 15:
                kids = (kids or 0) + n
        for m in OLD_COUNT.finditer(line):
            n = int(m.group(1))
            if n < 60 and (m.group(2) or ctx):
                olds = (olds or 0) + n
    return kids, olds


_FLOOR_WORD = {"หนึ่ง": 1, "เดียว": 1, "สอง": 2, "สาม": 3, "สี่": 4, "ห้า": 5}
BUILDING = re.compile(r"(?:บ้าน|ตึก|อาคาร|ทาวน์เฮาส์|ทาวน์โฮม|ตึกแถว|หอพัก|อพาร์ท\S*|ห้องแถว|ที่พัก[:：]?)\s*\S{0,8}?\s*"
                      r"(\d{1,2}|หนึ่ง|เดียว|สอง|สาม|สี่|ห้า)\s*ชั้น|(?:บ้าน)?ชั้นเดียว")
HIGH_RISE = re.compile(r"คอนโด|อาคารสูง|แฟลต|ตึกสูง")


def building_floors(t: str) -> int | None:
    """How many floors the place has: 'บ้านชั้นเดียว' -> 1, 'บ้าน 2 ชั้น' -> 2, 'ตึก 4 ชั้น'/'คอนโด' -> 3 (= 3 or more).
    'น้ำถึงชั้น 2' is the WATER level, not the building — a building word must come first."""
    m = BUILDING.search(t)
    if m:
        if m.group(1) is None:
            return 1
        n = _FLOOR_WORD.get(m.group(1)) or int(m.group(1))
        return min(n, 3) if n else None
    if HIGH_RISE.search(t):
        return 3
    return None


def extract_entities(text: str) -> dict:
    t = normalize(text)
    kids, olds = _ages(t)
    kid_count, old_count = _counts(t)
    adults = None
    m = re.search(r"ผู้ใหญ่\s*(\d+)", t)
    if m:
        adults = int(m.group(1)) + (old_count or 0)      # adults include the elderly (schema)
    else:
        m = re.search(r"(?:อยู่กัน|รวม|มี|บ้านมี|ในบ้านมี|พวกเรา|ทั้งหมด)\s*(\d+)\s*(?:คน|ชีวิต)", t) or re.search(r"(\d+)\s*(?:คน|ชีวิต|people|persons)(?!ละ)", t)
        if m:
            kid_n = max(len(kids), kid_count or 0)
            adults = max(int(m.group(1)) - kid_n, len(olds)) or None   # "มีเด็ก 3 คน" is 3 children, not 3 adults
        elif re.search(r"อยู่(?:บ้าน)?คนเดียว|alone", t):
            adults = 1
        elif old_count:
            adults = old_count
        elif len(olds) >= 2:            # "ตา 74 ยาย 71" with no head-count -> at least these adults
            adults = len(olds)
    days = None
    m = re.search(r"(?:ติด(?:มา|อยู่)?|มา)\s*(\d+)\s*(?:วัน|คืน)", t) or re.search(r"(\d+)\s*(?:วัน|คืน)แล้ว", t)
    if m:
        days = int(m.group(1))
    elif "เมื่อวานซืน" in t:
        days = 2
    elif re.search(r"ตั้งแต่เมื่อวาน|since yesterday", t):
        days = 1
    c = re.search(r"0\d[\dx]{1,2}[-\s]?[\dx]{3}[-\s]?[\dx]{3,4}", t)
    h = re.search(r"(?:บ้านเลขที่|เลขที่)\s*(\d+(?:/\d+)?)", t)
    s = re.search(r"(ซ\.\s?[^\s,]+(?:\s\d+)?|ซอย\s?[^\s,]+(?:\s\d+)?|ถ\.\s?[^\s,]+|ถนน[^\s,]+|soi\s?\d+)", t)
    return {"adults": adults, "children_ages": kids, "elderly_ages": olds, "days_trapped": days,
            "children_count": kid_count, "elderly_count": old_count, "building_floors": building_floors(t),
            "contact": c.group(0) if c else None, "house_no": h.group(1) if h else None,
            "street": s.group(1) if s else None}

"""Domain knowledge layer: synonym groups -> concept tags, and negation marking.

Why: a character n-gram model only knows phrasings it has seen. Medical/flood synonyms
(อัมพฤกษ์ ≈ ติดเตียง, ไตวาย ≈ ฟอกไต, ตาตุ่ม ≈ น้ำตื้น) are added as explicit concept tags, so
one training example of "[[BEDRIDDEN]]" generalises to every synonym in the group.
Negations ("อาหารยังพอ", "ไม่มีใครป่วย") are rewritten to NEG tags so they stop looking like needs.

Rule for editing: add general Thai/English synonyms from domain knowledge. Never copy phrases
from the held-out test set (05_evaluation/data/hard_messages.jsonl).
"""
import re

CONCEPTS = {
    "BEDRIDDEN": ["ติดเตียง", "อัมพาต", "อัมพฤกษ์", "ลุกไม่ขึ้น", "ลุกจากเตียงไม่ได้", "นอนป่วย", "พลิกตัว", "เส้นเลือดในสมอง",
                  "stroke", "bedridden", "ผู้ป่วยนอนเตียง", "นอนให้อาหารทางสายยาง", "สายยาง"],
    "DIALYSIS": ["ฟอกไต", "ฟอกเลือด", "ไตวาย", "ไตเสื่อม", "โรคไต", "ป่วยไต", "dialysis", "kidney"],
    "HEART": ["หัวใจ", "บายพาส", "เจ็บหน้าอก", "แน่นหน้าอก", "heart"],
    "PREGNANT": ["ตั้งครรภ์", "คนท้อง", "ท้องแก่", "ใกล้คลอด", "เจ็บท้องคลอด", "น้ำคร่ำ", "ครรภ์", "pregnant"],
    "INJURED": ["บาดเจ็บ", "บาด", "เลือดออก", "เลือดไหล", "แผล", "กระดูกหัก", "ขาหัก", "แขนหัก", "หัก", "ซี่โครง", "หัวแตก", "หัวฟาด",
                "ไฟดูด", "ไฟช็อต", "ตะปูตำ", "จมน้ำ", "หมดสติ", "ซึม", "injured", "bleeding", "broken"],
    "BLIND": ["ตาบอด", "พิการทางสายตา", "สายตาพิการ", "blind"],
    "WHEELCHAIR": ["วีลแชร์", "รถเข็น", "เดินไม่ได้", "เดินเองไม่ได้", "ขาพิการ", "พิการแขนขา", "ขาลีบ", "ขยับไม่ได้", "wheelchair"],
    "NEED_FOOD": ["อาหาร", "ข้าว", "มาม่า", "บะหมี่", "ของกิน", "อะไรกิน", "หิว", "food"],
    "NEED_WATER": ["น้ำดื่ม", "น้ำกิน", "น้ำเปล่า", "ขวดน้ำ", "drinking water"],
    "NEED_MILK": ["นมเด็ก", "นมผง", "นมกล่อง", "นมสูตร", "นมหมด", "นมให้", "นมสำหรับ", "นมแม่", "ขาดนม", "ขอนม", "ไม่มีนม", "milk", "formula"],
    "NEED_MED": ["ยาหมด", "ยาเหลือ", "ยาใกล้หมด", "ขอยา", "ไม่มียา", "ยาประจำตัว", "ยาความดัน", "ยาเบาหวาน", "ยาลดไข้", "ยาโรค",
                 "อินซูลิน", "ออกซิเจน", "medicine", "insulin", "oxygen"],
    "NEED_EVAC": ["ขอเรือ", "เรือมา", "ส่งเรือ", "เรือไปรับ", "รอเรือ", "อพยพ", "มารับ", "ไปรับ", "พาออก", "เจ็ตสกี", "boat", "rescue", "evacuate"],
    "NEED_POWER": ["แบต", "ชาร์จ", "ไฟดับ", "มือถือจะดับ", "โทรศัพท์จะดับ", "battery", "power"],
    "W_SHALLOW": ["ตาตุ่ม", "ข้อเท้า", "เข่า", "ankle", "knee"],
    "W_WAIST": ["เอว", "สะโพก", "waist", "hip"],
    "W_CHEST": ["ถึงอก", "หน้าอก", "มิดอก", "ระดับอก", "ถึงคอ", "มิดคอ", "มิดหัว", "chest", "neck"],
    "W_FLOOR1": ["ชั้นล่าง", "ชั้น 1", "ชั้น1", "ชั้นเดียว", "หน้าต่าง", "ground floor", "first floor"],
    "W_FLOOR2": ["ชั้น 2", "ชั้น2", "ชั้นสอง", "ชั้นบน", "second floor", "2nd floor", "upstairs"],
    "W_ROOF": ["หลังคา", "ดาดฟ้า", "roof"],
    "HAZARD": ["ระวัง", "เตือนภัย", "อันตราย", "อย่าเข้า", "อย่าใช้ทาง", "อย่าขับ", "หลีกเลี่ยง", "คันกั้นน้ำ", "รั่ว", "หลุม",
               "สายไฟ", "เสาไฟ", "งู", "จระเข้", "ตะขาบ", "กระแสน้ำแรง", "careful", "warning", "avoid"],
    "RESOLVED": ["ปลอดภัยแล้ว", "รับแล้ว", "รับออกมาแล้ว", "ได้รับความช่วยเหลือแล้ว", "ไม่ต้องแชร์", "ลบโพสต์", "เรียบร้อย",
                 "อยู่ศูนย์อพยพแล้ว", "ถึงโรงพยาบาลแล้ว", "คลอดเรียบร้อย", "คลอดที่โรงพยาบาล", "ขอบคุณทีม", "rescued", "safe now"],
    "OFFER": ["ให้ยืม", "แจก", "บริจาค", "พร้อมไปช่วย", "พร้อมลงพื้นที่", "ทักมา", "ติดต่อได้ที่", "ขอเป็นอาสา", "มีเรือพาย", "มีเรือยาง", "รถยกสูงว่าง", "เรือว่าง",
              "ใครต้องการ", "ใครขาด", "donate", "volunteer"],
    "CHATTER": ["สู้ๆ", "เป็นกำลังใจ", "สงสาร", "ขอให้ปลอดภัย", "ขอให้น้ำลด", "ไม่มีใครแก้", "ทุกปี", "ดูไลฟ์", "ดูข่าว", "แชร์เยอะ",
                "หน่วยงานไปไหน", "stay safe"],
}

# negations: (pattern) -> tag.  Run BEFORE concept tagging so "อาหารยังพอ" doesn't also fire NEED_FOOD.
NEGATIONS = [
    (r"(?:อาหาร|ข้าว|ของกิน)\s*(?:ยัง)?\s*(?:มี)?\s*(?:พอ|เหลือเยอะ|เพียงพอ)", " NEG_FOOD "),
    (r"(?:มี)?(?:อาหาร|ข้าว|ของกิน)(?:ยัง)?(?:มี)?พอ", " NEG_FOOD "),
    (r"น้ำ(?:ดื่ม|กิน)\s*(?:ยัง)?\s*(?:มี)?\s*พอ", " NEG_WATER "),
    (r"ไม่(?:ต้องการ|ขาด)\s*(?:อาหาร|ข้าว)", " NEG_FOOD "),
    (r"ไม่มี(?:ใคร|คน)?(?:ป่วย|เจ็บ|บาดเจ็บ)|ทุกคน(?:แข็งแรง|ปลอดภัย|โอเค)|no one (?:is )?(?:sick|injured)", " NEG_SICK "),
    (r"ไม่มี(?:คนแก่|ผู้สูงอายุ)", " NEG_OLD "),
    (r"ไม่มีเด็ก", " NEG_KID "),
    (r"(?:ยัง)?ไม่(?:อยาก|ต้อง)(?:อพยพ|ออกจากบ้าน|ย้าย)", " NEG_EVAC "),
]
_NEG = [(re.compile(p), tag) for p, tag in NEGATIONS]


def mark(text: str) -> str:
    """Text for the classifier: negations rewritten + concept tags appended."""
    t = text
    for rx, tag in _NEG:
        t = rx.sub(tag, t)
    low = re.sub(r"NEG_[A-Z]+", " ", t).lower()   # don't let tag names ("NEG_FOOD") match English synonyms
    tags = [f"[[{c}]]" for c, words in CONCEPTS.items() if any(w in low for w in words)]
    return t + " " + " ".join(tags)

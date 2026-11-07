"""Find and hide personal data in text (shared: the agent masks before an external LLM, the API masks training exports).

  masked, vault = mask("ยายติดเตียง บ้านเลขที่ 12/3 โทร 081-234-5678 นายสมชาย ใจดี")
  -> "ยายติดเตียง บ้านเลขที่ [บ้านเลขที่1] โทร [เบอร์1] นาย[ชื่อ1] [นามสกุล1]"      (vault keeps the real values)
"""
import os, re

ENABLED = os.getenv("LLM_MASK_PII", "1") != "0"
KIN = ("ยาย", "ตา", "แม่", "พ่อ", "ป้า", "ลุง", "น้า", "อา", "พี่", "น้อง", "ลูก", "หลาน", "ปู่", "ย่า", "ทวด", "เจ้าหน้าที่",
       "หมอ", "พยาบาล", "ทุกคน", "ครู", "ผู้ใหญ่", "ท่าน")
# order matters: longer / more specific patterns first
PATTERNS = [
    ("ลิงก์แผนที่", re.compile(r"https?://(?:maps\.app\.goo\.gl|goo\.gl/maps|(?:www\.)?google\.[a-z.]+/maps|maps\.google\.[a-z.]+)\S*", re.I)),
    ("ลิงก์", re.compile(r"https?://\S+", re.I)),
    ("อีเมล", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("พิกัด", re.compile(r"-?\d{1,3}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}")),
    ("เลขบัตร", re.compile(r"(?<!\d)\d[\s-]?\d{4}[\s-]?\d{5}[\s-]?\d{2}[\s-]?\d(?!\d)")),
    ("เบอร์", re.compile(r"(?<![\d.])(?:\+66[\s-]?|0)\d{1,2}[\s-]?[\dxX]{3}[\s-]?[\dxX]{3,4}(?![\d.])")),
    ("ไลน์", re.compile(r"((?:line|ไลน์)\s?(?:id)?\s?[:：]?\s?)(@?[A-Za-z0-9._-]{3,30})", re.I)),   # keep the word, mask the id
]
HOUSE = re.compile(r"((?:บ้าน\s*)?เลขที่\s*)(\d+(?:\s*/\s*\d+)?)")
# a name right after a title, up to the next space / punctuation (Thai has no spaces between words, so a title
# followed by a long run of letters, e.g. "คุณยายติดเตียง", is NOT treated as a name — we never cut medical words)
# surname: only after a FORMAL title (นาย/นาง/นางสาว/น.ส.), and never a word that carries case information
SURNAME = re.compile(r" ([ก-๙]{2,20})(?=[\s,.)\]]|$)")
CASE_WORDS = re.compile(r"ติด|ป่วย|เตียง|ไต|หัวใจ|ท้อง|ครรภ์|เจ็บ|พิการ|อายุ|ขวบ|ปี|โทร|เบอร์|บ้าน|น้ำ|ขอ|ด่วน|ช่วย|ต้องการ|อยู่|ซอย|ถนน|หมู่|"
                        r"เรือ|อาหาร|ยา|นม|แบต|ไฟ|ชั้น|หลังคา|เอว|อก|เข่า|คน|เด็ก|ยาย|ตา|แม่|พ่อ|ลูก|หลาน|และ|กับ|ค่ะ|ครับ|คะ|นะ")
FORMAL = ("นาย", "นาง", "นางสาว", "น.ส.")
NAME = re.compile(r"((?:นางสาว|น\.ส\.|นาย|นาง|ด\.ช\.|ด\.ญ\.|เด็กชาย|เด็กหญิง|คุณ|ชื่อ)\s?)([ก-๙A-Za-z]{2,15})(?=[\s,.)\]]|$)")


def mask(text: str) -> tuple[str, dict]:
    """-> (masked text, vault {placeholder: original})."""
    if not text:
        return text, {}
    vault, count = {}, {}

    def put(kind, value):
        for k, v in vault.items():                      # same value -> same placeholder (keeps "the same phone twice")
            if v == value and k.startswith(f"[{kind}"):
                return k
        count[kind] = count.get(kind, 0) + 1
        key = f"[{kind}{count[kind]}]"
        vault[key] = value
        return key

    out = text
    for kind, rx in PATTERNS:
        if rx.groups == 2:
            out = rx.sub(lambda m, k=kind: m.group(1) + put(k, m.group(2)), out)
        else:
            out = rx.sub(lambda m, k=kind: put(k, m.group(0)), out)
    out = HOUSE.sub(lambda m: m.group(1) + put("บ้านเลขที่", m.group(2)), out)

    res, pos = [], 0
    for m in NAME.finditer(out):
        word = m.group(2)
        if any(word.startswith(k) for k in KIN):
            continue
        res.append(out[pos:m.start()] + m.group(1) + put("ชื่อ", word)); pos = m.end()
        sm = SURNAME.match(out, pos) if m.group(1).strip() in FORMAL else None
        if sm and not CASE_WORDS.search(sm.group(1)):
            res.append(" " + put("นามสกุล", sm.group(1))); pos = sm.end()
    out = "".join(res) + out[pos:]
    return out, vault


def unmask(value, vault: dict):
    """Put the originals back into a string / list / dict returned by the LLM."""
    if not vault or value is None:
        return value
    if isinstance(value, str):
        for k, v in vault.items():
            value = value.replace(k, v)
        return value
    if isinstance(value, list):
        return [unmask(v, vault) for v in value]
    if isinstance(value, dict):
        return {k: unmask(v, vault) for k, v in value.items()}
    return value


def summary(vault: dict) -> dict:
    """{'เบอร์': 1, 'บ้านเลขที่': 1} — shown in the agent trace ("🔒 ปิดบังก่อนส่ง")."""
    out = {}
    for k in vault:
        kind = re.sub(r"\d+\]$", "", k[1:])
        out[kind] = out.get(kind, 0) + 1
    return out



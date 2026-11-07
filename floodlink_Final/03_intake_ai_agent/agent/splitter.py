"""Split one submitted text into separate cases.

People often paste several requests at once ("1. ... 2. ...", or "บ้านเลขที่ 12 ... อีกบ้าน บ้านเลขที่ 40 ...").
Step 1  rules  : list markers, "เคส 2"/"บ้านที่ 2", lines that each start with their OWN place (บ้านเลขที่ / ซอย /
                 ถนน / พิกัด ...), repeated "บ้านเลขที่"/"อีกบ้าน", blank lines  (fast, no API)
Step 2  LLM    : only when the rules find ONE part but the text still looks like several cases
                 (several house numbers / phone numbers / "อีกบ้าน" ...) and an LLM is available
Shared context : header lines (area, reporter's phone) are copied into parts that don't have their own.
"""
import re
from floodcommon.triage import normalize_area

MAX_CASES = 20
PHONE = re.compile(r"0\d[\dx]{1,2}[-\s]?[\dx]{3}[-\s]?[\dx]{3,4}")
HOUSE = re.compile(r"(?:บ้านเลขที่|เลขที่)\s*\d+")
CASE_SIGNAL = re.compile(r"บ้านเลขที่|ซ\.|ซอย|ถ\.|ถนน|\d+\s*คน|ผู้ใหญ่|เด็ก|ยาย|ตา|ป้า|ลุง|แม่|พ่อ|น้ำถึง|น้ำท่วม|ชั้น|หลังคา|"
                         r"ติดเตียง|ฟอกไต|ท้อง|บาดเจ็บ|ป่วย|อายุ|ขวบ|เดือน|ติดอยู่|ขอเรือ|อพยพ")
# explicit case markers -> always a new case
STRONG_MARK = re.compile(r"(?m)^\s*(?:(?:เคส|case|บ้านที่|บ้านหลังที่|รายที่|จุดที่|ครอบครัวที่)\s*\d+|#\d+)\s*[:.)\-]?", re.I)
# numbered / bulleted lines -> a new case only if the part has its own anchor (else it's a detail list of one case)
LIST_MARK = re.compile(r"(?m)^\s*(?:\d{1,2}\s*[.)]|[-•*]\s)")
INLINE_NEW = re.compile(r"(?=(?:อีก(?:บ้าน|เคส|หลัง|ครอบครัว|จุด)|เคสที่\s*\d|บ้านที่\s*\d|บ้านหลังที่\s*\d))")
MULTI_HINT = re.compile(r"อีก(?:บ้าน|เคส|หลัง|ครอบครัว|จุด)|หลายบ้าน|หลายเคส|เคสที่\s*2|บ้านที่\s*2")
ANCHOR = re.compile(r"บ้านเลขที่|เลขที่\s*\d|ซ\.|ซอย|ถ\.|ถนน|หมู่\s*\d|หมู่บ้าน|\d+\s*(?:คน|ชีวิต)|"
                    r"บ้าน(?:ป้า|ลุง|ยาย|ตา|นาย|นาง|คุณ|พี่|น้า)|soi|" + PHONE.pattern)


# a line that starts with a place ("บ้านเลขที่ 40 ...", "ซ.คลองแห 6 ...", "พิกัด 7.03, 100.48 ...") and says something
# about people / water / needs is a case of its own when its place differs from the case before it
LINE_PLACE = re.compile(r"^\s*(?:[-•*]\s*)?(?:บ้านเลขที่|เลขที่\s*\d|ซ\.|ซอย|ถ\.|ถนน|หมู่บ้าน|ชุมชน|พิกัด|\d{1,4}/\d{1,4}\s)")
CONTENT = re.compile(r"\d+\s*(?:คน|ชีวิต)|ผู้ใหญ่|เด็ก|ยาย|ตา|ป้า|ลุง|แม่|พ่อ|น้ำถึง|น้ำท่วม|น้ำขึ้น|ชั้น|หลังคา|ติดเตียง|ฟอกไต|ท้อง|"
                     r"บาดเจ็บ|ป่วย|อายุ|ขวบ|เดือน|ติดอยู่|ขอเรือ|อพยพ|อาหาร|ทารก|หัวใจ")
SOI = re.compile(r"(?:ซ\.|ซอย)\s*([^\s,()]+(?:\s*\d+(?:/\d+)?)?)")
COORD = re.compile(r"\d{1,2}\.\d{3,}\s*,\s*\d{2,3}\.\d{3,}")


def _place_key(line: str) -> dict:
    h, so, c = HOUSE.search(line), SOI.search(line), COORD.search(line)
    return {"house": re.sub(r"\D", "", h.group(0)) if h else None,
            "soi": re.sub(r"\s+", "", so.group(1)) if so else None, "coord": c.group(0).replace(" ", "") if c else None}


def _other_place(a: dict, b: dict) -> bool:
    """True when two lines clearly name different places (compare what both of them state)."""
    for k in ("house", "soi", "coord"):
        if a[k] and b[k]:
            return a[k] != b[k]
    return False


def _line_parts(text: str):
    lines = text.split("\n")
    starts, keys = [], []
    for i, ln in enumerate(lines):
        if LINE_PLACE.search(ln) and CONTENT.search(ln) and len(ln.strip()) >= 12:
            k = _place_key(ln)
            if any(k.values()) and (not keys or _other_place(keys[-1], k)):
                starts.append(i); keys.append(k)
    if len(starts) < 2:
        return None
    head = "\n".join(lines[:starts[0]])
    parts = ["\n".join(lines[a:b]) for a, b in zip(starts, starts[1:] + [len(lines)])]
    return head, parts


def _new_house_starts(text: str) -> list[int]:
    """Positions of house numbers not seen before ("บ้านเลขที่ 12 ... บ้านเลขที่ 12 แบตจะหมด" is still one house)."""
    seen, out = set(), []
    for m in HOUSE.finditer(text):
        n = re.sub(r"\D", "", m.group(0))
        if n not in seen:
            seen.add(n); out.append(m.start())
    return out


def _signal(s: str) -> bool:
    return bool(CASE_SIGNAL.search(s)) and len(s.strip()) >= 12


def _anchor(s: str) -> bool:
    return bool(ANCHOR.search(s) or normalize_area(s))


def looks_multi(text: str) -> bool:
    return len(set(HOUSE.findall(text))) >= 2 or len(set(PHONE.findall(text))) >= 2 or bool(MULTI_HINT.search(text))


def _cut(text: str, starts: list[int]) -> list[str]:
    return [text[:starts[0]]] + [text[a:b] for a, b in zip(starts, starts[1:] + [len(text)])]


def _glue(parts: list[str], need_anchor: bool) -> list[str]:
    """Attach parts that aren't a case on their own (no content / no anchor) to the previous part."""
    out = []
    for p in parts:
        ok = _signal(p) and (_anchor(p) or not need_anchor)
        if out and not ok:
            out[-1] += " " + p.strip()
        else:
            out.append(p)
    return out


def _rule_parts(text: str) -> tuple[str, list[str], str]:
    strong = list(STRONG_MARK.finditer(text))
    if len(strong) >= 2:
        raw = _cut(text, [m.start() for m in strong])
        return raw[0], _glue([p for p in raw[1:] if p.strip()], need_anchor=False), "marker"
    for name, finder in (("list", lambda: [m.start() for m in LIST_MARK.finditer(text)]),
                         ("inline", lambda: [m.start() for m in INLINE_NEW.finditer(text)]),
                         ("lines", None),
                         ("house_no", lambda: _new_house_starts(text))):
        if name == "lines":
            lp = _line_parts(text)
            if lp:
                return lp[0], lp[1], "lines"
            continue
        starts = finder()
        if len(starts) >= 2 or (name == "inline" and starts):
            raw = _cut(text, starts)
            head, body = raw[0], [p for p in raw[1:] if p.strip()]
            if name in ("inline", "house_no") and _signal(head) and _anchor(head):
                head, body = "", [head] + body          # first case has no marker in front of it
            parts = _glue(body, need_anchor=True)
            if len(parts) >= 2:
                return head, parts, name
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    parts = _glue(paras, need_anchor=True)
    if len(parts) >= 2:
        return "", parts, "paragraph"
    return "", [text], "none"


def _with_context(header: str, parts: list[str]) -> list[str]:
    """Copy shared area / reporter phone from the header into parts that lack them."""
    area = normalize_area(header) if header.strip() else None
    phone = PHONE.search(header).group(0) if header and PHONE.search(header) else None
    out, prev_area = [], area
    for p in parts:
        p = p.strip()
        extra = []
        own = normalize_area(p)
        if not own and prev_area:            # "ซอยเดียวกัน" -> same area as the case before
            extra.append(f"(พื้นที่: {prev_area})")
        prev_area = own or prev_area
        if phone and not PHONE.search(p):
            extra.append(f"(ติดต่อผู้แจ้ง: {phone})")
        out.append(p + (" " + " ".join(extra) if extra else ""))
    return out


def split_cases(text: str, llm=None) -> dict:
    text = (text or "").strip()
    header, parts, method = _rule_parts(text)
    if len(parts) >= 2:
        return {"segments": _with_context(header, parts)[:MAX_CASES], "method": f"rules:{method}",
                "note": f"แยกได้ {len(parts)} เคส"}
    if llm is not None and hasattr(llm, "split_cases") and looks_multi(text):
        try:
            segs = [s.strip() for s in llm.split_cases(text) if s and s.strip()]
            if len(segs) >= 2:
                return {"segments": segs[:MAX_CASES], "method": "llm", "note": f"LLM แยกได้ {len(segs)} เคส"}
        except Exception as e:
            return {"segments": [text], "method": "single", "note": f"อาจมีหลายเคส แต่ LLM แยกไม่สำเร็จ: {str(e)[:120]}"}
    note = "ข้อความนี้อาจมีหลายเคส — ถ้าใช่ ให้ขึ้นบรรทัดใหม่แล้วใส่ 'เคส 1', 'เคส 2' หน้าแต่ละเคส" if looks_multi(text) else None
    return {"segments": [text], "method": "single", "note": note}


SPLIT_PROMPT = """ข้อความด้านล่างอาจมีคำขอความช่วยเหลือน้ำท่วมหลายเคส (หลายบ้าน/หลายครอบครัว/หลายจุด)
แยกออกเป็นเคส เคสละ 1 string โดย:
- คัดลอกข้อความเดิมของแต่ละเคส ห้ามแต่งเพิ่มหรือสรุป
- ถ้ามีข้อมูลร่วม (พื้นที่, เบอร์ผู้แจ้ง) ที่ใช้กับทุกเคส ให้เติมท้ายเคสที่ไม่มี ในวงเล็บ
- ถ้ามีแค่เคสเดียว ให้ตอบ array ที่มี 1 string
ตอบเป็น JSON: {"cases": ["...", "..."]}"""

"""Raw Facebook comment dump (Ctrl+A copy) -> clean, anonymised, de-duplicated CSV ready for labelling.

usage: python prepare.py raw.txt out_dir
Outputs:
  comments_all.csv      every parsed comment (anonymised) + dup group + noise flag
  to_label.csv          one row per duplicate group, chatter removed  -> send to labelling
  report.json           counts for the data-quality report
"""
import csv, json, random, re, sys, unicodedata
from collections import Counter
from pathlib import Path

BADGES = {"แฟนตัวยง", "ผู้ร่วมให้ข้อมูลยอดนิยม", "ผู้ดูแล", "ผู้ดูแลระบบ", "ผู้เขียน", "ผู้สร้างสรรค์เนื้อหา", "ผู้ติดตาม",
          "ผู้สนับสนุนรายใหม่", "ผู้ร่วมให้ข้อมูลที่โดดเด่น", "ผู้ตอบกลับยอดนิยม", "ผู้เชี่ยวชาญ"}
DROP = {"แก้ไขแล้ว", "GIF", "ตอบกลับ", "·", ""}
IMG = "ไม่มีคำอธิบายรูปภาพ"


def parse(raw: str) -> list[dict]:
    raw = raw.replace("\r", "").replace("￼", "")
    out = []
    for block in re.split(r"\n\s*ตอบกลับ\s*\n", "\n" + raw + "\n"):
        lines = [l.rstrip() for l in block.split("\n")]
        while lines and (not lines[0].strip() or lines[0].strip() in DROP or lines[0].strip() == IMG):
            lines.pop(0)                                             # "แก้ไขแล้ว" etc. of the previous comment
        if not lines:
            continue
        author = None
        if len(lines) > 1 and lines[1].strip() == "·":           # "Name\n ·" header
            author, lines = lines[0].strip(), lines[1:]
        has_img, body = False, []
        for l in lines:
            s = l.strip()
            if s == IMG or s.startswith("อาจเป็นรูปภาพ"):
                has_img = True; continue
            if s in DROP or s in BADGES or (not body and s == "·"):
                continue
            body.append(s)
        text = "\n".join(body).strip()
        if text:
            out.append({"author": author, "text": text, "has_image": has_img})
    return out


# ---------------- anonymisation ----------------
rnd = random.Random(42)
PHONE = re.compile(r"(?<!\d)(?:\+?66[\s-]?|0)(?:[689]\d|2)[\s.-]?\d{3}[\s.-]?\d{3,4}(?!\d)|(?<!\d)(?<!\d\.)0\d{8,10}(?!\d)|(?<!\d)(?<!\d\.)0\d(?:[\s.-]?\d){7,9}(?![\d.])")
LATIN_NAME = re.compile(r"\b[A-Z][a-z]{2,}(?:\s[A-Z][a-z]{2,}){1,2}\b")           # FB name tags in text
HOUSE = re.compile(r"((?:บ้าน\s*เลขที่|เลขที่|บ้านเลข|บ\.?\s?ล\.?\s?ท\.?)\s*)(\d{1,4}(?:/\d{1,4})?)")
COORD = re.compile(r"(\d{1,2}\.\d{3,})(\s*°?\s*[NS]?\s*[,.]\s*)(\d{2,3}\.\d{3,})")
DEG = re.compile(r"(?<![\d.])\d{1,3}\.\d{4,}(?![\d.])")
MAPS = re.compile(r"https?://(?:maps\.app\.goo\.gl|goo\.gl/maps|maps\.google\.[a-z.]+|www\.google\.[a-z.]+/maps)\S*")
URL = re.compile(r"https?://\S+")
KEEP_NAMES = {"Google Maps", "Hat Yai"}
TH_TITLE = re.compile(r"(นางสาว|น\.ส\.|นาย|นาง(?!ฟ้า)|ด\.ช\.|ด\.ญ\.|เด็กชาย|เด็กหญิง)\s*[ก-ฮะ-์]{2,}(?:\s+[ก-ฮะ-์]{3,})?")
NAME_AFTER = re.compile(r"((?:ชื่อ(?:เล่น)?|ชื่อจริง)\s*[:：]?\s*)([ก-ฮะ-์]{2,}(?:\s*[,และ]\s*[ก-ฮะ-์]{2,})*)")
NAME_PAREN = re.compile(r"(\(\s*ชื่[อิ]+\s*)[^)]{1,30}(\))")


def _digits(s: str) -> str:
    return re.sub(r"\d", lambda m: str(rnd.randint(0, 9)), s)


def fake_phone(m):
    s = m.group(0)
    digits = re.sub(r"\D", "", s)
    keep = 3 if digits.startswith("0") else 4                       # keep "08x"/"+668" prefix -> still looks like a phone
    i, out, n = 0, [], 0
    for ch in s:
        if ch.isdigit():
            out.append(ch if n < keep else str(rnd.randint(0, 9))); n += 1
        else:
            out.append(ch)
    return "".join(out)


def anonymise(text: str, authors: set[str]) -> tuple[str, int]:
    n = 0
    def sub(rx, fn, t):
        nonlocal n
        t2, k = rx.subn(fn, t); n += k; return t2
    t = sub(PHONE, fake_phone, text)
    t = sub(MAPS, lambda m: "https://maps.app.goo.gl/" + "".join(rnd.choice("abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(17)), t)
    t = sub(URL, lambda m: "<URL>", t)
    t = sub(COORD, lambda m: f"{float(m.group(1)) + rnd.uniform(-.004, .004):.5f}{m.group(2)}{float(m.group(3)) + rnd.uniform(-.004, .004):.5f}", t)
    t = sub(DEG, lambda m: f"{float(m.group(0)) + rnd.uniform(-.004, .004):.{min(len(m.group(0).split('.')[1]), 6)}f}"
            if 5 <= float(m.group(0)) <= 21 or 97 <= float(m.group(0)) <= 106 else m.group(0), t)      # lone lat / lng lines
    t = sub(HOUSE, lambda m: m.group(1) + _digits(m.group(2)), t)
    t = sub(TH_TITLE, lambda m: m.group(1) + "<NAME>", t)
    t = sub(NAME_AFTER, lambda m: m.group(1) + "<NAME>", t)
    t = sub(NAME_PAREN, lambda m: m.group(1) + "<NAME>" + m.group(2), t)
    t = sub(LATIN_NAME, lambda m: m.group(0) if m.group(0) in KEEP_NAMES else "<NAME>", t)
    for a in authors:                                               # commenter names quoted inside other comments
        if len(a) >= 5 and a in t:
            t = t.replace(a, "<NAME>"); n += 1
    return t, n


# ---------------- noise / chatter ----------------
HELP_HINT = re.compile(r"ช่วย|ติด|อพยพ|พิกัด|บ้านเลข|ซ\.|ซอย|ถ\.|ถนน|น้ำ(?:ถึง|ท่วม|ขึ้น|มิด)|ชั้น|หลังคา|ผู้สูงอายุ|เด็ก|ป่วย|ติดเตียง|ฟอกไต|"
                       r"อาหาร|เรือ|ด่วน|ไม่ไหว|ติดต่อไม่ได้|\d{2,3}-?\d{3}-?\d{4}|maps|ปลอดภัยแล้ว|ได้รับ(?:การช่วย|ความช่วย)|ออกมาได้|ขอบคุณ")
CHEER = re.compile(r"^(?:[\s🙏❤️♥️💕👍🥰😭🥹✌️💪]*(?:สู้\s*ๆ*|สู้สู้|สุดยอด|ขอบคุณ\S*|ขอให้(?:ทุกคน)?ปลอดภัย\S*|เป็นกำลังใจ\S*|ขอเป็นกำลังใจ\S*|"
                   r"เก่งมาก\S*|ฮีโร่\S*|คนเก่ง\S*|พี่กัน\S*|คุณกัน\S*)[\s\S]{0,60})$")


def is_chatter(t: str) -> bool:
    if HELP_HINT.search(t):
        return False
    return len(t) < 120 or bool(CHEER.match(t))


def norm(t: str) -> str:
    t = unicodedata.normalize("NFC", t.lower())
    t = re.sub(r"<[a-z]+>|https?://\S+", " ", t)
    t = re.sub(r"[^฀-๿a-z0-9]+", "", t)                   # drop emoji, punctuation, spaces
    return re.sub(r"(.)\1{2,}", r"\1\1", t)                          # ค่าาาา -> ค่าา


def dup_groups(texts: list[str], thr: float = 0.85) -> list[int]:
    """Near-duplicate clustering (shares / re-posts with small edits): char 3-gram TF-IDF cosine + union-find."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.neighbors import NearestNeighbors
    keys = [norm(t) or "_" for t in texts]
    X = TfidfVectorizer(analyzer="char", ngram_range=(3, 3), min_df=1).fit_transform(keys)
    nn = NearestNeighbors(n_neighbors=min(15, len(texts)), metric="cosine").fit(X)
    dist, idx = nn.kneighbors(X)
    parent = list(range(len(texts)))
    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a
    for i in range(len(texts)):
        for d, j in zip(dist[i], idx[i]):
            if j != i and 1 - d >= thr and len(keys[i]) > 15 and len(keys[j]) > 15:
                parent[find(i)] = find(j)
            elif keys[i] == keys[j] and j != i:
                parent[find(i)] = find(j)
    roots = {}
    return [roots.setdefault(find(i), len(roots)) for i in range(len(texts))]


def main(src, out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    rows = parse(Path(src).read_text(encoding="utf-8"))
    authors = {r["author"] for r in rows if r["author"]}
    n_pii = 0
    for r in rows:
        r["text"], k = anonymise(r["text"], authors); n_pii += k
        r["chatter"] = is_chatter(r["text"])
    groups = dup_groups([r["text"] for r in rows])
    size = Counter(groups)
    for i, (r, g) in enumerate(zip(rows, groups)):
        r["row_id"], r["dup_group"], r["dup_count"] = f"R{i:05d}", f"G{g:05d}", size[g]

    with open(out / "comments_all.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, ["row_id", "dup_group", "dup_count", "chatter", "has_image", "text"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in w.fieldnames})

    seen, keep = set(), []
    for r in sorted(rows, key=lambda r: -len(r["text"])):           # keep the most complete version of each group
        if r["dup_group"] in seen:
            continue
        seen.add(r["dup_group"]); keep.append(r)
    keep.sort(key=lambda r: r["row_id"])
    with open(out / "to_label.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, ["row_id", "dup_group", "dup_count", "has_image", "chatter", "text"])
        w.writeheader()
        for r in keep:
            w.writerow({k: r[k] for k in w.fieldnames})

    lens = sorted(len(r["text"]) for r in keep)
    rep = {"comments_parsed": len(rows), "with_author": sum(1 for r in rows if r["author"]),
           "chatter_removed": sum(r["chatter"] for r in rows), "duplicate_groups": len(size),
           "groups_with_copies": sum(1 for v in size.values() if v > 1), "largest_group": max(size.values()),
           "to_label": len(keep), "to_label_chatter": sum(1 for r in keep if r["chatter"]), "has_image_only_text": sum(1 for r in keep if r["has_image"]),
           "pii_replacements": n_pii, "median_len": lens[len(lens) // 2] if lens else 0, "p95_len": lens[int(len(lens) * .95)] if lens else 0}
    (out / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

"""Knowledge base retrieval (RAG): markdown files in 06_chat_assistant/kb/, ranked with character-bigram BM25
(works for Thai without a word tokenizer). Pure Python.

Chunks:  "## question / other wording / ..." sections (FAQ style, the heading = ways people ask) and "- **topic**: ..."
bullets, plus one whole-file chunk. Question words ("ทำยังไง", "ได้ไหม", "เท่าไหร่" ...) are removed from the query
so they do not decide the match, and a hit must cover enough of the question (MIN_COVER) — otherwise we say we
do not know instead of answering something unrelated.
"""
import math, re
from collections import Counter
from pathlib import Path

KB_DIR = Path(__file__).resolve().parent.parent / "kb"
MIN_COVER = 0.34
MIN_SCORE, MIN_SCORE_HIGH_COVER = 12.0, 8.0     # weaker matches only count when most of the question is covered
STOP = re.compile(r"ทำยังไง|ทำไง|ทำอย่างไร|อย่างไร|ยังไง|ได้ไหม|ได้มั้ย|ไหม|มั้ย|หรือเปล่า|หรือยัง|เท่าไหร่|เท่าไร|ที่ไหน|ตรงไหน|"
                  r"อะไรบ้าง|อะไร|บ้าง|ครับ|ค่ะ|คะ|นะ|จ้า|หน่อย|ช่วยบอก|อยากรู้|อยากทราบ|สอบถาม|ขอถาม|ถ้า|ต้อง|ควร|"
                  r"ของฉัน|ของผม|ของหนู|ของเรา|ฉัน|ผม|หนู|เรา|เขา|มี|เป็น|คือ|การ|แล้ว|จะ|ให้|ได้|[?？!.,]")


def _grams(s: str) -> list[str]:
    s = re.sub(r"\s+", "", s.lower())
    return [s[i:i + 2] for i in range(len(s) - 1)]


def _query_grams(q: str) -> list[str]:
    core = STOP.sub(" ", q)
    g = _grams(core)
    return g if len(g) >= 2 else _grams(q)


class KB:
    def __init__(self, folder: Path = KB_DIR):
        self.chunks = []
        for f in sorted(folder.glob("*.md")):
            text = f.read_text(encoding="utf-8")
            title = (re.search(r"^#\s+(.+)$", text, re.M) or [None, f.stem])[1]
            body = re.sub(r"^#\s.*$", "", text, count=1, flags=re.M)
            sections = re.split(r"\n(?=##\s)", body)
            for sec in sections:
                m = re.match(r"##\s+(.+)\n", sec)
                if m:                                       # FAQ section: heading = the ways people ask
                    asks = [a.strip() for a in m.group(1).split("/") if a.strip()]
                    self.chunks.append({"source": f.name, "title": asks[0], "text": sec[m.end():].strip(), "whole": False,
                                        "keys": asks, "faq": True})
                    continue
                items = [b.strip() for b in re.split(r"\n(?=\s*(?:[-*]|\d+\.)\s)", sec) if len(b.strip()) > 20]
                for it in items:
                    self.chunks.append({"source": f.name, "title": title, "text": it, "whole": False,
                                        "keys": [k.strip() for k in re.findall(r"\*\*(.+?)\*\*", it)], "faq": False})
            self.chunks.append({"source": f.name, "title": title, "text": re.sub(r"^##\s+", "", body.strip(), flags=re.M),
                                "whole": True, "keys": [], "faq": False})
        # headings / keys count twice: they are what the chunk is ABOUT
        self.docs = [Counter(_grams(c["title"] + " " + " ".join(c["keys"]) * 2 + " " + c["text"])) for c in self.chunks]
        self.keygrams = [set(_grams(" ".join(c["keys"]) + " " + c["title"])) for c in self.chunks]
        self.avg = sum(sum(d.values()) for d in self.docs) / max(len(self.docs), 1)
        df = Counter(g for d in self.docs for g in d)
        n = len(self.docs)
        self.idf = {g: math.log(1 + (n - c + .5) / (c + .5)) for g, c in df.items()}

    def search(self, query: str, k: int = 3) -> list[dict]:
        qg = _query_grams(query)
        q = Counter(qg)
        if not q:
            return []
        scores = []
        for i, d in enumerate(self.docs):
            L = sum(d.values())
            s = sum(self.idf.get(g, 0) * (d[g] * 2.2) / (d[g] + 1.2 * (.25 + .75 * L / self.avg)) for g in q if g in d)
            cover = sum(1 for g in q if g in d) / len(q)
            key_cover = sum(1 for g in q if g in self.keygrams[i]) / len(q)
            s *= (1 + key_cover)                           # the question matches the chunk's heading / topic
            if self.chunks[i]["whole"]:
                s *= 0.6                                   # prefer a specific item over the whole file
            scores.append((s, cover, i))
        out, seen = [], set()
        for s, cover, i in sorted(scores, reverse=True):
            c = self.chunks[i]
            if s <= 0 or cover < MIN_COVER or c["text"] in seen or s < (MIN_SCORE_HIGH_COVER if cover >= 0.7 else MIN_SCORE):
                continue
            seen.add(c["text"]); out.append({**c, "score": round(s, 2), "cover": round(cover, 2)})
            if len(out) == k:
                break
        return out

    def best_answer(self, hits: list[dict]) -> dict:
        """Without an LLM: if the top hits all come from one non-FAQ file (e.g. the hotline list), show that whole section."""
        if len(hits) >= 2 and len({h["source"] for h in hits}) == 1 and not hits[0].get("faq"):
            whole = next((c for c in self.chunks if c["source"] == hits[0]["source"] and c["whole"]), None)
            if whole and hits[0]["source"].startswith("01_"):
                return whole
        return hits[0]

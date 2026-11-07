# -*- coding: utf-8 -*-
# Problem 03: Duplicate / Noise / Broken Text / Normalization
# Simulates scraping/OCR noise on real questions from motorcycle_qa.txt,
# then checks the REAL file for duplicates, near-duplicates and inconsistent category names
import re
from itertools import combinations

from data_loader import load_qa, similarity, section


def make_noisy_samples(data, n=2):
    base = [d["question"] for d in data[:n]]
    raw = []
    for q in base:
        raw.append(q)                                        # original
        raw.append(q)                                        # exact duplicate
        raw.append("   " + q + "   ")                        # extra whitespace
        raw.append(q.replace(" ", "_") + "!!!")              # symbol noise
    raw.append("")                                           # empty row from a broken scrape
    return raw


def normalize(text):
    text = text.lower()
    text = re.sub(r"[_@!\-]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def run():
    data = load_qa()
    raw = make_noisy_samples(data)

    print("Before cleaning (simulated noise on real questions from the KB):")
    for x in raw:
        print(repr(x))

    normalized = [normalize(x) for x in raw if x.strip()]
    unique = list(dict.fromkeys(normalized))

    print("\nAfter Normalization + Deduplication:")
    for x in unique:
        print(repr(x))
    print("\nCount before:", len(raw))
    print("Count after:", len(unique))

    all_q = [normalize(d["question"]) for d in data]
    print(f"\nChecked the full motorcycle_qa.txt ({len(data)} entries): "
          f"{len(all_q) - len(set(all_q))} exact duplicate question(s) after normalization")

    section("Found in LAB 2 (real data)")
    # 1) near-duplicates: different text, overlapping topic
    pairs = sorted(((similarity(a["text"], b["text"]), a, b) for a, b in combinations(data, 2)),
                   key=lambda x: x[0], reverse=True)[:3]
    print("Most similar entry pairs (possible overlap / conflicting answers):")
    for s, a, b in pairs:
        print(f"  {s:.2f}  {a['question'][:40]}  <->  {b['question'][:40]}")

    # 2) inconsistent category names for the same topic
    cats = sorted(set(d["category"] for d in data))
    print(f"\n{len(cats)} category names for only {len(data)} entries:")
    for c in cats:
        overlap = [o for o in cats if o != c and (o in c or c in o)]
        flag = f"   <- overlaps with {overlap}" if overlap else ""
        print(f"  - {c} ({sum(d['category'] == c for d in data)}){flag}")

    # 3) coverage: only 35 entries
    print(f"\nCoverage: only {len(data)} Q&A -> common questions (ไฟเลี้ยวไม่ติด, เกียร์ค้าง, ยางแบน) have no answer")
    print("Cause: noise/duplicates make identical facts look different, inconsistent labels break filtering,")
    print("and a small KB pushes the LLM to answer from weak context")


if __name__ == "__main__":
    run()

# -*- coding: utf-8 -*-
# Problem 04: Chunk too large / too small / Overlap
# Uses real content (combined answers from a category) from motorcycle_qa.txt
from data_loader import load_qa, section

CATEGORY = "การบำรุงรักษาและการแก้ปัญหา"


def chunk(words, size, overlap=0):
    step = size - overlap
    return [" ".join(words[i:i + size]) for i in range(0, len(words), step)]


def lab2_split_text(text, chunk_size, overlap):
    # exact copy of LAB 2 src/text_splitter.split_text (character-based)
    if len(text) <= chunk_size:
        return [text]
    chunks, start = [], 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def run():
    data = load_qa()
    doc = " ".join(d["answer"] for d in data if d["category"] == CATEGORY and d["lang"] == "ทางการ")
    words = doc.split()

    print(f"Sample document: combined answers from category '{CATEGORY}' ({len(words)} words)")

    print("\nLarge chunk (size=60):")
    for c in chunk(words, 60)[:2]:
        print("-", c[:150] + "...")

    print("\nSmall chunk (size=6):")
    for c in chunk(words, 6)[:5]:
        print("-", c)

    print("\nChunk + Overlap (size=25, overlap=8):")
    for c in chunk(words, 25, 8)[:3]:
        print("-", c[:120] + "...")

    print("\nCause:")
    print("- Too large: multiple Q&A pairs get mixed into a single chunk, diluting the Embedding")
    print("- Too small: an explanation may be cut off mid-sentence, losing context")
    print("- Overlap: preserves context at the boundary between chunks")

    section("Found in LAB 2: character-based split cuts Thai words and numbers")
    entry = next(d for d in data if "น้ำมันเครื่องรถจักรยานยนต์บ่อยแค่ไหน" in d["question"])
    text = f"Question: {entry['question']} Answer: {entry['answer']}"
    pieces = lab2_split_text(text, 120, 20)          # smaller size to show what happens
    for i, p in enumerate(pieces):
        print(f"  chunk {i}: ...{p[-25:]!r}")
    print("  -> pieces end in the middle of a word/number; chunk 1+ has NO question text")

    lens = [len(f"Question: {d['question']} Answer: {d['answer']}") for d in data]
    print(f"\nLAB 2 setting CHUNK_SIZE=400: longest chunk = {max(lens)} chars -> "
          f"{sum(l > 400 for l in lens)} split today, but ANY longer answer will be split")
    print("Fix: keep 1 Q&A = 1 chunk; if too long, split at sentence/space boundaries and repeat the question")


if __name__ == "__main__":
    run()

# -*- coding: utf-8 -*-
# Problem 02: Vocabulary Mismatch (formal vs slang vs typo) and Token order (Position)
# Uses real questions from motorcycle_qa.txt + real user queries typed into LAB 2
from data_loader import load_qa, similarity, section


def bow(text):
    result = {}
    for token in text.split():
        result[token] = result.get(token, 0) + 1
    return result


def with_position(text):
    return [(i, token) for i, token in enumerate(text.split())]


def find(data, keyword):
    return next(d for d in data if keyword in d["question"])


def run():
    data = load_qa()

    # same intent, different wording
    pairs = [
        ("formal KB vs slang user", find(data, "น้ำมันเครื่องรถจักรยานยนต์บ่อยแค่ไหน")["question"],
         "น้ำมันเครื่อง ต้องถ่ายทุกกี่โลวะ"),
        ("KB vs typo user (LAB 2 real query)", find(data, "กดสตาร์ทแล้วรถไม่ติด")["question"],
         "รถเสย สตารดไมดด"),
    ]

    for label, kb_q, user_q in pairs:
        print(f"--- {label}")
        print("KB question  :", kb_q)
        print("User question:", user_q)
        common = set(bow(kb_q)) & set(bow(user_q))
        print("BoW (whitespace tokens) overlap:", common or "None")
        print(f"Char-bigram similarity (LAB 2 BM25 style): {similarity(kb_q, user_q):.2f}")
        print()

    print("-> Same intent, but BoW finds almost nothing in common (Vocabulary Mismatch)")
    print("   Thai has no spaces between words, so a whole sentence becomes ONE token for BoW")
    print("   Character bigrams help a little, but typos like 'สตารด' vs 'สตาร์ท' still score low")

    print("\nExample: effect of Token order on meaning (Position):")
    entry = find(data, "รถจมน้ำมิด")
    a = " ".join(entry["answer"].split()[:6])
    b = " ".join(reversed(a.split()))
    print("A (original):", with_position(a))
    print("B (reversed order):", with_position(b))
    print("BoW identical:", bow(a) == bow(b))

    section("Found in LAB 2")
    print("- Typo query 'รถเสย สตารดไมดด' ranked 'ซื้อรถมือสอง' #1; the correct answer (สตาร์ทไม่ติด) was #2")
    print("- Token limit: paraphrase-multilingual-MiniLM-L12-v2 truncates input at max_seq_length (128 tokens)")
    lens = sorted((len("Question: " + d["question"] + " Answer: " + d["answer"]), d["question"]) for d in data)
    long_ones = [x for x in lens if x[0] > 300]
    print(f"  LAB 2 chunk length: {lens[0][0]}-{lens[-1][0]} chars; {len(long_ones)} chunks > 300 chars")
    print("  Measured by problem10_debug_scripts.py: 77-129 tokens per chunk -> 1/35 chunks over 128 (1 token cut)")
    print("  -> fine today, but any longer answer will have its END silently ignored by the embedding")
    print("Fix: USE_QUERY_TRANSFORM (LLM rewrites typo/slang), embed question separately, or a long-context model (bge-m3)")


if __name__ == "__main__":
    run()

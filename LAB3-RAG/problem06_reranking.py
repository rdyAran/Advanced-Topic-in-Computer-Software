# -*- coding: utf-8 -*-
# Problem 06: The Relevant Document ends up ranked near the bottom by First-stage Retrieval
# Uses real data from motorcycle_qa.txt
from data_loader import load_qa, similarity, section

# user: "รถออโต้วิ่งแล้วมีเสียงหอนจากล้อหลัง"
GENERIC_TERMS = ["รถ", "ออโต้", "หลัง"]
SPECIFIC_TERMS = ["เสียงหอน", "เฟืองท้าย"]


def first_stage(doc):
    text = doc["question"] + doc["answer"]
    return sum(text.count(t) for t in GENERIC_TERMS)


def rerank(doc):
    text = doc["question"] + doc["answer"]
    score = first_stage(doc)
    score += sum(10 for t in SPECIFIC_TERMS if t in text)
    return score


def run():
    data = load_qa()

    first = sorted(data, key=first_stage, reverse=True)[:6]
    second = sorted(first, key=rerank, reverse=True)

    print("User: 'รถออโต้วิ่งแล้วมีเสียงหอนจากล้อหลัง'")
    print(f"Before Re-ranking (Top 6 from First-stage: generic terms {GENERIC_TERMS}):")
    for d in first:
        print(f"  score={first_stage(d):2} | {d['question']}")

    print(f"\nAfter Re-ranking (extra weight for specific terms {SPECIFIC_TERMS}):")
    for d in second:
        print(f"  score={rerank(d):2} | {d['question']}")

    print("\nCause: First-stage Retrieval counts generic terms, so long answers that repeat 'รถ/ออโต้/หลัง'")
    print("win, and the most specific document can end up near the bottom of Top-k")
    print("Re-ranking uses finer-grained signals to push the relevant document toward the top")

    section("Found in LAB 2")
    q = "รถเสย สตารดไมดด"
    ranked = sorted(data, key=lambda d: similarity(q, d["question"]), reverse=True)[:3]
    print(f"Typo query '{q}' (char-bigram ranking, similar to LAB 2 BM25):")
    for i, d in enumerate(ranked, 1):
        print(f"  #{i} {similarity(q, d['question']):.2f} {d['question']}")
    print("  (a tie at the top: which one wins depends on tie-breaking -> unstable ranking)")
    print("- Real LAB 2 run: correct answer (สตาร์ทไม่ติด) was #2 -> with TOP_K=1 (LAB 1 main.py) the user gets a wrong answer")
    print("- USE_RERANK=False by default (bge-reranker-v2-m3 is ~2 GB)")
    print("- RRF fuses RANKS only: a chunk that is 'okay' in both BM25 and dense can beat one that is 'perfect' in one")
    print("Fix: turn on the cross-encoder (20 -> 3) and compare with `python -m evaluation.eval_retrieval`")


if __name__ == "__main__":
    run()

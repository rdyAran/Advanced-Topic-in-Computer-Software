# -*- coding: utf-8 -*-
# Problem 01: Hallucination / No evidence in Retrieved Context
# Uses motorcycle_qa.txt as a real Knowledge Base
#
# LAB 2 finding: retriever ALWAYS returns top-k (MIN_SCORE in config.py is never used),
# so even an unrelated question sends unrelated context to the LLM.
from data_loader import load_qa, section

DOCS = load_qa()


def retrieve(question, top_k=3):
    words = question.lower().split()
    scored = [(sum(w in d["text"].lower() for w in words) / len(words), d) for d in DOCS]
    scored = [s for s in scored if s[0] > 0]
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_k]


def bad_generate(question, context):
    if not context:
        # Simulated failure: the model still fabricates an answer even without evidence in the KB
        return "เติมน้ำมันดีเซลผสมเบนซินช่วยให้มอเตอร์ไซค์แรงขึ้น (ข้อมูลนี้ไม่มีอยู่จริงใน Knowledge Base)"
    # Simulated failure: answers from whatever came back, even a weak match
    return context[0][1]["answer"]


def grounded_generate(question, context, min_score=0.6):
    # Fix: only answer when the best match has enough supporting evidence
    if not context or context[0][0] < min_score:
        return "ไม่พบข้อมูลที่สนับสนุนคำตอบใน Knowledge Base"
    return context[0][1]["answer"]


def run():
    cases = [
        ("Out of KB scope", "ตั๋วเครื่องบินไปเชียงใหม่ราคาเท่าไหร่"),
        ("Weak match (LAB 2 case)", "รถ ยนต์ไฟฟ้า ชาร์จ กี่ชั่วโมง"),
        ("In KB", "รถ ใช้ E20 ได้ไหม"),
    ]

    for label, q in cases:
        ctx = retrieve(q)
        print(f"--- Query ({label}): {q}")
        print("Retrieved:", [f"{s:.2f} {d['question']}" for s, d in ctx] or "Not found")
        print("Bad answer  :", bad_generate(q, ctx)[:120])
        print("Fixed answer:", grounded_generate(q, ctx)[:120])
        print()

    print("Cause: The generator answers even though the Retrieved Context has no supporting evidence")
    print("- Out of scope : nothing retrieved, but the model still invents an answer")
    print("- Weak match   : only the word 'รถ' matches, the top document is unrelated (EV charging is not in the KB)")

    section("Found in LAB 2")
    print("- config.py defines MIN_SCORE = 0.0 but no file uses it -> top-3 is always sent to the LLM")
    print("- Real run: 'รถเสียทำใง' -> context = น้ำมันเฟืองท้าย / โช้คหลัง / จอดตากแดด (all unrelated)")
    print("- Only the prompt rule 'answer from context only' stops hallucination; a 7B model may not obey")
    print("Fix: drop chunks below a score threshold BEFORE calling the LLM (as grounded_generate does)")


if __name__ == "__main__":
    run()

# -*- coding: utf-8 -*-
# Problem 07: Retrieval is correct, but the Generated Answer distorts the Context (Faithfulness)
# Uses real answers from motorcycle_qa.txt that contain safety-critical instructions and numbers
import re

from data_loader import load_qa, similarity, section

NUM = re.compile(r"\d[\d,\.]*")
CITE = re.compile(r"\[(\d+)\]")
CRITICAL_WORDS = ["ห้าม", "ไม่ควร", "อันตราย", "เด็ดขาด"]


def find_entry(data, keyword):
    return next(d for d in data if keyword in d["question"])


def bad_generator(context):
    # Simulated failure: the generator unknowingly flips a safety instruction / changes a number
    return (context.replace("ห้ามสตาร์ทเด็ดขาด", "สตาร์ทได้ทันที")
                   .replace("95 เดซิเบล", "110 เดซิเบล"))


def grounded_generator(context):
    return context


def faithfulness_check(answer, context):
    """Cheap post-check (no LLM judge): numbers and critical words in the context must survive"""
    problems = []
    for n in sorted(set(NUM.findall(answer)) - set(NUM.findall(context))):
        problems.append(f"number '{n}' is not in the context")
    for w in CRITICAL_WORDS:
        if w in context and w not in answer:
            problems.append(f"critical word '{w}' was dropped")
    return problems or ["OK"]


def citation_check(answer, contexts, min_sim=0.15):
    """Every [n] must point to a context that the sentence actually uses"""
    problems = []
    for sentence in re.split(r"(?<=[\]\.])\s+", answer):
        for n in CITE.findall(sentence):
            n = int(n)
            if n > len(contexts):
                problems.append(f"[{n}] does not exist")
                continue
            s = similarity(CITE.sub("", sentence), contexts[n - 1])
            if s < min_sim:
                problems.append(f"[{n}] cited but sentence does not use it (sim={s:.2f})")
    return problems or ["OK"]


def run():
    data = load_qa()

    for keyword in ["รถจมน้ำมิด", "ท่อแต่งเสียงดัง"]:
        entry = find_entry(data, keyword)
        context = entry["answer"]
        bad = bad_generator(context)
        print("Question:", entry["question"])
        print("Retrieved Context :", context[:160] + "...")
        print("Bad Generation    :", bad[:160] + "...")
        print("Grounded          :", grounded_generator(context)[:160] + "...")
        print("faithfulness_check(bad)     ->", faithfulness_check(bad, context))
        print("faithfulness_check(grounded)->", faithfulness_check(context, context))
        print()

    print("Cause: Retrieval is correct, but the Generator changes a critical detail")
    print("('ห้ามสตาร์ท' -> 'สตาร์ทได้' can destroy an engine; a wrong dB limit gives wrong legal advice)")
    print("The Prompt must force answers from Context only, and Faithfulness must be checked before replying")

    section("Found in LAB 2 (real qwen2.5:7b output)")
    ctx = [find_entry(data, k)["answer"] for k in ["น้ำมันเฟืองท้าย", "โช้คหลัง", "จอดรถตากแดด"]]
    real_answer = "คำถามนี้ไม่ชัดเจนว่าเกิดปัญหาอะไร จึงขอให้ระบุปัญหาเฉพาะเจาะจงเพื่อให้คำแนะนำที่เหมาะสม [1][2][3]"
    print("Answer:", real_answer)
    print("citation_check ->", citation_check(real_answer, ctx))
    good_answer = "น้ำมันเฟืองท้ายควรเปลี่ยนทุกๆ 2 ครั้งของการเปลี่ยนน้ำมันเครื่อง [1]"
    print("\nAnswer:", good_answer)
    print("citation_check ->", citation_check(good_answer, ctx))
    print("\nOther LAB 2 issues:")
    print("- When the LLM fails (404/429/503), rag_pipeline falls back to chunks[0] even if it is the wrong topic")
    print("- eval_generation.py uses char-bigram F1: 'ห้ามสตาร์ท' vs 'สตาร์ทได้' still scores high")
    print("Fix: add faithfulness_check + citation_check after generation; fallback only when score >= threshold")


if __name__ == "__main__":
    run()

# -*- coding: utf-8 -*-
# Problem 09: CHUNK_SIZE / OVERLAP / EVAL_K_VALUES and Retrieval Evaluation on motorcycle_qa.txt
# Runs a REAL evaluation (pure Python, char-bigram retriever) on 5 query types to show
# why LAB 2's golden set (mostly verbatim/partial) gives scores that look better than reality.
from data_loader import load_qa, similarity, section

CHUNK_SIZE = 400
CHUNK_OVERLAP = 50
EVAL_K_VALUES = [1, 3, 5]
MIN_SCORE = 0.12

# (query, source question keyword) ; keyword=None -> out of scope (correct behaviour = return nothing)
GOLDEN = {
    "verbatim": [(None, k) for k in ["น้ำมันเครื่องรถจักรยานยนต์บ่อยแค่ไหน", "ผ้าเบรกหมด", "หมวกกันน็อก",
                                     "ขับลุยน้ำท่วม", "ท่อแต่งเสียงดัง", "รถโดนขโมย"]],
    "natural": [("ถ่ายน้ำมันเครื่องมอไซค์ทุกกี่กิโล", "น้ำมันเครื่องรถจักรยานยนต์บ่อยแค่ไหน"),
                ("รู้ได้ยังไงว่าถึงเวลาเปลี่ยนผ้าเบรก", "ผ้าเบรกหมด"),
                ("ซื้อหมวกนิรภัยต้องดูอะไร ใช้ได้นานกี่ปี", "หมวกกันน็อก"),
                ("หลังขี่ฝ่าน้ำขังควรตรวจเช็กอะไรบ้าง", "ขับลุยน้ำท่วม"),
                ("เปลี่ยนท่อไอเสียเสียงดังผิดกฎหมายไหม", "ท่อแต่งเสียงดัง"),
                ("วิธีป้องกันมอเตอร์ไซค์หายมีอะไรบ้าง", "รถโดนขโมย")],
    "slang": [("น้ำมันเครื่องต้องถ่ายทุกกี่โลวะ", "น้ำมันเครื่องรถจักรยานยนต์บ่อยแค่ไหน"),
              ("เบรกดังเอี๊ยดๆ ผ้าเบรกหมดยังวะ", "ผ้าเบรกหมด"),
              ("ท่อซิ่งเสียงลั่นๆ ตำรวจจับป่ะ", "ท่อแต่งเสียงดัง"),
              ("กลัวรถหายว่ะ ล็อกไงดี", "รถโดนขโมย")],
    "typo": [("รถเสย สตารดไมดด", "กดสตาร์ทแล้วรถไม่ติด"),
             ("น้ำมันเคื่องเปลี่ยนตอนไหน", "น้ำมันเครื่องรถจักรยานยนต์บ่อยแค่ไหน"),
             ("ผ้าเบกหมดดูไง", "ผ้าเบรกหมด"),
             ("ยางหัวโลน ใช้ต่อได้มั้ย", "ยางหัวโล้น")],
    "out_of_scope": [("รถยนต์ไฟฟ้าชาร์จกี่ชั่วโมง", None), ("ตั๋วเครื่องบินไปเชียงใหม่ราคาเท่าไหร่", None),
                     ("สูตรต้มยำกุ้ง", None), ("ต่อทะเบียนรถยนต์ออนไลน์ยังไง", None)],
}


def ranges(total):
    result, start, step = [], 0, CHUNK_SIZE - CHUNK_OVERLAP
    while start < total:
        result.append((start, min(start + CHUNK_SIZE, total)))
        start += step
    return result


def retrieve(data, query, k):
    scored = sorted(((similarity(query, d["text"]), d) for d in data), key=lambda x: x[0], reverse=True)
    return scored[:k]


def run():
    data = load_qa()
    full_text = " ".join(d["text"] for d in data)
    r = ranges(len(full_text))
    print(f"Real document from motorcycle_qa.txt is {len(full_text)} characters long ({len(data)} Q&A)")
    print(f"Number of chunks if split as ONE long text (CHUNK_SIZE={CHUNK_SIZE}, OVERLAP={CHUNK_OVERLAP}):", len(r))
    print("First few chunk ranges:", r[:4])
    print("Overlap Chunk 1/2 =", r[0][1] - r[1][0])
    print("-> chunk boundaries ignore Q&A boundaries; LAB 2 avoids this by chunking per Q&A (35 chunks)")

    print("\nRetrieval Evaluation (char-bigram retriever, same idea as LAB 2 BM25):")
    print(f"{'type':<13}{'n':>3}" + "".join(f"{'Hit@' + str(k):>8}" for k in EVAL_K_VALUES) + f"{'MRR':>8}")
    for qtype, items in GOLDEN.items():
        if qtype == "out_of_scope":
            continue
        hits = {k: 0 for k in EVAL_K_VALUES}
        rr = 0.0
        for query, key in items:
            query = query or next(d["question"] for d in data if key in d["question"])
            ranked = [d for _, d in retrieve(data, query, len(data))]
            rank = next(i for i, d in enumerate(ranked, 1) if key in d["question"])
            rr += 1 / rank
            for k in EVAL_K_VALUES:
                hits[k] += rank <= k
        n = len(items)
        print(f"{qtype:<13}{n:>3}" + "".join(f"{hits[k] / n:>8.2f}" for k in EVAL_K_VALUES) + f"{rr / n:>8.2f}")

    print(f"\nOut-of-scope questions (should return NOTHING, MIN_SCORE={MIN_SCORE}):")
    for query, _ in GOLDEN["out_of_scope"]:
        score, top = retrieve(data, query, 1)[0]
        verdict = "rejected ✓" if score < MIN_SCORE else f"answered with '{top['question'][:30]}' ✗"
        print(f"  {score:.2f}  {query:<38} {verdict}")

    in_scope = [q for t, items in GOLDEN.items() if t not in ("out_of_scope", "verbatim") for q, _ in items]
    too_low = [q for q in in_scope if retrieve(data, q, 1)[0][0] < MIN_SCORE]
    print(f"\nTrade-off: {len(too_low)}/{len(in_scope)} IN-scope questions also fall below MIN_SCORE "
          f"(would be wrongly rejected), e.g. {too_low[:3]}")
    print("-> lexical scores cannot separate in-scope from out-of-scope questions;")
    print("   the threshold must use a semantic (dense) score and be tuned on a golden set with BOTH kinds")

    section("Found in LAB 2: evaluation that looks better than reality")
    print("- LAB 2 golden_set.json: verbatim 35 / partial 35 / natural 35 / slang 8 / typo 0 / out-of-scope 0")
    print("  -> 70 of 113 queries are copied from the KB, so the overall Hit@3 is inflated")
    print("- Paraphrases were written by the same person who wrote the KB (author bias)")
    print("- No typo and no out-of-scope queries -> Problem 1 and Problem 2 are never measured")
    print("- Generation metrics are lexical (char-bigram F1); relevance uses the same embedding as retrieval")
    print("Fix: report scores BY TYPE, add typo + out-of-scope sets, add number_match / refusal_accuracy")


if __name__ == "__main__":
    run()

"""
build_golden_set.py — create data/golden_set.json (the evaluation set)

Each item = 1 source Q&A x up to 4 query variants:
  verbatim : exact question from the knowledge base  (sanity check)
  natural  : hand-written paraphrase                  (NOT copied from the data -> no leakage)
  partial  : only the first part of the question (auto-generated)
  slang    : hand-written casual/slang paraphrase

The expected answer (gold) is the original answer, linked by the source question
-> qa_id is looked up from chunk_store, so it stays correct after re-indexing.

Run:  python -m evaluation.build_golden_set
"""

import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from src.document_loader import load_qa_file

# source question -> (natural paraphrase, slang paraphrase or None)
PARAPHRASES = {
    "รถจักรยานยนต์มีส่วนประกอบหลักอะไรบ้าง":
        ("มอเตอร์ไซค์คันหนึ่งประกอบด้วยระบบอะไรบ้าง", None),
    "เครื่องยนต์ 2 จังหวะ กับ 4 จังหวะ แตกต่างกันอย่างไร":
        ("เครื่องสองที กับ สี่ที ต่างกันยังไง", "เครื่อง 2T กับ 4T อันไหนดีกว่าวะ"),
    "ระบบหัวฉีด (Fuel Injection) กับคาร์บูเรเตอร์ ต่างกันอย่างไร":
        ("รถหัวฉีดดีกว่ารถคาร์บูตรงไหน", None),
    "รถเกียร์ออโต้ (CVT) กับรถเกียร์ธรรมดา ต่างกันอย่างไร":
        ("สกู๊ตเตอร์กับรถเกียร์ควรเลือกแบบไหน", None),
    "ระบบเบรก ABS กับ CBS คืออะไร":
        ("เบรกกันล้อล็อกกับเบรกร่วมทำงานต่างกันยังไง", None),
    "ซีซี (cc) ของรถจักรยานยนต์หมายถึงอะไร":
        ("ความจุกระบอกสูบของมอเตอร์ไซค์บอกอะไรเรา", None),
    "ควรเปลี่ยนน้ำมันเครื่องรถจักรยานยนต์บ่อยแค่ไหน":
        ("ถ่ายน้ำมันเครื่องมอไซค์ทุกกี่กิโล", "น้ำมันเครื่องต้องถ่ายทุกกี่โลวะ"),
    "น้ำมันเฟืองท้ายของรถออโต้ต้องเปลี่ยนไหม":
        ("รถสกู๊ตเตอร์จำเป็นต้องถ่ายน้ำมันเกียร์ท้ายหรือเปล่า", None),
    "สายพานรถเกียร์ออโต้ (CVT) ควรเปลี่ยนเมื่อไร":
        ("สายพานขับเคลื่อนของสกู๊ตเตอร์ใช้ได้กี่กิโลเมตร", None),
    "โซ่รถจักรยานยนต์ต้องดูแลอย่างไร":
        ("ควรหยอดน้ำมันและตั้งโซ่บ่อยแค่ไหน", None),
    "ผ้าเบรกหมดสังเกตได้อย่างไร":
        ("รู้ได้ยังไงว่าถึงเวลาเปลี่ยนผ้าเบรก", "เบรกดังเอี๊ยดๆ ผ้าเบรกหมดยังวะ"),
    "แรงดันลมยางรถจักรยานยนต์ควรเติมเท่าไร":
        ("ยางหน้ายางหลังควรเติมลมกี่ปอนด์", None),
    "แบตเตอรี่รถจักรยานยนต์มีอายุการใช้งานเท่าไร":
        ("แบตมอไซค์ใช้ได้กี่ปีถึงต้องเปลี่ยน", None),
    "หมวกกันน็อกที่ดีควรเลือกอย่างไร และควรเปลี่ยนเมื่อไร":
        ("ซื้อหมวกนิรภัยต้องดูอะไร ใช้ได้นานกี่ปี", None),
    "พ.ร.บ. กับประกันภัยภาคสมัครใจ แตกต่างกันอย่างไร":
        ("ประกันภาคบังคับคุ้มครองรถเราด้วยไหม", None),
    "รถจักรยานยนต์ใช้น้ำมันแก๊สโซฮอล์ E20 ได้หรือไม่":
        ("มอเตอร์ไซค์เติม E20 แล้วเครื่องจะเสียไหม", None),
    "กดสตาร์ทแล้วรถไม่ติด มีแต่เสียงแชะๆ เป็นอะไรครับ":
        ("สตาร์ทมือแล้วเครื่องไม่หมุน เกิดจากอะไร", "กดสตาร์ทแม่งไม่ติดเลย ดังแต่แชะๆ"),
    "รถออโต้ออกตัวสั่นๆ อืดๆ ต้องทำยังไง":
        ("สกู๊ตเตอร์ออกตัวแล้วกระตุก ควรแก้อย่างไร", None),
    "ใช้น้ำมันเครื่องรถยนต์เติมมอไซค์ได้ไหม":
        ("น้ำมันเครื่องของรถเก๋งใช้กับรถจักรยานยนต์ได้หรือเปล่า", None),
    "ล้างรถด้วยน้ำยาล้างจานได้ไหม":
        ("ใช้ซันไลต์ล้างมอเตอร์ไซค์จะทำให้สีเสียไหม", None),
    "ยางรถตะปูตำ ใช้แบบปะยางเสียบได้ไหม":
        ("ยางรั่วเพราะโดนตะปู ควรปะหรือเปลี่ยนเส้นใหม่", None),
    "ขับลุยน้ำท่วมมา ต้องทำอะไรต่อบ้าง":
        ("หลังขี่ฝ่าน้ำขังควรตรวจเช็กอะไรบ้าง", None),
    "เติมลมไนโตรเจนดีกว่าลมธรรมดาจริงไหม":
        ("ลมไนโตรเจนคุ้มกว่าลมปกติหรือเปล่า", None),
    "จอดรถตากแดดทุกวัน รถจะพังไวไหม":
        ("จอดมอเตอร์ไซค์กลางแจ้งเป็นประจำมีผลเสียอะไรบ้าง", None),
    "ไฟหน้ารถหรี่ๆ ตอนขับช้า แต่บิดแล้วสว่าง เป็นเพราะอะไร":
        ("ทำไมไฟหน้าสว่างขึ้นเมื่อเร่งเครื่อง", None),
    "ใส่ท่อแต่งเสียงดังๆ โดนจับป่ะวะ":
        ("เปลี่ยนท่อไอเสียเสียงดังผิดกฎหมายไหม", "ท่อซิ่งเสียงลั่นๆ ตำรวจจับป่ะ"),
    "รถจมน้ำมิดเลย สตาร์ทเลยได้ป่ะวะ":
        ("มอเตอร์ไซค์โดนน้ำท่วมทั้งคัน ควรสตาร์ทเครื่องทันทีไหม", None),
    "ยางหัวโล้นแล้วแม่งยังวิ่งได้ ใช้ต่อได้ป่ะ":
        ("ดอกยางสึกหมดแล้วยังใช้งานต่อได้หรือไม่", None),
    "ใส่ไฟหน้า LED แต่งสว่างๆ โคตรชัด มีปัญหาป่ะ":
        ("เปลี่ยนหลอดไฟหน้าเป็น LED มีข้อเสียอะไรไหม", None),
    "โช้คหลังน้ำมันแตก ซึมเยิ้มเลย ขี่ต่อได้ป่ะวะ":
        ("โช้คอัพรั่วยังขับขี่ได้อย่างปลอดภัยไหม", None),
    "ซื้อรถมือสองต้องดูไรบ้าง กลัวโดนย้อมแมว":
        ("ก่อนซื้อมอเตอร์ไซค์มือสองควรตรวจสอบอะไร", "จะซื้อรถมือสองดูไงไม่ให้โดนหลอกวะ"),
    "น้ำมันขวดหน้าบ้านถูกกว่าปั๊ม เติมได้ป่ะวะ":
        ("น้ำมันที่ขายเป็นขวดปลอดภัยต่อเครื่องยนต์ไหม", None),
    "เปลี่ยนกล่อง ECU ปลดรอบ รถแรงขึ้นจริงป่ะวะ":
        ("กล่องไฟแต่งช่วยเพิ่มกำลังเครื่องได้จริงไหม", None),
    "รถโดนขโมยบ่อยชิบ กันยังไงดีวะ":
        ("วิธีป้องกันมอเตอร์ไซค์หายมีอะไรบ้าง", "กลัวรถหายว่ะ ล็อกไงดี"),
    "รถกินน้ำมันโคตรเปลือง ผิดปกติป่ะวะ":
        ("ทำไมมอเตอร์ไซค์ใช้น้ำมันมากกว่าปกติ", "รถซดน้ำมันหนักมาก เป็นไรวะ"),
}


def partial_of(question):
    """keep roughly the first 60% of the question (at least 8 chars)"""
    cut = max(8, int(len(question) * 0.6))
    return question[:cut].strip()


def main():
    records = load_qa_file(config.SOURCE_FILE)
    items = []
    for r in records:
        natural, slang = PARAPHRASES.get(r["question"], (None, None))
        queries = [{"type": "verbatim", "query": r["question"]}]
        if natural:
            queries.append({"type": "natural", "query": natural})
        if len(r["question"]) >= 20:
            queries.append({"type": "partial", "query": partial_of(r["question"])})
        if slang:
            queries.append({"type": "slang", "query": slang})
        items.append({
            "item_id": len(items),
            "source_question": r["question"],
            "category": r["category"],
            "gold_answer": r["answer"],
            "queries": queries,
        })

    missing = set(PARAPHRASES) - {r["question"] for r in records}
    if missing:
        print(f"[warn] {len(missing)} paraphrases no longer match the data file")

    with open(config.GOLDEN_SET_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    counts = {}
    for it in items:
        for q in it["queries"]:
            counts[q["type"]] = counts.get(q["type"], 0) + 1
    total = sum(counts.values())
    print(f"golden_set.json: {len(items)} items, {total} queries  {counts}")
    print(f"Saved to: {config.GOLDEN_SET_FILE}")


if __name__ == "__main__":
    main()

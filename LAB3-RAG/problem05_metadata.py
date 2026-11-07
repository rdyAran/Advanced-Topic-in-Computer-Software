# -*- coding: utf-8 -*-
# Problem 05: Similarity Search returns a document with the right content but wrong Metadata (register/tone)
# Uses real data from motorcycle_qa.txt, which has formal/casual/slang variants
from data_loader import load_qa, section

QUERY = "สตาร์ท ไม่ติด แบต"
QUERY_NO_FORMAL = "ยาง ดอกยาง สึก"


def score(query, text):
    return sum(word in text for word in query.split())


def search(data, query, lang=None):
    docs = data if lang is None else [d for d in data if d["lang"] == lang]
    return max(docs, key=lambda d: score(query, d["question"] + " " + d["answer"]))


def lab2_category(raw_header):
    # LAB 2 src/document_loader.py: keeps the whole header text as category
    return raw_header.strip("[]").replace("หมวด:", "").strip()


def run():
    data = load_qa()

    bad = search(data, QUERY)
    good = search(data, QUERY, lang="ทางการ")

    print("Query:", QUERY)
    print("\nWithout filtering by Metadata (lang) -> picks the document with the most keyword matches, ignoring tone:")
    print(f"  [{bad['lang']}] {bad['question']}")
    print(f"  {bad['answer'][:90]}...")

    print("\nFilter lang='ทางการ' (want a formal-tone answer for an official service-center chatbot):")
    print(f"  [{good['lang']}] {good['question']}")
    print(f"  {good['answer'][:90]}...")

    print("\nSide effect: filtering too strictly when NO formal entry covers the topic")
    b2, g2 = search(data, QUERY_NO_FORMAL), search(data, QUERY_NO_FORMAL, lang="ทางการ")
    print(f"  Query: {QUERY_NO_FORMAL}")
    print(f"  no filter      -> [{b2['lang']}] {b2['question']}")
    print(f"  lang='ทางการ'  -> [{g2['lang']}] {g2['question']}   <- wrong topic!")
    print("  -> a metadata filter must fall back (e.g. rewrite the slang answer formally) instead of returning another topic")

    print("\nCause: Keyword/Semantic Similarity picks the document with the most matching words")
    print("but does not guarantee the document has the correct Metadata (e.g. register/tone) the system needs")

    section("Found in LAB 2: language variant is stored INSIDE the category")
    lab2_cats = sorted(set(lab2_category("[หมวด: " + d["raw_category"] + "]") for d in data))
    print(f"LAB 2 parser -> {len(lab2_cats)} categories (no separate 'lang' field):")
    for c in lab2_cats:
        print("  -", c)
    print(f"\nThis data_loader -> {len(set(d['category'] for d in data))} categories + "
          f"lang field {sorted(set(d['lang'] for d in data))}")
    print("-> In LAB 2 you cannot filter by tone at all, and one topic is spread over 3-4 category names")
    print("Fix: split category/lang in document_loader.py, store both in chunk_store, filter before search")


if __name__ == "__main__":
    run()

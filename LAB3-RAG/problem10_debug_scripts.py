# -*- coding: utf-8 -*-
# Problem 10: Debug RAG Scripts
#
# Part A - 4 classic bugs in RAG scripts, each shown as BUGGY vs FIXED on motorcycle_qa.txt
#          (all four happened or could happen in LAB 1 / LAB 2)
# Part B - "RAG doctor": checks a real LAB 2 project folder for these bugs
#          python problem10_debug_scripts.py [path\to\LAB2-RAG-LLM]
#          (default: ../LAB2-RAG-LLM, or the LAB2_DIR environment variable)
import hashlib
import importlib.util
import json
import os
import re
import sys

from data_loader import DATA_PATH, load_qa, similarity, section

HERE = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------- Part A
def bug1_encoding():
    section("Bug 1: file read without encoding='utf-8' (Windows default is cp874/cp1252)")
    with open(DATA_PATH, "rb") as f:
        raw = f.read()
    wrong = raw.decode("cp1252", errors="replace")           # what open(path) may do on Windows
    n_wrong = len(re.findall(r"\[หมวด:", wrong))
    n_right = len(load_qa())
    print(f"BUGGY open(path)                    -> {n_wrong} entries parsed (Thai text becomes garbage)")
    print(f"FIXED open(path, encoding='utf-8')  -> {n_right} entries parsed")
    print("Also: print() of Thai on Windows console -> UnicodeEncodeError; fixed by sys.stdout.reconfigure(encoding='utf-8')")


def bug2_off_by_one(data):
    section("Bug 2: off-by-one when slicing the ranking")
    q = "ควรเปลี่ยนน้ำมันเครื่องรถจักรยานยนต์บ่อยแค่ไหน"
    ranked = sorted(data, key=lambda d: similarity(q, d["text"]), reverse=True)
    buggy = ranked[1:4]          # BUG: 'skip the query itself' copied from a doc-to-doc similarity script
    fixed = ranked[0:3]
    print("Query:", q)
    print("BUGGY ranked[1:4] ->", [d["question"][:30] for d in buggy])
    print("FIXED ranked[0:3] ->", [d["question"][:30] for d in fixed])
    print("-> the best answer is silently dropped; Hit@1 = 0 for every verbatim query")


def bug3_misaligned_store(data):
    section("Bug 3: FAISS index order != chunk_store order")
    q = "รถโดนขโมยบ่อย กันยังไง"
    index_order = list(data)                                       # vectors added in file order
    chunk_store = sorted(data, key=lambda d: d["category"])        # BUG: store saved after sorting
    best_pos = max(range(len(index_order)), key=lambda i: similarity(q, index_order[i]["text"]))
    print("Query:", q)
    print("Index says best position =", best_pos)
    print("BUGGY chunk_store[pos] ->", chunk_store[best_pos]["question"])
    print("FIXED (same order)     ->", index_order[best_pos]["question"])
    aligned = all(a["id"] == b["id"] for a, b in zip(index_order, chunk_store))
    print("Sanity check: ids aligned =", aligned, "-> add `assert chunk['chunk_id'] == position` after loading")


def bug4_stale_index(data):
    section("Bug 4: stale index (LAB 1 'still answers about computers')")
    old_index = [{"question": "SSD กับ HDD แตกต่างกันอย่างไร", "answer": "SSD เร็วกว่า HDD ..."},
                 {"question": "RAM ทำหน้าที่อะไร", "answer": "RAM คือหน่วยความจำชั่วคราว ..."}]
    q = "รถเสียทำใง"
    best = max(old_index, key=lambda d: similarity(q, d["question"] + d["answer"]))
    print("Data file now: motorcycle_qa.txt, but vector_db/ was built from com_h.txt")
    print(f"Query '{q}' -> '{best['question']}'   <- answer from the OLD knowledge base")
    print("FIX: save sha256(data file) in index_meta.json at build time; compare at startup; rebuild if different")


# ---------------------------------------------------------------- Part B
def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def report(ok, msg):
    print(("  ✓ " if ok else "  ✗ ") + msg)


def rag_doctor(lab2_dir):
    section(f"Part B: RAG doctor -> {lab2_dir}")
    print("Environment:")
    report(True, f"python = {sys.executable} ({sys.version.split()[0]})")
    for mod in ["numpy", "faiss", "sentence_transformers"]:
        found = importlib.util.find_spec(mod) is not None
        report(found, f"import {mod}" + ("" if found else
               f"  -> run: \"{sys.executable}\" -m pip install -r requirements.txt"))

    if not os.path.isdir(lab2_dir):
        print(f"\n  (LAB 2 folder not found: {lab2_dir})")
        print("  Run: python problem10_debug_scripts.py C:\\path\\to\\LAB2-RAG-LLM")
        return

    cfg_path = os.path.join(lab2_dir, "config.py")
    cfg = open(cfg_path, encoding="utf-8").read() if os.path.exists(cfg_path) else ""
    print("\nLAB 2 project:")
    m = re.search(r'SOURCE_FILE\s*=\s*os\.path\.join\(DATA_DIR,\s*"([^"]+)"\)', cfg)
    src = os.path.join(lab2_dir, "data", m.group(1)) if m else None
    report(bool(src and os.path.exists(src)), f"SOURCE_FILE = {m.group(1) if m else '?'}")

    meta_path = os.path.join(lab2_dir, "vector_db", "index_meta.json")
    if os.path.exists(meta_path) and src and os.path.exists(src):
        meta = json.load(open(meta_path, encoding="utf-8"))
        same = meta.get("source_sha256") == sha256(src)
        report(same, "vector_db matches data file" if same else "vector_db is STALE -> python build_index.py")
    else:
        report(False, "vector_db/index_meta.json missing -> python build_index.py")

    # MIN_SCORE defined but never used
    used = False
    for root, _, files in os.walk(os.path.join(lab2_dir, "src")):
        for fn in files:
            if fn.endswith(".py") and "MIN_SCORE" in open(os.path.join(root, fn), encoding="utf-8").read():
                used = True
    report(used, "MIN_SCORE is used by the pipeline" if used else
           "MIN_SCORE is defined in config.py but never used (Problem 1)")

    # category/lang mixed (Problem 5)
    loader = os.path.join(lab2_dir, "src", "document_loader.py")
    if os.path.exists(loader):
        mixed = '"lang"' not in open(loader, encoding="utf-8").read()
        report(not mixed, "document_loader separates category / lang" if not mixed else
               "document_loader keeps '| ภาษา: ...' inside category (Problem 5)")

    # secrets
    gi = os.path.join(lab2_dir, ".gitignore")
    ignored = os.path.exists(gi) and ".env" in open(gi, encoding="utf-8").read().split()
    report(ignored, ".env is in .gitignore" if ignored else ".env NOT ignored -> API key may be pushed to GitHub")

    # token length (Problem 2) - only if the model is installed
    store = os.path.join(lab2_dir, "vector_db", "chunk_store.json")
    if importlib.util.find_spec("sentence_transformers") and os.path.exists(store):
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        chunks = json.load(open(store, encoding="utf-8"))
        lens = [len(model.tokenizer(c["text"])["input_ids"]) for c in chunks]
        over = sum(l > model.max_seq_length for l in lens)
        report(over == 0, f"tokens per chunk {min(lens)}-{max(lens)}, max_seq_length={model.max_seq_length}, "
                          f"{over}/{len(lens)} chunks truncated (Problem 2)")
    else:
        print("  - token-length check skipped (needs sentence-transformers + vector_db/chunk_store.json)")


def run(lab2_dir=None):
    data = load_qa()
    print("Part A: 4 bugs commonly found in RAG scripts (BUGGY vs FIXED)")
    bug1_encoding()
    bug2_off_by_one(data)
    bug3_misaligned_store(data)
    bug4_stale_index(data)

    lab2_dir = lab2_dir or os.environ.get("LAB2_DIR") or os.path.join(HERE, "..", "LAB2-RAG-LLM")
    rag_doctor(os.path.abspath(lab2_dir))

    print("\nCause: most RAG failures are script/config bugs (encoding, slicing, ordering, stale files),")
    print("not model problems -> add sanity checks and assertions to every stage of the pipeline")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else None)

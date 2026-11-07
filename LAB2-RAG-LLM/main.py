"""
main.py — LAB 2: RAG + LLM chatbot (motorcycle knowledge base)

Flow:  question -> (memory/query transform) -> hybrid retrieval (BM25 + dense)
       -> (rerank) -> LLM generates answer with citations [1] [2]

Run:   python main.py
Turn features on/off in config.py (USE_LLM, USE_HYBRID, USE_RERANK, ...)
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import config
from src.index_meta import is_index_stale


def ensure_index():
    """main.py loads index_meta -> checks dataset -> builds a new index if needed"""
    stale, reason = is_index_stale(config)
    if stale:
        print(f"[index] Index needs rebuilding ({reason})")
        from build_index import build_index
        build_index(config)
    else:
        print(f"[index] Using existing index ({reason})")


def print_flags():
    flags = ["USE_HYBRID", "USE_RERANK", "USE_QUERY_TRANSFORM", "USE_MEMORY", "USE_LLM", "SHOW_DEBUG"]
    print("Flags: " + " | ".join(f"{f}={getattr(config, f)}" for f in flags))


def print_result(result):
    print(f"\n🤖 {result['answer']}")

    print("\nแหล่งอ้างอิง:")
    for i, c in enumerate(result["sources"], start=1):
        print(f"  [{i}] {c['question']}  (หมวด: {c['category']}, บรรทัด {c['line_no']})")

    if config.SHOW_DEBUG:
        d = result["debug"]
        print("\n[debug] standalone query:", d["standalone"])
        if len(d["queries"]) > 1 or d["queries"][0] != d["standalone"]:
            print("[debug] queries:", d["queries"])
        if d["hyde"]:
            print("[debug] HyDE:", d["hyde"][:200])
        for i, c in enumerate(result["sources"], start=1):
            scores = {k: round(v, 4) for k, v in c.items() if k.endswith("score")}
            print(f"[debug] [{i}] chunk {c['chunk_id']} {scores}")


def main():
    ensure_index()

    from src.rag_pipeline import RAGPipeline
    pipeline = RAGPipeline(config)

    print("\n--- ระบบ RAG + LLM: รถจักรยานยนต์ การดูแลรักษา และการขับขี่ ---")
    print_flags()
    print("พิมพ์ 'exit', 'quit' หรือ 'q' เพื่อออก | 'clear' เพื่อล้างประวัติการคุย\n")

    while True:
        try:
            query = input("\nไงพวก! 😎\nถามฉันมาได้เลย: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if query.lower() in ("exit", "quit", "q"):
            print("---- ยินดีรับใช้ !!! ----")
            break
        if query.lower() == "clear":
            pipeline.memory.clear()
            print("ล้างประวัติการคุยแล้ว")
            continue
        if not query:
            continue

        print_result(pipeline.ask(query))


if __name__ == "__main__":
    main()

"""
eval_generation.py — score answer quality (NO LLM judge)

For each golden item (natural + slang queries) run the full RAG pipeline and score:
  faithfulness : coverage of answer bigrams inside the retrieved context
  correctness  : char-bigram F1 between answer and gold answer
  relevance    : cosine similarity (embedding) between question and answer
  citation     : answer contains [n]

If USE_LLM = False the pipeline returns the retrieved answer (non-LLM mode) —
useful as a baseline to compare against the LLM.

Run:  python -m evaluation.eval_generation            (all natural + slang queries)
      python -m evaluation.eval_generation --limit 10 (save API quota)
Output: outputs/eval_generation.json
"""

import json
import os
import sys
import time

import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from evaluation.metrics import average, coverage, has_citation, token_f1
from src.index_meta import is_index_stale
from src.rag_pipeline import RAGPipeline


def main():
    stale, reason = is_index_stale(config)
    if stale:
        sys.exit(f"Index is stale ({reason}). Run: python build_index.py")
    with open(config.GOLDEN_SET_FILE, "r", encoding="utf-8") as f:
        golden = json.load(f)

    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    config.USE_MEMORY = False          # every question is independent
    pipe = RAGPipeline(config)
    emb = pipe.retriever.dense.embedding_model
    mode = "llm" if pipe.generator else "non-llm"

    cases = [(it, q) for it in golden for q in it["queries"] if q["type"] in ("natural", "slang")]
    if limit:
        cases = cases[:limit]

    rows = []
    for i, (item, q) in enumerate(cases, start=1):
        res = pipe.ask(q["query"])
        context = " ".join(c["answer"] for c in res["sources"])
        qv, av = emb.encode_query(q["query"]), emb.encode_query(res["answer"])
        scores = {
            "faithfulness": round(coverage(res["answer"], context), 4),
            "correctness": round(token_f1(res["answer"], item["gold_answer"]), 4),
            "relevance": round(float(np.dot(qv, av)), 4),
            "citation": has_citation(res["answer"]),
        }
        rows.append({"item_id": item["item_id"], "type": q["type"], "query": q["query"],
                     "answer": res["answer"], "gold_answer": item["gold_answer"], **scores})
        print(f"[{i}/{len(cases)}] {scores}")
        if pipe.generator and config.LLM_PROVIDER != "ollama":
            time.sleep(1)   # be gentle with free-tier rate limits

    summary = average([{k: r[k] for k in ("faithfulness", "correctness", "relevance", "citation")}
                       for r in rows])
    report = {"mode": mode, "provider": config.LLM_PROVIDER if pipe.generator else None,
              "n": len(rows), "summary": summary, "results": rows}

    print(f"\nMode: {mode}   Summary: {summary}")
    with open(config.EVAL_GENERATION_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Saved to: {config.EVAL_GENERATION_FILE}")


if __name__ == "__main__":
    main()

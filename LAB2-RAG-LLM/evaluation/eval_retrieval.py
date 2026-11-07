"""
eval_retrieval.py — compare 4 retrieval configurations on the golden set
    dense -> bm25 -> hybrid -> hybrid+rerank
Metrics: Hit@k, Recall@k, Precision@k, MRR, nDCG@k  (k = TOP_K)
No LLM is used here (query transform OFF) so results are reproducible.

Run:  python -m evaluation.eval_retrieval
      python -m evaluation.eval_retrieval --no-rerank   (skip the heavy cross-encoder)
Output: outputs/eval_retrieval.json
"""

import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from evaluation.metrics import average, retrieval_scores
from src.hybrid_retriever import HybridRetriever
from src.index_meta import is_index_stale


def relevant_ids(chunks, source_question):
    return {c["qa_id"] for c in chunks if c["question"] == source_question}


def evaluate(run_fn, golden, chunks, k):
    per_type, all_scores, rows = {}, [], []
    for item in golden:
        rel = relevant_ids(chunks, item["source_question"])
        for q in item["queries"]:
            results = run_fn(q["query"])
            retrieved = [r["qa_id"] for r in results]
            s = retrieval_scores(retrieved, rel, k)
            all_scores.append(s)
            per_type.setdefault(q["type"], []).append(s)
            rows.append({"item_id": item["item_id"], "type": q["type"], "query": q["query"],
                         "retrieved_qa_ids": retrieved[:k], "relevant": sorted(rel),
                         "hit": s[f"hit@{k}"]})
    return {
        "overall": average(all_scores),
        "by_type": {t: average(v) for t, v in per_type.items()},
        "n_queries": len(all_scores),
        "misses": [r for r in rows if r["hit"] == 0.0],
    }


def main():
    stale, reason = is_index_stale(config)
    if stale:
        sys.exit(f"Index is stale ({reason}). Run: python build_index.py")
    if not os.path.exists(config.GOLDEN_SET_FILE):
        sys.exit("golden_set.json not found. Run: python -m evaluation.build_golden_set")

    with open(config.GOLDEN_SET_FILE, "r", encoding="utf-8") as f:
        golden = json.load(f)

    k = config.TOP_K
    hr = HybridRetriever(config.EMBEDDING_MODEL_NAME, config.FAISS_INDEX_FILE,
                         config.CHUNK_STORE_FILE, config.BM25_INDEX_FILE, rrf_k=config.RRF_K)
    chunks = hr.chunks

    configs = {
        "dense": lambda q: hr.retrieve(q, k, mode="dense"),
        "bm25": lambda q: hr.retrieve(q, k, mode="bm25"),
        "hybrid": lambda q: hr.retrieve(q, k, mode="hybrid"),
    }
    if "--no-rerank" not in sys.argv:
        try:
            from src.rerankers import CrossEncoderReranker
            rr = CrossEncoderReranker(config.RERANKER_MODEL_NAME)
            configs["hybrid+rerank"] = lambda q: rr.rerank(
                q, hr.retrieve(q, config.CANDIDATE_K, mode="hybrid"), k)
        except Exception as e:  # model download failed, out of memory, ...
            print(f"[warn] skip hybrid+rerank: {e}")

    report = {"k": k, "golden_items": len(golden), "configs": {}}
    for name, fn in configs.items():
        print(f"Evaluating: {name} ...")
        report["configs"][name] = evaluate(fn, golden, chunks, k)

    print(f"\n{'config':<15}" + "".join(f"{m:>13}" for m in report['configs']['dense']['overall']))
    for name, res in report["configs"].items():
        print(f"{name:<15}" + "".join(f"{v:>13.4f}" for v in res["overall"].values()))

    print(f"\nHit@{k} by query type:")
    types = list(report["configs"]["dense"]["by_type"])
    print(f"{'config':<15}" + "".join(f"{t:>11}" for t in types))
    for name, res in report["configs"].items():
        print(f"{name:<15}" + "".join(f"{res['by_type'][t][f'hit@{k}']:>11.3f}" for t in types))

    with open(config.EVAL_RETRIEVAL_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to: {config.EVAL_RETRIEVAL_FILE}")


if __name__ == "__main__":
    main()

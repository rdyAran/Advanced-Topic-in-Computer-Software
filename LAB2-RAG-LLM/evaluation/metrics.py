"""
metrics.py — retrieval & generation metrics (pure Python, no LLM judge)

Retrieval (relevance judged at Q&A level: qa_id):
  Hit@k, Recall@k, Precision@k, MRR, nDCG@k
Generation (lexical, character-bigram based so it works with Thai):
  token_f1, coverage (faithfulness proxy)

Self-test:  python -m evaluation.metrics
"""

import math
import re


def _dedup(seq):
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def hit_at_k(retrieved, relevant, k):
    return 1.0 if any(r in relevant for r in retrieved[:k]) else 0.0


def recall_at_k(retrieved, relevant, k):
    if not relevant:
        return 0.0
    return len(set(_dedup(retrieved)[:k]) & set(relevant)) / len(set(relevant))


def precision_at_k(retrieved, relevant, k):
    top = _dedup(retrieved)[:k]
    if not top:
        return 0.0
    return sum(1 for r in top if r in relevant) / k


def mrr(retrieved, relevant):
    for rank, r in enumerate(retrieved, start=1):
        if r in relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved, relevant, k):
    top = _dedup(retrieved)[:k]
    dcg = sum(1.0 / math.log2(i + 2) for i, r in enumerate(top) if r in relevant)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(set(relevant)), k)))
    return dcg / ideal if ideal else 0.0


def retrieval_scores(retrieved, relevant, k):
    return {
        f"hit@{k}": hit_at_k(retrieved, relevant, k),
        f"recall@{k}": recall_at_k(retrieved, relevant, k),
        f"precision@{k}": precision_at_k(retrieved, relevant, k),
        "mrr": mrr(retrieved, relevant),
        f"ndcg@{k}": ndcg_at_k(retrieved, relevant, k),
    }


def average(dicts):
    if not dicts:
        return {}
    return {k: round(sum(d[k] for d in dicts) / len(dicts), 4) for k in dicts[0]}


# ---------------- generation ----------------
_CITATION = re.compile(r"\[\d+\]")
_KEEP = re.compile(r"[฀-๿a-z0-9]+")


def char_bigrams(text):
    text = _CITATION.sub(" ", text.lower())
    grams = []
    for seg in _KEEP.findall(text):
        grams.extend(seg[i:i + 2] for i in range(max(len(seg) - 1, 1)))
    return grams


def token_f1(prediction, reference):
    p, r = char_bigrams(prediction), char_bigrams(reference)
    if not p or not r:
        return 0.0
    rc = {}
    for g in r:
        rc[g] = rc.get(g, 0) + 1
    common = 0
    for g in p:
        if rc.get(g, 0) > 0:
            common += 1
            rc[g] -= 1
    if common == 0:
        return 0.0
    prec, rec = common / len(p), common / len(r)
    return 2 * prec * rec / (prec + rec)


def coverage(answer, context):
    """fraction of answer bigrams that appear in the context (faithfulness proxy)"""
    a = char_bigrams(answer)
    if not a:
        return 0.0
    ctx = set(char_bigrams(context))
    return sum(1 for g in a if g in ctx) / len(a)


def has_citation(answer):
    return 1.0 if _CITATION.search(answer) else 0.0


# ---------------- self-test ----------------
def _self_test():
    ret, rel = [3, 1, 7], {1}
    assert hit_at_k(ret, rel, 1) == 0.0 and hit_at_k(ret, rel, 3) == 1.0
    assert mrr(ret, rel) == 0.5
    assert recall_at_k(ret, rel, 3) == 1.0
    assert abs(precision_at_k(ret, rel, 3) - 1 / 3) < 1e-9
    assert abs(ndcg_at_k(ret, rel, 3) - 1 / math.log2(3)) < 1e-9
    assert ndcg_at_k([1], {1}, 3) == 1.0
    assert mrr([], {1}) == 0.0
    assert token_f1("เปลี่ยนน้ำมันเครื่อง", "เปลี่ยนน้ำมันเครื่อง") == 1.0
    assert token_f1("abc", "xyz") == 0.0
    assert coverage("น้ำมัน [1]", "เปลี่ยนน้ำมันเครื่อง") == 1.0
    assert has_citation("ตอบ [2]") == 1.0 and has_citation("ตอบ") == 0.0
    print("metrics self-test: all passed ✅")


if __name__ == "__main__":
    _self_test()

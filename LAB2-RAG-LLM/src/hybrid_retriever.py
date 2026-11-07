"""
hybrid_retriever.py
-------------------
BM25 (exact-token search) + dense (semantic search) fused with
Reciprocal Rank Fusion (RRF):

    RRF(d) = sum over retrievers of  1 / (RRF_K + rank(d))

BM25 is implemented here (no extra package). Thai has no spaces between
words, so Thai text is tokenised into character bigrams; Latin words / numbers
are kept as whole tokens (e.g. "ABS", "e20", "cvt").
"""

import math
import pickle
import re
from collections import Counter

from src.retriever import Retriever

_THAI = re.compile(r"[฀-๿]+")
_LATIN = re.compile(r"[a-z0-9]+(?:[.\-][a-z0-9]+)*")


def tokenize(text):
    text = text.lower()
    tokens = _LATIN.findall(text)
    for seg in _THAI.findall(text):
        if len(seg) == 1:
            tokens.append(seg)
        else:
            tokens.extend(seg[i:i + 2] for i in range(len(seg) - 1))
    return tokens


class BM25:
    def __init__(self, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b

    def fit(self, texts):
        self.docs = [Counter(tokenize(t)) for t in texts]
        self.doc_len = [sum(d.values()) for d in self.docs]
        self.avgdl = sum(self.doc_len) / max(len(self.docs), 1)
        n = len(self.docs)
        df = Counter()
        for d in self.docs:
            df.update(d.keys())
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        return self

    def scores(self, query):
        q = tokenize(query)
        out = []
        for d, dl in zip(self.docs, self.doc_len):
            s = 0.0
            for t in q:
                tf = d.get(t)
                if not tf:
                    continue
                s += self.idf[t] * tf * (self.k1 + 1) / (
                    tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            out.append(s)
        return out

    def search(self, query, top_k):
        s = self.scores(query)
        order = sorted(range(len(s)), key=lambda i: s[i], reverse=True)
        return [(i, s[i]) for i in order[:top_k] if s[i] > 0]

    def save(self, path):
        with open(path, "wb") as f:
            pickle.dump(self, f)
        print(f"[bm25] Saved BM25 index to: {path}")

    @staticmethod
    def load(path):
        with open(path, "rb") as f:
            return pickle.load(f)


def build_bm25(chunks, path):
    """called from build_index.py"""
    bm25 = BM25().fit([c["text"] for c in chunks])
    bm25.save(path)
    return bm25


def rrf_fuse(ranked_lists, rrf_k=60):
    """ranked_lists: list of lists of chunk_id (best first) -> {chunk_id: rrf score}"""
    fused = {}
    for ranked in ranked_lists:
        for rank, cid in enumerate(ranked, start=1):
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (rrf_k + rank)
    return fused


class HybridRetriever:
    def __init__(self, model_name, index_path, chunk_store_path, bm25_path,
                 rrf_k=60, use_hybrid=True):
        self.dense = Retriever(model_name, index_path, chunk_store_path)
        self.chunks = self.dense.chunks
        self.bm25 = BM25.load(bm25_path)
        self.rrf_k = rrf_k
        self.use_hybrid = use_hybrid

    def retrieve_bm25(self, query, top_k):
        results = []
        for idx, s in self.bm25.search(query, top_k):
            c = dict(self.chunks[idx])
            c["score"] = float(s)
            c["bm25_score"] = float(s)
            results.append(c)
        return results

    def fuse(self, result_lists, top_k):
        """RRF over several result lists (dense, bm25, multi-query ...)"""
        fused = rrf_fuse([[r["chunk_id"] for r in lst] for lst in result_lists], self.rrf_k)
        info = {}
        for lst in result_lists:
            for r in lst:
                info.setdefault(r["chunk_id"], {}).update(
                    {k: v for k, v in r.items() if k.endswith("_score")})
        out = []
        for cid, s in sorted(fused.items(), key=lambda x: x[1], reverse=True)[:top_k]:
            c = dict(self.chunks[cid])
            c.update(info.get(cid, {}))
            c["score"] = s
            c["rrf_score"] = s
            out.append(c)
        return out

    def retrieve(self, query, top_k=20, query_vector=None, mode=None):
        """
        mode: "dense" | "bm25" | "hybrid"  (default from use_hybrid)
        query_vector: optional pre-computed vector (HyDE)
        """
        mode = mode or ("hybrid" if self.use_hybrid else "dense")
        if query_vector is None and mode != "bm25":
            query_vector = self.dense.embedding_model.encode_query(query)

        if mode == "dense":
            return self.dense.search_vector(query_vector, top_k)
        if mode == "bm25":
            return self.retrieve_bm25(query, top_k)

        dense = self.dense.search_vector(query_vector, top_k)
        sparse = self.retrieve_bm25(query, top_k)
        return self.fuse([dense, sparse], top_k)

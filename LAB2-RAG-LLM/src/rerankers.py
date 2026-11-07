"""
rerankers.py
------------
Cross-encoder re-ranking: reads (query, chunk) together, so it judges relevance
more accurately than vector similarity. Used as  20 candidates -> top 3.
OFF by default (USE_RERANK) because the model is large (~2 GB).
"""

_CACHE = {}


class CrossEncoderReranker:
    def __init__(self, model_name):
        from sentence_transformers import CrossEncoder
        if model_name not in _CACHE:
            print(f"[reranker] Loading cross-encoder: {model_name} ...")
            _CACHE[model_name] = CrossEncoder(model_name, max_length=512)
        self.model = _CACHE[model_name]

    def rerank(self, query, chunks, top_k=3):
        if not chunks:
            return []
        pairs = [(query, c["text"]) for c in chunks]
        scores = self.model.predict(pairs, show_progress_bar=False)
        out = []
        for c, s in zip(chunks, scores):
            c = dict(c)
            c["rerank_score"] = float(s)
            c["score"] = float(s)
            out.append(c)
        out.sort(key=lambda c: c["rerank_score"], reverse=True)
        return out[:top_k]

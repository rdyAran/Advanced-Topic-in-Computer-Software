"""
embedding_model.py
------------------
Wrap sentence-transformers. The model is cached so it is loaded only once,
even when retriever / reranker / evaluation all need it.
"""

from sentence_transformers import SentenceTransformer

_MODEL_CACHE = {}


class EmbeddingModel:
    def __init__(self, model_name):
        if model_name not in _MODEL_CACHE:
            print(f"[embedding_model] Loading model: {model_name} ...")
            _MODEL_CACHE[model_name] = SentenceTransformer(model_name)
            print("[embedding_model] Model loaded successfully.")
        self.model = _MODEL_CACHE[model_name]

    def encode(self, texts, show_progress=True):
        """list of texts -> numpy array (n_texts, dim), L2-normalised"""
        return self.model.encode(
            texts,
            show_progress_bar=show_progress,
            normalize_embeddings=True,
        )

    def encode_query(self, query_text):
        """single query -> vector (dim,)"""
        return self.model.encode([query_text], normalize_embeddings=True)[0]

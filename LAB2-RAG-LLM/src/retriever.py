"""
retriever.py
------------
Dense-only retrieval (baseline from LAB 1):
query -> embedding -> FAISS similarity search -> top-k chunks
"""

from src.embedding_model import EmbeddingModel
from src.vector_store import VectorStore, load_chunk_store


class Retriever:
    def __init__(self, model_name, index_path, chunk_store_path):
        self.embedding_model = EmbeddingModel(model_name)
        self.vector_store = VectorStore()
        self.vector_store.load(index_path)
        self.chunks = load_chunk_store(chunk_store_path)

    def search_vector(self, query_vector, top_k=3):
        """search with a ready-made vector (used by HyDE)"""
        top_k = min(top_k, len(self.chunks))
        scores, indices = self.vector_store.search(query_vector, top_k)
        results = []
        for score, idx in zip(scores, indices):
            if idx == -1:
                continue
            chunk = dict(self.chunks[idx])
            chunk["score"] = float(score)
            chunk["dense_score"] = float(score)
            results.append(chunk)
        return results

    def retrieve(self, query, top_k=3):
        query_vector = self.embedding_model.encode_query(query)
        return self.search_vector(query_vector, top_k)

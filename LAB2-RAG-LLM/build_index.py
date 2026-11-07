"""
build_index.py — build ALL indexes with one command.

  data/*.txt -> document_loader -> text_splitter -> embedding_model
             -> vector_store (FAISS)  +  BM25
             -> vector_db/{document.index, bm25_index.pkl, chunk_store.json, index_meta.json}

Run:  python build_index.py
(main.py also calls this automatically when the data file changes)
"""

import json
import os
import sys

import numpy as np

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import config
from src.document_loader import load_qa_file
from src.embedding_model import EmbeddingModel
from src.hybrid_retriever import build_bm25
from src.index_meta import save_index_meta
from src.text_splitter import build_chunks
from src.vector_store import VectorStore, save_chunk_store


def build_index(cfg=config):
    print("=== BUILD INDEX ===")
    print(f"[1/5] Load knowledge base: {cfg.SOURCE_FILE}")
    records = load_qa_file(cfg.SOURCE_FILE)
    print(f"      {len(records)} Q&A records")
    with open(cfg.EXTRACTED_TEXT_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print("[2/5] Split into chunks")
    chunks = build_chunks(records, cfg.CHUNK_SIZE, cfg.CHUNK_OVERLAP)
    print(f"      {len(chunks)} chunks")
    with open(cfg.CHUNKS_FILE, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    print("[3/5] Create embeddings")
    model = EmbeddingModel(cfg.EMBEDDING_MODEL_NAME)
    embeddings = model.encode([c["text"] for c in chunks])
    np.save(cfg.EMBEDDINGS_FILE, embeddings)
    print(f"      shape = {embeddings.shape}")

    print("[4/5] Build FAISS + BM25")
    store = VectorStore()
    store.build_index(embeddings)
    store.save(cfg.FAISS_INDEX_FILE)
    build_bm25(chunks, cfg.BM25_INDEX_FILE)
    save_chunk_store(chunks, cfg.CHUNK_STORE_FILE)

    print("[5/5] Save index_meta (dataset fingerprint)")
    save_index_meta(cfg, {"num_records": len(records), "num_chunks": len(chunks),
                          "embedding_dim": int(embeddings.shape[1])})
    print("=== DONE ===")


if __name__ == "__main__":
    build_index()

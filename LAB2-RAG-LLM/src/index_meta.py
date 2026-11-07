"""
index_meta.py
-------------
Save a "fingerprint" of the dataset that the index was built from.
main.py compares it with the current data file + config; if anything changed
(e.g. you replaced the .txt file) the index is stale and is rebuilt.
This prevents the "still answering from the old data" problem.
"""

import hashlib
import json
import os


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def current_fingerprint(cfg):
    return {
        "source_file": os.path.basename(cfg.SOURCE_FILE),
        "source_sha256": file_sha256(cfg.SOURCE_FILE),
        "chunk_size": cfg.CHUNK_SIZE,
        "chunk_overlap": cfg.CHUNK_OVERLAP,
        "embedding_model": cfg.EMBEDDING_MODEL_NAME,
    }


def save_index_meta(cfg, extra=None):
    meta = current_fingerprint(cfg)
    meta.update(extra or {})
    with open(cfg.INDEX_META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"[index_meta] Saved: {cfg.INDEX_META_FILE}")
    return meta


def load_index_meta(cfg):
    if not os.path.exists(cfg.INDEX_META_FILE):
        return None
    with open(cfg.INDEX_META_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def is_index_stale(cfg):
    """Return (stale: bool, reason: str)."""
    needed = [cfg.FAISS_INDEX_FILE, cfg.BM25_INDEX_FILE,
              cfg.CHUNK_STORE_FILE, cfg.INDEX_META_FILE]
    missing = [p for p in needed if not os.path.exists(p)]
    if missing:
        return True, "missing: " + ", ".join(os.path.basename(p) for p in missing)

    saved = load_index_meta(cfg)
    now = current_fingerprint(cfg)
    for key, value in now.items():
        if saved.get(key) != value:
            return True, f"'{key}' changed ({saved.get(key)} -> {value})"
    return False, "up to date"

# -*- coding: utf-8 -*-
# Problem 08: Analyzing the Configuration of a RAG system that uses motorcycle_qa.txt as its knowledge base
# CONFIG below mirrors LAB 2 config.py; validate() lists the configuration problems found in LAB 2
import hashlib
import os

from data_loader import DATA_PATH, load_qa, section

CONFIG = {
    "SOURCE_FILE": "motorcycle_qa.txt",
    "USE_HYBRID": True,
    "USE_RERANK": False,
    "USE_QUERY_TRANSFORM": False,
    "USE_MEMORY": True,
    "USE_LLM": True,
    "SHOW_DEBUG": False,
    "TOP_K": 3,
    "MIN_SCORE": 0.0,
    "LLM_PROVIDER": "gemini",
    "LLM_MODEL": "gemini-2.5-flash",
    "API_KEY_SET": False,
}

# fingerprint saved when the index was built (LAB 1: built from the computer-hardware file com_h.txt)
SAVED_INDEX_META = {"source_file": "com_h.txt", "source_sha256": "<hash of com_h.txt>"}

DEPRECATED_MODELS = {"gemini-2.5-flash"}     # returned HTTP 404 "no longer available to new users"


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def describe(cfg, n_docs):
    steps = []
    if cfg["USE_MEMORY"]:
        steps.append("Using Conversation Memory")
    if cfg["USE_QUERY_TRANSFORM"]:
        steps.append("Query Transform (rewrite / multi / HyDE)")
    steps.append(f"{'BM25 + Dense (RRF)' if cfg['USE_HYBRID'] else 'Dense'} Retrieval on {n_docs} documents")
    steps.append(f"{'Performing' if cfg['USE_RERANK'] else 'Not performing'} Re-ranking")
    steps.append(f"Generating the answer with {cfg['LLM_PROVIDER']} / {cfg['LLM_MODEL']}" if cfg["USE_LLM"]
                 else "No LLM: return the best retrieved answer")
    print("Pipeline:")
    for i, s in enumerate(steps, 1):
        print(f"{i}. {s}")


def validate(cfg):
    issues = []
    if not os.path.exists(os.path.join(os.path.dirname(DATA_PATH), cfg["SOURCE_FILE"])):
        issues.append(f"SOURCE_FILE '{cfg['SOURCE_FILE']}' not found")
    if SAVED_INDEX_META["source_file"] != cfg["SOURCE_FILE"] or \
            SAVED_INDEX_META["source_sha256"] != sha256(DATA_PATH):
        issues.append(f"Stale index: built from '{SAVED_INDEX_META['source_file']}', "
                      f"config uses '{cfg['SOURCE_FILE']}' -> answers come from OLD data")
    if cfg["USE_LLM"] and cfg["LLM_MODEL"] in DEPRECATED_MODELS:
        issues.append(f"LLM_MODEL '{cfg['LLM_MODEL']}' is deprecated -> HTTP 404")
    if cfg["USE_LLM"] and cfg["LLM_PROVIDER"] in ("gemini", "openai") and not cfg["API_KEY_SET"]:
        issues.append("USE_LLM=True but no API key in .env -> LLM silently disabled")
    if cfg["USE_QUERY_TRANSFORM"] and not cfg["USE_LLM"]:
        issues.append("USE_QUERY_TRANSFORM needs USE_LLM=True (it is silently skipped)")
    if cfg["MIN_SCORE"] <= 0:
        issues.append("MIN_SCORE=0 (and unused in LAB 2) -> irrelevant context always reaches the LLM")
    if cfg["TOP_K"] == 1 and not cfg["USE_RERANK"]:
        issues.append("TOP_K=1 without re-ranking -> a correct answer at rank 2 is lost")
    return issues


def run():
    data = load_qa()
    print("CONFIG =", CONFIG)
    print(f"Loaded Knowledge Base from {CONFIG['SOURCE_FILE']}: {len(data)} Q&A entries\n")
    describe(CONFIG, len(data))

    print("\nvalidate(CONFIG):")
    for i in validate(CONFIG):
        print("  ✗", i)

    fixed = dict(CONFIG, LLM_MODEL="gemini-3.8-flash", API_KEY_SET=True, MIN_SCORE=0.35)
    SAVED_INDEX_META.update(source_file=CONFIG["SOURCE_FILE"], source_sha256=sha256(DATA_PATH))
    print("\nAfter fixing model name, .env key, MIN_SCORE and rebuilding the index:")
    for i in validate(fixed) or ["✓ no configuration issues"]:
        print("  ", i)

    section("Found in LAB 2 (errors that actually happened)")
    rows = [
        ("Answers about computers after switching data", "old SOURCE_FILE + stale vector_db/", "index_meta.json fingerprint -> auto rebuild"),
        ("ModuleNotFoundError: sentence_transformers", "pip installed into another Python", "python -m pip install -r requirements.txt"),
        ("HTTP 404 model no longer available", "deprecated model name", "model name in .env"),
        ("HTTP 503 high demand", "server busy", "retry + backoff + fallback model"),
        ("HTTP 429 quota exceeded", "free-tier quota / model not free", "switch model or LLM_PROVIDER=ollama"),
        ("WinError 10061", "Ollama not installed/running", "install Ollama, ollama pull qwen2.5:7b"),
    ]
    for symptom, cause, fix in rows:
        print(f"- {symptom}\n    cause: {cause}\n    fix  : {fix}")
    print("\nThe system's behavior results from the Config: every one of these bugs was a config problem, not an algorithm problem")


if __name__ == "__main__":
    run()

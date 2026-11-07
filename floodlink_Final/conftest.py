"""Lets pytest (run from repo root) import every module: floodcommon, api, agent, floodnlp."""
import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
for p in ["common", "02_api_backend", "03_intake_ai_agent", "04_flood_nlp_model", "06_chat_assistant"]:
    sys.path.insert(0, str(ROOT / p))

# tests are written for the small v1 model; WangchanBERTa is tested with a stub (03_intake_ai_agent/tests/test_wcb_provider.py)
os.environ.setdefault("OWN_MODEL", "v1")

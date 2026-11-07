"""Talks to the 03 Intake AI Agent service over HTTP (same .run()/.last interface as the local agent)."""
import os
import httpx
from floodcommon.schemas import Extraction


class AgentClient:
    def __init__(self, url: str | None = None, timeout: float = 90):
        self.url = (url or os.getenv("AGENT_URL", "http://agent:8001")).rstrip("/")
        self.http = httpx.Client(timeout=timeout)
        self.last = {}

    def run(self, text: str) -> Extraction:
        r = self.http.post(f"{self.url}/extract", json={"text": text})
        r.raise_for_status()
        data = r.json()
        self.last = {k: v for k, v in data.items() if k != "extraction"}
        return Extraction.model_validate(data["extraction"])

    def split(self, text: str) -> dict:
        try:
            r = self.http.post(f"{self.url}/split", json={"text": text})
            r.raise_for_status()
            return r.json()
        except Exception as e:      # splitting is a convenience — never block intake on it
            return {"segments": [text], "method": "none", "note": f"split unavailable: {e}"}

    def llm_json(self, system: str, user: str) -> dict:
        r = self.http.post(f"{self.url}/llm/json", json={"system": system, "user": user}, timeout=40)
        r.raise_for_status()
        return r.json()

    def health(self) -> dict:
        try:
            return self.http.get(f"{self.url}/health", timeout=5).json()
        except Exception as e:
            return {"ok": False, "error": str(e)}

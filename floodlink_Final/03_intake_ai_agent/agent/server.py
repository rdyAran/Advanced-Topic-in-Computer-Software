"""03 Intake AI Agent — HTTP service.  POST /extract {text} -> extraction + who decided + confidence."""
import logging
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from .router import IntakeAgent

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="FloodLink Intake AI Agent", version="0.2.0")
agent = IntakeAgent()


class ExtractIn(BaseModel):
    text: str


@app.get("/health")
def health():
    return {"ok": True, **agent.describe()}


@app.post("/extract")
def extract(body: ExtractIn):
    try:
        e = agent.run(body.text)
    except Exception as err:
        raise HTTPException(503, f"agent failed: {err}")
    return {"extraction": e.model_dump(mode="json"), **agent.last}


@app.post("/split")
def split(body: ExtractIn):
    """Split one submitted text into separate cases."""
    return agent.split(body.text)


class JsonIn(BaseModel):
    system: str
    user: str


@app.post("/llm/json")
def llm_json(body: JsonIn):
    """Generic JSON completion through the LLM chain (used by the chatbot for intent + grounded KB answers)."""
    if agent.llm is None or not hasattr(agent.llm, "complete_json"):
        raise HTTPException(503, "no LLM configured")
    try:
        return agent.llm.complete_json(body.system, body.user)
    except Exception as err:
        raise HTTPException(503, f"LLM failed: {err}")

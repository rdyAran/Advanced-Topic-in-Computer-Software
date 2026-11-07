import json
import pytest
from agent.groq import GroqProvider, to_strict_schema
from agent.router import LLMChain, IntakeAgent
from floodcommon.schemas import Extraction

ANSWER = {"message_type": "help_request", "area": "คอหงส์", "street": None, "landmark": None, "house_no": None, "adults": 1,
          "children_ages": [], "elderly_ages": [85], "flags": ["bedridden"], "water_level": "floor2", "days_trapped": None,
          "needs": [], "contact": None, "summary": "ยาย 85 ติดเตียง น้ำถึงชั้น 2"}


def ok(_payload):
    return {"choices": [{"message": {"content": json.dumps(ANSWER, ensure_ascii=False)}}]}


def test_strict_schema_shape():
    s = to_strict_schema(Extraction)
    assert s["additionalProperties"] is False and set(s["required"]) == set(s["properties"])
    assert "$ref" not in json.dumps(s) and '"default"' not in json.dumps(s)
    assert {"type": "null"} in s["properties"]["water_level"]["anyOf"]


def test_groq_strict_payload_and_parse():
    g = GroqProvider(api_key="x", model="openai/gpt-oss-120b")
    sent = []
    g._post = lambda p: (sent.append(p), ok(p))[1]
    e = g.extract("ยายอายุ 85 ติดเตียง")
    assert e.flags[0].value == "bedridden" and sent[0]["response_format"]["type"] == "json_schema"
    assert sent[0]["reasoning_effort"] == "low"


def test_groq_falls_back_to_json_object_when_strict_rejected():
    g = GroqProvider(api_key="x", model="openai/gpt-oss-120b")
    calls = []
    def post(p):
        calls.append(p["response_format"]["type"])
        if p["response_format"]["type"] == "json_schema":
            raise RuntimeError("400 response_format json_schema not supported for this model")
        return ok(p)
    g._post = post
    assert g.extract("x").water_level.value == "floor2" and calls == ["json_schema", "json_object"]


def test_groq_non_strict_model_puts_schema_in_prompt():
    g = GroqProvider(api_key="x", model="some/other-model")
    p = g._payload("x")
    assert p["response_format"] == {"type": "json_object"} and "schema" in p["messages"][0]["content"]
    assert "reasoning_effort" not in p


class Down:
    name, model = "gemini", "gemini-3.5-flash"
    def __init__(self): self.calls = 0
    def extract(self, text):
        self.calls += 1; raise RuntimeError("503 UNAVAILABLE")


def test_chain_fails_over_and_circuit_breaker_skips_down_provider():
    g = GroqProvider(api_key="x", interactive=True); g.name = "groq"; g._post = ok
    gem = Down()
    chain = LLMChain([gem, g], cooldown=60)
    assert chain.extract("x").flags[0].value == "bedridden" and chain.last_model.startswith("groq")
    chain.extract("y")
    assert gem.calls == 1          # skipped while in cool-down


def test_hybrid_reports_which_llm_answered():
    g = GroqProvider(api_key="x"); g.name = "groq"; g._post = ok
    a = IntakeAgent(strategy="hybrid", threshold=0.99, llm=LLMChain([Down(), g]), log_teacher=False)
    a.run("แม่นอนป่วย น้ำขึ้นชั้นบน คอหงส์")
    assert a.last["escalated"] and a.last["provider_used"].startswith("groq")


def test_parse_failure_moves_to_next_mode():
    g = GroqProvider(api_key="x", model="openai/gpt-oss-120b")
    seen = []
    def post(p):
        seen.append((p["response_format"]["type"], p.get("reasoning_effort")))
        if len(seen) < 3:
            raise RuntimeError('400 {"error":{"message":"Parsing failed. The model generated output that could not be parsed.","code":"json_validate_failed"}}')
        return ok(p)
    g._post = post
    assert g.extract("x").flags[0].value == "bedridden"
    assert seen == [("json_schema", "low"), ("json_schema", "medium"), ("json_object", "low")]


def test_bad_json_in_object_mode_is_retried_then_fails_cleanly():
    g = GroqProvider(api_key="x", model="some/other-model")
    g._post = lambda p: {"choices": [{"message": {"content": '{"message_type": "nonsense"}'}}]}
    with pytest.raises(RuntimeError, match="Groq failed"):
        g.extract("x")

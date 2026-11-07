"""WangchanBERTa adapter (own_model.WCBProvider) without torch: the Predictor is replaced by a stub."""
import floodwcb
from agent import own_model
from agent.router import IntakeAgent
from floodcommon.schemas import Extraction
from floodcommon.triage import priority


def _pred(**kw):
    base = {"message_type": "help_request", "flags": [], "needs": [], "water_level": None, "lost_contact": False,
            "insufficient_info": False, "priority": "green", "confidence": 0.9, "red_prob": 0.05, "rule_hits": []}
    return {**base, **kw}


class StubPredictor:
    queue = []

    def __init__(self, path, device=None, threads=None):
        self.cfg = {"version": "wcb-test+rules"}

    def predict(self, texts):
        return [StubPredictor.queue.pop(0) for _ in texts]


def _provider(monkeypatch, *preds):
    monkeypatch.setattr(floodwcb, "Predictor", StubPredictor, raising=False)
    StubPredictor.queue = list(preds)
    return own_model.WCBProvider(path="unused")


def test_critical_word_from_model_makes_the_case_red(monkeypatch):
    m = _provider(monkeypatch, _pred(priority="red", needs=["evacuation"], rule_hits=["help_cue", "critical:ทารก"]))
    e, conf = m.predict("ฝากตรงนี้ด้วยค่ะ มีเด็กทารก ซ.สังทิศ 2 โทร 081-234-5678")
    assert e.message_type.value == "help_request" and e.contact and e.street
    assert e.priority_hint == "red" and "ทารก" in e.priority_hint_reason
    color, reason = priority(e)
    assert color == "red" and reason.startswith("AI: พบคำวิกฤต")
    assert conf["rule_hits"] == ["help_cue", "critical:ทารก"]


def test_rules_still_win_when_they_are_more_urgent(monkeypatch):
    m = _provider(monkeypatch, _pred(flags=["dialysis"], priority="orange"))
    e, _ = m.predict("ยายฟอกไต")
    assert priority(e) == ("red", "ผู้ป่วยฟอกไต")


def test_new_flags_needs_and_lost_contact_are_kept(monkeypatch):
    m = _provider(monkeypatch, _pred(flags=["sick_now", "chronic_illness", "cannot_swim"], needs=["medical", "medicine"],
                                     lost_contact=True, water_level="floor1", priority="red"))
    e, _ = m.predict("แม่ไข้สูง มีโรคประจำตัว ว่ายน้ำไม่เป็น ติดต่อไม่ได้แล้ว")
    assert {f.value for f in e.flags} == {"sick_now", "chronic_illness", "cannot_swim"}
    assert {n.value for n in e.needs} == {"medical", "medicine"} and e.lost_contact
    assert priority(e)[0] == "red" and "ป่วยหนักตอนนี้" in e.summary


def test_non_help_message_has_no_colour_or_entities(monkeypatch):
    m = _provider(monkeypatch, _pred(message_type="irrelevant", flags=["heart"], priority="none"))
    e, _ = m.predict("ขอให้ทุกคนปลอดภัย โทร 081-234-5678")
    assert e.message_type.value == "irrelevant" and e.flags == [] and e.contact is None and e.priority_hint is None


def test_auto_falls_back_to_v1_without_the_exported_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(own_model, "WCB_DIR", tmp_path / "missing")
    monkeypatch.setenv("OWN_MODEL", "auto")
    m = own_model.load_own_model()
    assert m.kind == "v1"


def test_hybrid_keeps_critical_word_when_llm_answers(monkeypatch):
    class LLM:
        model = "fake"
        def extract(self, text):
            return Extraction(message_type="help_request", needs=["food"], summary="llm")
    m = _provider(monkeypatch, _pred(priority="red", confidence=0.1, rule_hits=["critical:ตัวซีด"]))
    a = IntakeAgent(strategy="hybrid", threshold=0.5, own=m, llm=LLM(), log_teacher=False)
    e = a.run("ช่วยด่วนได้ไหมคะ น้องตัวซีดแล้ว")
    assert a.last["escalated"] and e.summary == "llm" and priority(e)[0] == "red"


def test_llm_schemas_do_not_expose_the_model_hint():
    from agent.providers import to_gemini_schema
    from agent.groq import to_strict_schema
    for sch in (to_gemini_schema(Extraction), to_strict_schema(Extraction)):
        assert "priority_hint" not in sch["properties"] and "lost_contact" in sch["properties"]

from agent.router import IntakeAgent
from floodcommon.schemas import Extraction


class FakeLLM:
    model = "fake-gemini"
    def __init__(self, fail=False): self.fail, self.calls = fail, 0
    def extract(self, text):
        self.calls += 1
        if self.fail: raise RuntimeError("503 UNAVAILABLE")
        return Extraction(message_type="help_request", flags=["bedridden"], water_level="floor2", area="คอหงส์", summary="llm")


def agent(llm, threshold=0.7):
    return IntakeAgent(strategy="hybrid", threshold=threshold, llm=llm, log_teacher=False)


def test_confident_message_stays_on_own_model():
    llm = FakeLLM(); a = agent(llm, threshold=0.0)
    e = a.run("ช่วยด้วยค่ะ คอหงส์ ซ.สังทิศ 1 ผู้ใหญ่ 3 คน น้ำถึงเอว ไม่มีอาหาร โทร 081-xxx-1234")
    assert llm.calls == 0 and a.last["provider_used"].startswith("own_model") and e.water_level.value == "waist"


def test_uncertain_message_escalates_to_llm():
    llm = FakeLLM(); a = agent(llm, threshold=0.99)
    e = a.run("แม่นอนอยู่กับที่ ลุกเองไม่ได้ น้ำขึ้นชั้นบนแล้ว คอหงส์")
    assert llm.calls == 1 and a.last["escalated"] and a.last["provider_used"].startswith("llm") and e.summary == "llm"


def test_llm_down_keeps_own_model_answer():
    a = agent(FakeLLM(fail=True), threshold=0.99)
    e = a.run("ช่วยด้วย ยายอายุ 85 ติดเตียง น้ำถึงชั้น 2 คอหงส์")
    assert a.last["escalated"] and a.last["ai_error"] and a.last["provider_used"].startswith("own_model")
    assert e.message_type.value == "help_request"


def test_thai_number_words_and_pregnancy_not_baby():
    a = IntakeAgent(strategy="own", log_teacher=False)
    e = a.run("ที่บ้านมีสามคน ตาเก้าสิบ ยายแปดสิบห้า หลาน 4 ขวบ")
    assert e.elderly_ages == [85, 90] and e.children_ages == [4.0] and e.adults == 2
    e = a.run("มีคนท้องแปดเดือน น้ำท่วมมิดชั้นล่าง")
    assert e.children_ages == []

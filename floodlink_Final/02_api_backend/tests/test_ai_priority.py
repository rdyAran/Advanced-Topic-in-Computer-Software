"""The own model may raise a case's colour (priority_hint); the API keeps that through merges and shows why."""
from api import service
from floodcommon.schemas import Extraction
from floodcommon.triage import priority


def ext(**kw):
    return Extraction(message_type="help_request", **kw)


def test_hint_only_makes_colour_more_urgent():
    assert priority(ext(needs=["food"], priority_hint="red", priority_hint_reason="พบคำวิกฤต: ทารก")) == ("red", "AI: พบคำวิกฤต: ทารก")
    assert priority(ext(flags=["dialysis"], priority_hint="green"))[0] == "red"          # a hint never lowers the colour
    assert priority(ext(water_level="roof"))[0] == "red"
    assert priority(ext(flags=["sick_now"]))[0] == "red" and priority(ext(flags=["in_labor"]))[0] == "red"
    assert priority(ext(lost_contact=True, elderly_ages=[65]))[0] == "orange"
    assert priority(ext(lost_contact=True))[0] == "yellow"
    assert priority(ext(needs=["medicine"]))[0] == "yellow"


class HintAgent:
    """Stands in for the agent: first report carries the model's red hint, the second (a re-post) does not."""
    def __init__(self):
        self.calls, self.last = 0, {"provider_used": "own_model (wcb-test)"}

    def run(self, text):
        self.calls += 1
        if self.calls == 1:
            return ext(area="คอหงส์", house_no="12", street="ซ.สังทิศ 2", needs=["food"],
                       priority_hint="red", priority_hint_reason="พบคำวิกฤต: ทารก")
        return ext(area="คอหงส์", house_no="12", street="ซ.สังทิศ 2", water_level="waist")


def test_ai_raised_colour_survives_a_merge():
    conn, a = service.connect(":memory:"), HintAgent()
    r1 = service.process_message(conn, a, "ฝากด้วยค่ะ บ้านเลขที่ 12 ซ.สังทิศ 2 คอหงส์ มีเด็กทารก ไม่มีอาหาร")
    r2 = service.process_message(conn, a, "โพสต์ซ้ำ บ้านเลขที่ 12 ซ.สังทิศ 2 คอหงส์ น้ำถึงเอวแล้ว")
    assert r2["action"] == "merged" and r2["case_id"] == r1["case_id"]
    case = service.list_cases(conn)[0]
    assert case["priority"] == "red" and case["priority_reason"].startswith("AI:")

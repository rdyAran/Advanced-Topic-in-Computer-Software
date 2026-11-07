"""Kind of place matters: a one-storey house with water at the chest has nowhere to go up."""
from api import service
from agent.router import IntakeAgent
from floodcommon.schemas import Extraction
from floodcommon.triage import priority, form_water, clean_form_text

agent = IntakeAgent(strategy="own", log_teacher=False)


def test_one_storey_house_is_more_urgent():
    one = Extraction(message_type="help_request", water_level="chest", building_floors=1)
    two = Extraction(message_type="help_request", water_level="chest", building_floors=2)
    assert priority(one)[0] == "red" and "ชั้นเดียว" in priority(one)[1]
    assert priority(two)[0] == "yellow"
    assert priority(Extraction(message_type="help_request", water_level="waist", building_floors=1))[0] == "orange"


def test_form_water_line_is_read_exactly():
    assert form_water("ที่พัก: บ้าน 2 ชั้น\nระดับน้ำ: น้ำมิดชั้น 1 ยังไม่ถึงชั้น 2 (อยู่ชั้น 2)").value == "floor1"
    assert form_water("ระดับน้ำ: น้ำถึงชั้น 2 แล้ว").value == "floor2"
    assert form_water("ระดับน้ำ: น้ำเกือบมิดหลังคา ขึ้นไปอยู่บนหลังคา").value == "roof"
    assert form_water("น้ำถึงเอว") is None and "ที่พัก" not in clean_form_text("ที่พัก: \nช่วยด้วย")


def test_form_message_end_to_end(monkeypatch):
    c = service.connect(":memory:")
    t = "ช่วยด้วย ผู้ใหญ่ 3 คน ซ.ควนลัง 7 ควนลัง โทร 089-111-2222\nที่พัก: บ้านชั้นเดียว\nระดับน้ำ: น้ำถึงอก"
    case = service.get_case(c, service.process_batch(c, agent, t)["case_id"])
    assert case["building_floors"] == 1 and case["water_level"] == "chest" and case["priority"] == "red"
    t2 = "ช่วยด้วย ผู้ใหญ่ 2 คน ซ.คลองแห 4 คลองแห โทร 081-000-1111\nที่พัก: บ้าน 2 ชั้น\nระดับน้ำ: น้ำมิดชั้น 1 ยังไม่ถึงชั้น 2 (อยู่ชั้น 2)"
    case2 = service.get_case(c, service.process_batch(c, agent, t2)["case_id"])
    assert case2["building_floors"] == 2 and case2["water_level"] == "floor1" and case2["priority"] != "red"

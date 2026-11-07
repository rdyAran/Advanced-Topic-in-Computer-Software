"""Run from repo root: python -m pytest -q   (local agent, no API key needed)"""
from api import service
from agent.router import IntakeAgent
from floodcommon.schemas import Extraction
from floodcommon.triage import priority, missing_fields, normalize_area

agent = IntakeAgent(strategy="own", log_teacher=False)


def ext(**kw):
    return Extraction(message_type="help_request", **kw)


def test_priority_rules():
    assert priority(ext(flags=["dialysis"]))[0] == "red"
    assert priority(ext(children_ages=[0.75]))[0] == "red"
    assert priority(ext(flags=["bedridden"], water_level="roof"))[0] == "red"
    assert priority(ext(flags=["bedridden"], water_level="waist"))[0] == "orange"
    assert priority(ext(elderly_ages=[82]))[0] == "orange"
    assert priority(ext(water_level="chest"))[0] == "yellow"
    assert priority(ext(water_level="knee", needs=["power"]))[0] == "green"


def test_missing_fields_and_area():
    assert missing_fields(ext(area="คอหงส์", adults=2, water_level="knee", contact="08x")) == []
    assert set(missing_fields(ext())) == {"area", "people_count", "water_level", "contact"}
    assert normalize_area("help at Khlong Hae soi 4") == "คลองแห"


def test_create_merge_resolve_flow():
    conn = service.connect(":memory:")
    r1 = service.process_message(conn, agent, "ช่วยด้วยค่ะ บ้านเลขที่ 12 ซ.ควนลัง 7 ควนลัง ยายอายุ 85 น้ำถึงเอว ติดต่อ 081-xxx-1234")
    assert r1["action"] == "created"
    r2 = service.process_message(conn, agent, "โพสต์ซ้ำนะคะ บ้านเลขที่ 12 ซ.ควนลัง 7 ควนลัง ยายอายุ 85 ตอนนี้น้ำขึ้นชั้น 2 แล้ว")
    assert r2["action"] == "merged" and r2["case_id"] == r1["case_id"]
    case = service.list_cases(conn)[0]
    assert case["water_level"] == "floor2" and case["report_count"] == 2
    r3 = service.process_message(conn, agent, "อัปเดตค่ะ ที่บ้านซ.ควนลัง 7 ควนลัง กู้ภัยมารับแล้ว ขอบคุณทุกคน")
    assert r3["action"] == "resolved"
    assert service.list_cases(conn)[0]["status"] == "resolved"


def test_followup_for_incomplete_message():
    conn = service.connect(":memory:")
    r = service.process_message(conn, agent, "ช่วยด้วย ติดอยู่ในบ้าน น้ำขึ้นเรื่อยๆ ด่วนมาก")
    assert r["action"] == "created" and r["followup"] and "ตำแหน่ง" in r["followup"]


def test_officer_override_locks_priority():
    conn = service.connect(":memory:")
    r = service.process_message(conn, agent, "ช่วยด้วย ผู้ใหญ่ 2 คน น้ำถึงเข่า คลองแห ซ.คลองแห 4 ไม่มีไฟชาร์จ ติดต่อ 089-xxx-5555")
    c = service.update_case(conn, r["case_id"], priority_override="red")
    assert c["priority"] == "red" and c["priority_locked"] == 1


def test_ai_stats_count_own_model():
    conn = service.connect(":memory:")
    service.process_message(conn, agent, "ช่วยด้วย ผู้ใหญ่ 2 คน น้ำถึงเอว คลองแห ไม่มีอาหาร")
    st = service.stats(conn)["ai"]
    assert st["handled_by_own_model"] == 1 and st["own_model_share"] == 1.0

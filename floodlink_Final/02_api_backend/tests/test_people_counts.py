"""'จำนวนคน: ผู้ใหญ่ 1 เด็ก 12 ผู้สูงอายุ 5' is a head count of 18, not one adult (bug report from the web form)."""
from api import service
from agent.router import IntakeAgent
from floodnlp.entities import extract_entities
from floodcommon.triage import people_total

agent = IntakeAgent(strategy="own", log_teacher=False)
FORM = """บ้านชั้นเดียว
ตำแหน่ง: https://maps.app.goo.gl/wNqRmZvBPcTXz1sm8
เบอร์ติดต่อ: (แบตเหลือ  %)
จำนวนคน: ผู้ใหญ่ 1 เด็ก 12 ผู้สูงอายุ 5
ผู้ป่วย/กลุ่มเปราะบาง: เด็กเล็ก ผู้สูงอายุ มีโรคประจำตัว
ระดับน้ำ: ท่วมเอว
ต้องการ: น้ำ ข้าว
ทางเข้า/อุปสรรค:
ติดมาแล้ว:  วัน"""


def test_form_head_count(monkeypatch):
    monkeypatch.setattr(service, "resolve_map_link", lambda url: None)
    c = service.connect(":memory:")
    case = service.get_case(c, service.process_batch(c, agent, FORM)["case_id"])
    assert case["people_total"] == 18 and case["children_count"] == 12 and case["elderly_count"] == 5 and case["adults"] == 6
    assert case["summary"].startswith("18 คน") and "เด็ก 12" in case["summary"]
    assert "people_count" not in case["missing_fields"] and "area" not in case["missing_fields"]


def test_ages_are_not_counts_and_counts_are_not_adults():
    e = extract_entities("ผู้ใหญ่ 3 เด็ก 2 ขวบ")
    assert e["children_ages"] == [2.0] and e["children_count"] is None and people_total(e) == 4
    e = extract_entities("มีเด็ก 3 คน ยายอายุ 80")
    assert e["children_count"] == 3 and e["adults"] == 1 and people_total(e) == 4
    e = extract_entities("ผู้สูงอายุ 85 ติดเตียง")
    assert e["elderly_ages"] == [85] and e["elderly_count"] is None

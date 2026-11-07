from api import service
from agent.router import IntakeAgent
from floodcommon.location import extract_location, nav_url

agent = IntakeAgent(strategy="own", log_teacher=False)


def test_extract_location_variants():
    assert extract_location("พิกัด 7.008123, 100.475201 ช่วยด้วย")["precision"] == "exact"
    u = extract_location("https://www.google.com/maps/@7.0081,100.4752,17z")
    assert (u["lat"], u["lng"]) == (7.0081, 100.4752)
    assert extract_location("https://maps.app.goo.gl/AbCdEf123")["precision"] == "link"
    assert extract_location("โทร 081-234-5678 อายุ 85.5")["precision"] is None   # not coordinates
    assert extract_location("51.5072, -0.1276")["precision"] is None             # outside Thailand


def test_nav_url_precision_order():
    assert nav_url({"geo_precision": "exact", "lat": 7.0, "lng": 100.4})["precision"] == "exact"
    assert nav_url({"map_url": "https://maps.app.goo.gl/x"})["url"] == "https://maps.app.goo.gl/x"
    a = nav_url({"house_no": "12", "street": "ซ.สังทิศ 2", "area": "คอหงส์", "lat": 7.0, "lng": 100.5})
    assert a["precision"] == "address" and "destination=" in a["url"]
    assert nav_url({"area": "คอหงส์", "lat": 7.0, "lng": 100.5})["precision"] == "area"


def test_case_gets_exact_location_and_nav_link():
    conn = service.connect(":memory:")
    r = service.process_batch(conn, agent, "ช่วยด้วย ยายอายุ 85 ติดเตียง น้ำถึงชั้น 2 คอหงส์ พิกัด 7.0081, 100.4752")
    assert r["n_cases"] == 1 and r["nav"]["precision"] == "exact" and "7.0081,100.4752" in r["nav"]["url"]
    c = service.list_cases(conn)[0]
    assert c["geo_precision"] == "exact" and c["nav"]["precision"] == "exact"


def test_one_text_many_cases():
    conn = service.connect(":memory:")
    text = ("ฝากแชร์ คลองแห โทร 081-xxx-1111\n"
            "1. บ้านเลขที่ 12 ซ.คลองแห 2 ยายอายุ 85 ติดเตียง น้ำถึงชั้น 2\n"
            "2. บ้านเลขที่ 40 ซ.คลองแห 4 ผู้ใหญ่ 3 คน เด็ก 2 ขวบ น้ำถึงอก\n"
            "3. ซ.คลองแห 6 ลุงฟอกไต ขอเรือ")
    r = service.process_batch(conn, agent, text)
    assert r["n_cases"] == 3 and r["batch_id"] and r["split_method"].startswith("rules")
    assert len({x["case_id"] for x in r["results"]}) == 3
    cases = service.list_cases(conn)
    assert all(c["contact"] for c in cases)          # reporter's phone copied to every case
    assert {c["priority"] for c in cases} >= {"red"}


def test_detail_bullets_stay_one_case():
    conn = service.connect(":memory:")
    r = service.process_batch(conn, agent, "บ้านเลขที่ 12 ซ.สังทิศ 2 คอหงส์\n- ยายติดเตียง\n- น้ำถึงชั้น 2\n- ไม่มีอาหาร")
    assert r["n_cases"] == 1

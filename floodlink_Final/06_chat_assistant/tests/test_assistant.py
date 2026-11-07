import pytest
from api import service
from agent.router import IntakeAgent
from assistant.bot import Assistant
from assistant.nlu import rule_intent, slots
from assistant import places as P

agent = IntakeAgent(strategy="own", log_teacher=False)


@pytest.fixture
def bot():
    conn = service.connect(":memory:")
    for t in ["ช่วยด้วย คลองแห ซ.คลองแห 2 ผู้ใหญ่ 3 คน น้ำดื่มหมด น้ำถึงอก",
              "คลองแห ซ.คลองแห 4 ยาย 80 น้ำถึงชั้น 2 ไม่มีน้ำกิน"]:
        service.process_batch(conn, agent, t)
    return Assistant(conn, intake=lambda txt, ch: service.process_batch(conn, agent, txt, ch),
                     get_case=lambda cid: next((c for c in service.list_cases(conn) if c["id"] == cid), None))


@pytest.mark.parametrize("text,intent", [
    ("ฉันมีของมาบริจาคเป็นน้ำดื่ม 200 แพ็ค ควรนำไปวางไว้ที่ไหน", "donate"),
    ("มีข้าวกล่อง 300 กล่อง จะเอาไปส่งที่ไหนดี", "donate"),
    ("ขอน้ำดื่มด้วยค่ะ ติดอยู่ในบ้าน คลองแห", "request_help"),
    ("ช่วยด้วย ยายติดเตียง น้ำถึงชั้น 2 คอหงส์", "request_help"),
    ("พ่อหมดสติ ถูกไฟดูด", "emergency"),
    ("ศูนย์พักพิงใกล้ๆ อยู่ไหน", "find_shelter"),
    ("ไปรับข้าวแจกได้ที่ไหน", "find_distribution"),
    ("อยากเป็นอาสา มีเรือ 2 ลำ", "volunteer"),
    ("เคส C-1A2B3C ถึงไหนแล้ว", "case_status"),
    ("โดนน้ำกัดเท้าทำยังไง", "info"),
])
def test_rule_intents(text, intent):
    assert rule_intent(text)[0] == intent


def test_slots_items_qty_area():
    s = slots("มีน้ำดื่ม 1,200 ขวด กับนมเด็ก 30 กล่อง อยู่แถวคอหงส์")
    assert s["items"][:2] == ["water", "milk"] and s["qty"] == 1200 and s["area"] == "คอหงส์"


def test_donation_ranks_hub_that_needs_it_and_warns_big_load(bot):
    r = bot.handle("ฉันมีของมาบริจาคเป็นน้ำดื่ม 200 แพ็ค ควรนำไปวางไว้ที่ไหน", "s1")
    assert r["intent"] == "donate" and r["cards"] and r["cards"][0]["id"] == "P-HUB1"     # hub short of water
    assert "โทรนัด" in r["reply"] and all(c["nav_url"] and c["page_url"] for c in r["cards"])
    r2 = bot.handle("อยู่แถวคอหงส์", "s1")                                                 # follow-up gives location
    assert r2["intent"] == "donate" and "กม." in r2["cards"][0]["subtitle"]


def test_chat_creates_red_case_and_status(bot):
    r = bot.handle("ช่วยด้วยค่ะ ยายอายุ 85 ติดเตียง น้ำถึงชั้น 2 คอหงส์ ซ.สังทิศ 2 โทร 081-xxx-1234", "s2")
    cid = r["cards"][0]["id"]
    assert r["intent"] == "request_help" and "แดง" in r["cards"][0]["title"] and "/track/" in r["cards"][0]["page_url"]
    assert "/track/" in r["reply"] and r["links"][0]["url"] == r["cards"][0]["page_url"]
    st = bot.handle(f"{cid} ถึงไหนแล้ว", "s2")
    assert st["intent"] == "case_status" and "nav_url" not in st["cards"][0] and "ติดเตียง" not in str(st)   # public: status only


def test_emergency_gives_hotline_first(bot):
    r = bot.handle("พ่อถูกไฟดูด หมดสติ อยู่บ้านพรุ หลังวัด", "s3")
    assert r["reply"].startswith("📞") and any(l["url"] == "tel:1669" for l in r["links"])


def test_shelter_sorted_by_distance_with_location(bot):
    r = bot.handle("ศูนย์พักพิงอยู่ที่ไหน", "s4", lat=7.006, lng=100.44)
    assert r["cards"][0]["id"] == "P-SHL2"


def test_kb_answers_with_sources(bot):
    r = bot.handle("โดนน้ำกัดเท้าต้องทำยังไง", "s5")
    assert "น้ำกัดเท้า" in r["reply"] and r["sources"][0]["file"] == "05_health.md"


def test_volunteer_sees_needs_by_area(bot):
    r = bot.handle("อยากเป็นอาสา มีเรือ 2 ลำ", "s6")
    assert "คลองแห" in r["reply"]


def test_places_upsert_by_area_geocodes():
    conn = service.connect(":memory:"); P.init(conn, seed_demo=False)
    p = P.upsert(conn, {"id": "X1", "type": "donation_hub", "name": "จุดใหม่", "area": "ทุ่งเสา", "accepts": ["water"]})
    assert p["lat"] is not None and p["nav_url"]


@pytest.fixture
def tbot():
    from types import SimpleNamespace
    conn = service.connect(":memory:")
    tr = SimpleNamespace(view=lambda t: service.track_view(conn, t), followup=lambda t, c, x: service.track_followup(conn, agent, t, c, x),
                         safe=lambda t, c: service.track_safe(conn, t, c))
    b = Assistant(conn, intake=lambda txt, ch: service.process_batch(conn, agent, txt, ch), get_case=lambda cid: service.get_case(conn, cid), tracker=tr)
    b._conn = conn
    return b


def test_chat_asks_missing_info_one_by_one_and_adds_it_to_the_same_case(tbot):
    r = tbot.handle("ช่วยด้วยค่ะ ผู้ใหญ่ 4 คน แม่เดินไม่ได้ ขอเรือด่วน คลองแห", "u1")
    cid = r["cards"][0]["id"]
    assert "ทีมยังต้องการอีก" in r["reply"] and "บ้านอยู่ตรงไหน" in r["reply"] and r["quick_replies"] == ["📍 ส่งตำแหน่งของฉัน"]
    r = tbot.handle("บ้านเลขที่ 12 ซ.คลองแห 2 ตรงข้ามวัด", "u1")
    assert r["case_id"] == cid and "เบอร์" in r["reply"]
    r = tbot.handle("081-234-5678 แบตเหลือ 20%", "u1")
    assert r["case_id"] == cid and "น้ำสูงแค่ไหน" in r["reply"] and "น้ำถึงเอว" in r["quick_replies"]
    r = tbot.handle("น้ำถึงเอว", "u1")
    assert "ข้อมูลสำคัญครบแล้ว" in r["reply"]
    assert len(service.list_cases(tbot._conn)) == 1                         # everything went into ONE case


def test_chat_status_and_safe_close_with_confirmation(tbot):
    cid = tbot.handle("ช่วยด้วย ยายอายุ 85 ติดเตียง น้ำถึงชั้น 2 บ้านเลขที่ 9 ซ.สังทิศ 2 คอหงส์ โทร 081-234-5678", "u2")["cards"][0]["id"]
    st = tbot.handle("ทีมมายังคะ", "u2")
    assert st["intent"] == "my_status" and cid in st["reply"] and "ยังไม่มีทีมรับ" in st["reply"]
    ask = tbot.handle("ปลอดภัยแล้วค่ะ ญาติมารับแล้ว", "u2")
    assert "ยืนยัน" in ask["reply"] and service.get_case(tbot._conn, cid)["status"] != "resolved"
    done = tbot.handle("ยืนยัน ปลอดภัยแล้ว", "u2")
    assert "ปิด" in done["reply"] and service.get_case(tbot._conn, cid)["close_reason"] == "self_safe"


def test_another_house_makes_a_new_case_and_emergency_adds_to_current(tbot):
    a = tbot.handle("ช่วยด้วย ผู้ใหญ่ 3 คน น้ำถึงอก ซ.ควนลัง 7 ควนลัง โทร 089-111-2222", "u3")["cards"][0]["id"]
    e = tbot.handle("ตอนนี้ยายหมดสติแล้ว", "u3")
    assert e["reply"].startswith("📞") and e["case_id"] == a
    n = tbot.handle("อีกบ้านค่ะ ลุงฟอกไต น้ำถึงชั้น 2 ซ.คลองแห 4 คลองแห", "u3")
    assert n["cards"] and n["cards"][0]["id"] != a


def test_kb_says_it_does_not_know_instead_of_guessing(tbot):
    r = tbot.handle("ฟุตบอลคืนนี้ใครชนะ", "u4")
    assert "ยังไม่มีข้อมูล" in r["reply"]
    r = tbot.handle("ข้อมูลของฉันใครเห็นบ้าง", "u4")
    assert "ชุดกู้ภัยที่รับเคส" in r["reply"] and r["sources"][0]["file"] == "06_floodlink_faq.md"
    assert "ฟุตบอล" not in str(tbot.handle("รถจมน้ำทำยังไง", "u4")) and "สตาร์ท" in tbot.handle("รถจมน้ำทำยังไง", "u4")["reply"]


def test_short_answers_go_to_the_open_case(tbot):
    tbot.handle("แม่ติดอยู่ในบ้าน ช่วยด้วย น้ำขึ้นเร็วมาก ทุ่งเสา", "u5")
    for m in ["บ้านเลขที่ 45 ซอยทุ่งเสา 3 ใกล้โรงเรียน", "0891234567", "สองคน", "น้ำถึงอก"]:
        tbot.handle(m, "u5")
    assert len(service.list_cases(tbot._conn)) == 1
    c = service.list_cases(tbot._conn)[0]
    assert c["water_level"] == "chest" and c["contact"] and c["house_no"] == "45"

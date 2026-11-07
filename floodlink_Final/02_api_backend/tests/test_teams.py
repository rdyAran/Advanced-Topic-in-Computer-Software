"""One account per field team (the team lead). Centre creates it; dispatch = assign->accept/decline, or claim nearby."""
import pytest
from api import service, auth, teams
from agent.router import IntakeAgent

agent = IntakeAgent(strategy="own", log_teacher=False)
RED = "ช่วยด้วย ยายอายุ 85 ติดเตียง น้ำถึงชั้น 2 บ้านเลขที่ 9 ซ.สังทิศ 2 คอหงส์ โทร 081-234-5678 พิกัด 7.0100, 100.4700"
ORANGE = "ขอเรือด่วน ผู้ใหญ่ 3 คน น้ำถึงอก ซ.ควนลัง 7 ควนลัง โทร 089-111-2222"


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path)); monkeypatch.setenv("SEED_PASSWORD", "demo-pass-1")
    auth._fails.clear()
    c = service.connect(":memory:"); auth.seed_accounts(c)
    return c


def u(conn, name):
    return next(x for x in auth.list_users(conn) if x["username"] == name)


def test_officer_creates_team_lead_and_profile(conn):
    off = u(conn, "officer")
    lead = teams.create_team(conn, off, "pt3", "longpass-33", "ชุดเรือ 3 ป่อเต็กตึ๊ง", org="มูลนิธิป่อเต็กตึ๊ง", kind="volunteer",
                             phone="080-000-0003", boats=2, seats=12, has_medic=True)
    assert lead["role"] == "rescuer" and lead["team"] == "ชุดเรือ 3 ป่อเต็กตึ๊ง" and auth.login(conn, "pt3", "longpass-33")
    t = next(t for t in teams.board(conn) if t["name"] == lead["team"])
    assert t["org"] == "มูลนิธิป่อเต็กตึ๊ง" and t["seats"] == 12 and t["has_medic"] and t["lead"]["username"] == "pt3"
    with pytest.raises(auth.AuthError):
        teams.create_team(conn, off, "pt4", "longpass-33", "ชุดเรือ 3 ป่อเต็กตึ๊ง")      # one lead per team
    with pytest.raises(LookupError):
        teams.check_lead_account(conn, u(conn, "admin")["id"])                          # officers cannot touch admins


def test_assign_then_accept_or_decline(conn):
    off, b1 = u(conn, "officer"), u(conn, "boat1")
    cid = service.process_batch(conn, agent, RED)["case_id"]
    c = service.update_case(conn, cid, assigned_team="ทีมเรือ 1", user=off)
    assert c["assign_state"] == "pending" and c["waiting_accept_min"] == 0
    with pytest.raises(service.Forbidden):
        teams.accept(conn, u(conn, "boat2"), cid)
    c = teams.accept(conn, b1, cid)
    assert c["assign_state"] == "accepted" and c["waiting_accept_min"] is None
    c = teams.decline(conn, b1, cid, "เรือเข้าไม่ได้ น้ำเชี่ยว")
    assert c["assigned_team"] is None and c["status"] == "verified"
    assert auth.audit_list(conn, cid)[0]["detail"]["reason"].startswith("เรือ")
    with pytest.raises(service.Forbidden):
        teams.decline(conn, b1, cid, "อีกรอบ")                        # no longer its case
    tl = [t["text"] for t in service.public_timeline(conn, cid)]
    assert "ทีมเรือ 1 ตอบรับเคสแล้ว" in tl and tl[-1].startswith("ทีมที่ได้รับมอบหมายเข้าไม่ได้")


def test_nearby_hides_details_and_first_claim_wins(conn):
    b1, b2 = u(conn, "boat1"), u(conn, "boat2")
    teams.update_profile(conn, "ทีมเรือ 1", {"lat": 7.011, "lng": 100.471, "status": "available"}, b1)
    red = service.process_batch(conn, agent, RED)["case_id"]
    service.process_batch(conn, agent, ORANGE)
    near = teams.nearby(conn, b1)
    assert [n["id"] for n in near][0] == red and near[0]["km"] is not None and near[0]["km"] < 1
    assert "contact" not in near[0] and "house_no" not in near[0] and "081" not in str(near)
    c = teams.claim(conn, b1, red)
    assert c["assigned_team"] == "ทีมเรือ 1" and c["assign_state"] == "accepted" and c["status"] == "assigned"
    with pytest.raises(ValueError):
        teams.claim(conn, b2, red)
    assert red not in [n["id"] for n in teams.nearby(conn, b2)]
    assert [x["id"] for x in service.visible_cases(conn, b1)] == [red]


def test_board_suggestions_and_late_assignments(conn, monkeypatch):
    off = u(conn, "officer")
    teams.update_profile(conn, "ทีมเรือ 1", {"lat": 7.2, "lng": 100.6, "status": "available"}, off)
    teams.update_profile(conn, "ทีมเรือ 2", {"lat": 7.011, "lng": 100.471, "status": "available", "has_medic": True}, off)
    cid = service.process_batch(conn, agent, RED)["case_id"]
    s = teams.suggest_teams(conn, service.get_case(conn, cid))
    assert s[0]["team"] == "ทีมเรือ 2"                                  # closer + medic for a bedridden patient
    teams.update_profile(conn, "ทีมเรือ 2", {"status": "offline"}, off)
    assert all(x["team"] != "ทีมเรือ 2" for x in teams.suggest_teams(conn, service.get_case(conn, cid)))
    service.update_case(conn, cid, assigned_team="ทีมเรือ 1", user=off)
    conn.execute("UPDATE cases SET assigned_at='2020-01-01T00:00:00' WHERE id=?", (cid,))
    assert teams.late(conn)[0]["id"] == cid
    b = {t["name"]: t for t in teams.board(conn)}
    assert b["ทีมเรือ 1"]["pending"] == 1 and b["ทีมเรือ 1"]["red_cases"] == 1
    with pytest.raises(ValueError):
        teams.update_profile(conn, "ทีมเรือ 1", {"status": "flying"}, off)


def test_demo_scenario_sets_up_a_running_operation(conn):
    rows = [{"text": RED, "channel": "web_form", "timestamp": "2026-11-03T09:00:00"},
            {"text": ORANGE, "channel": "web_form", "timestamp": "2026-11-03T09:01:00"},
            {"text": "ขอน้ำดื่ม อาหาร ผู้ใหญ่ 2 คน ซ.คลองแห 4 คลองแห น้ำถึงเอว", "channel": "web_form", "timestamp": "2026-11-03T09:02:00"},
            {"text": "ช่วยด้วย เด็ก 2 ขวบ น้ำถึงอก ซ.ทุ่งเสา 5 ทุ่งเสา โทร 082-333-4444", "channel": "web_form", "timestamp": "2026-11-03T09:03:00"}]
    service.seed_demo(conn, agent, rows)
    real = service.process_batch(conn, agent, "ขอเรือ ผู้ใหญ่ 5 คน น้ำถึงชั้น 2 หมู่บ้านทดสอบ บ้านพรุ โทร 083-000-1111")["case_id"]
    d = teams.demo_scenario(conn, u(conn, "admin"))
    st = {c["id"]: c for c in service.list_cases(conn)}
    assert st[d["in_progress"]]["status"] == "in_progress" and st[d["in_progress"]]["assign_state"] == "accepted"
    assert st[d["pending"]]["assign_state"] == "pending" and all(st[i]["status"] == "verified" for i in d["verified"])
    assert st[real]["status"] == "new"                                   # real cases are never touched
    assert all(t["lat"] for t in teams.board(conn) if t["name"] in teams.DEMO_TEAMS)

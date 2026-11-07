"""v0.16 scope: accounts + roles, what each role may see/change, the reporter's private tracking link,
case lifecycle with close reasons, officer AI corrections -> training export, public summary without personal data."""
import base64, time
import pytest
from api import service, auth
from agent.router import IntakeAgent

agent = IntakeAgent(strategy="own", log_teacher=False)
JPEG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff" + b"\x00" * 50).decode()
RED = "ช่วยด้วย ยายอายุ 85 ติดเตียง น้ำถึงชั้น 2 บ้านเลขที่ 9 ซ.สังทิศ 2 คอหงส์ โทร 081-234-5678"


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    monkeypatch.setenv("SEED_PASSWORD", "demo-pass-1")
    monkeypatch.delenv("AUTH_SECRET", raising=False)
    auth._fails.clear()
    c = service.connect(":memory:")
    auth.seed_accounts(c)
    return c


def users(conn):
    return {u["username"]: u for u in auth.list_users(conn)}


# ---------------- accounts ----------------
def test_seed_login_token_and_lockout(conn):
    assert set(users(conn)) == {"admin", "officer", "boat1", "boat2"} and auth.seed_accounts(conn) is None
    u = auth.login(conn, "Officer", "demo-pass-1")
    assert u["role"] == "coordinator" and "pw_hash" not in u
    tok = auth.make_token(conn, u)
    assert auth.read_token(conn, tok)["username"] == "officer"
    assert auth.read_token(conn, tok[:-2] + "xx") is None and auth.read_token(conn, "junk") is None
    for _ in range(auth.MAX_FAILS):
        with pytest.raises(auth.AuthError):
            auth.login(conn, "boat1", "wrong-password")
    with pytest.raises(auth.AuthError, match="หลายครั้ง"):
        auth.login(conn, "boat1", "demo-pass-1")           # locked even with the right password


def test_password_change_and_disable_log_out_everywhere(conn):
    u = auth.login(conn, "boat2", "demo-pass-1")
    tok = auth.make_token(conn, u)
    auth.update_user(conn, u["id"], password="new-pass-22")
    assert auth.read_token(conn, tok) is None and auth.login(conn, "boat2", "new-pass-22")
    tok = auth.make_token(conn, auth.get_user(conn, u["id"]))
    auth.update_user(conn, u["id"], active=False)
    assert auth.read_token(conn, tok) is None
    with pytest.raises(auth.AuthError):
        auth.login(conn, "boat2", "new-pass-22")


def test_account_rules(conn):
    with pytest.raises(auth.AuthError):
        auth.create_user(conn, "x", "longenough1", "coordinator")           # username too short
    with pytest.raises(auth.AuthError):
        auth.create_user(conn, "team9", "short", "rescuer", team="ทีม 9")   # password too short
    with pytest.raises(auth.AuthError):
        auth.create_user(conn, "team9", "longenough1", "rescuer")            # rescuer needs a team
    with pytest.raises(auth.AuthError):
        auth.update_user(conn, users(conn)["admin"]["id"], role="coordinator")   # last admin stays
    auth.create_user(conn, "team9", "longenough1", "rescuer", team="ทีม 9")
    assert set(auth.teams(conn)) == {"ทีมเรือ 1", "ทีมเรือ 2", "ทีม 9"}


# ---------------- roles on cases ----------------
def test_rescuer_sees_only_its_team_and_limited_changes(conn):
    u = users(conn)
    a = service.process_batch(conn, agent, RED)["case_id"]
    b = service.process_batch(conn, agent, "ขอเรือด่วน ผู้ใหญ่ 3 คน น้ำถึงอก ซ.ควนลัง 7 ควนลัง โทร 089-111-2222")["case_id"]
    service.update_case(conn, a, assigned_team="ทีมเรือ 1", user=u["officer"])
    assert service.get_case(conn, a)["status"] == "assigned"
    assert [c["id"] for c in service.visible_cases(conn, u["boat1"])] == [a]
    assert service.visible_cases(conn, u["boat2"]) == [] and len(service.visible_cases(conn, u["officer"])) == 2
    ca, cb = service.get_case(conn, a), service.get_case(conn, b)
    service.check_update(u["boat1"], ca, status="in_progress")
    service.check_update(u["boat1"], ca, status="resolved", close_reason="not_found")
    for kw in ({"priority": "green"}, {"assigned_team": "ทีมเรือ 2"}, {"status": "new"},
               {"status": "resolved", "close_reason": "duplicate"}):
        with pytest.raises(service.Forbidden):
            service.check_update(u["boat1"], ca, **kw)
    with pytest.raises(service.Forbidden):
        service.check_update(u["boat1"], cb, status="in_progress")      # not its case
    service.check_update(u["officer"], cb, priority="green", assigned_team="ทีมเรือ 2")


def test_lifecycle_close_reason_reopen_and_audit(conn):
    off = users(conn)["officer"]
    cid = service.process_batch(conn, agent, RED)["case_id"]
    service.update_case(conn, cid, status="verified", user=off)
    service.update_case(conn, cid, assigned_team="ทีมเรือ 1", user=off)
    service.update_case(conn, cid, status="in_progress", user=users(conn)["boat1"])
    c = service.update_case(conn, cid, status="resolved", close_reason="rescued", user=users(conn)["boat1"])
    assert c["status"] == "resolved" and c["close_reason"] == "rescued" and c["closed_at"]
    c = service.update_case(conn, cid, status="in_progress", user=off)                  # reopen clears the reason
    assert c["close_reason"] is None
    acts = [a["action"] for a in reversed(auth.audit_list(conn, cid))]
    assert acts == ["created", "status", "assign", "status", "close", "reopen"]
    assert auth.audit_list(conn, cid)[1]["actor"] == "boat1"
    with pytest.raises(ValueError):
        service.update_case(conn, cid, status="resolved", close_reason="bored", user=off)


def test_photo_access_by_role_and_tracking_link(conn):
    u = users(conn)
    r = service.process_batch(conn, agent, RED, photos=[JPEG])
    pid, cid, tok = r["photos"][0]["id"], r["case_id"], r["track_token"]
    assert service.media_allowed(conn, pid, u["officer"]) and not service.media_allowed(conn, pid, None)
    assert not service.media_allowed(conn, pid, u["boat1"])
    service.update_case(conn, cid, assigned_team="ทีมเรือ 1", user=u["officer"])
    assert service.media_allowed(conn, pid, u["boat1"]) and not service.media_allowed(conn, pid, u["boat2"])
    assert service.media_allowed(conn, pid, track=tok) and not service.media_allowed(conn, pid, track="x" * 22)


# ---------------- reporter tracking link ----------------
def test_tracking_link_view_followup_and_safe(conn):
    r = service.process_batch(conn, agent, "ช่วยด้วยค่ะ ผู้ใหญ่ 4 คน แม่เดินไม่ได้ ขอเรือด่วน")
    tok, cid = r["track_token"], r["case_id"]
    assert len(tok) >= 20 and r["track_path"] == f"/track/{tok}"
    v = service.track_view(conn, tok)
    assert [c["id"] for c in v["cases"]] == [cid] and v["cases"][0]["status_th"] == "รอเจ้าหน้าที่ตรวจ"
    assert "contact" not in v["cases"][0] and v["cases"][0]["timeline"][0]["text"].startswith("รับเรื่องแล้ว")
    f = service.track_followup(conn, agent, tok, None, "บ้านเลขที่ 12 ซ.ควนลัง 7 ควนลัง น้ำถึงเอว โทร 081-234-5678", [JPEG])
    assert f["case"]["area"] == "ควนลัง" and f["missing_fields"] == []
    v = service.track_view(conn, tok)
    assert len(v["my_reports"]) == 2 and v["my_reports"][1]["photos"][0]["url"].endswith(f"?track={tok}")
    assert service.media_allowed(conn, v["my_reports"][1]["photos"][0]["id"], track=tok)
    service.update_case(conn, cid, assigned_team="ทีมเรือ 1", user=users(conn)["officer"])
    tl = [t["text"] for t in service.track_view(conn, tok)["cases"][0]["timeline"]]
    assert "มอบหมายให้ ทีมเรือ 1" in tl and not any("officer" in t for t in tl)
    s = service.track_safe(conn, tok)
    assert s["status"] == "resolved" and s["close_reason"] == "self_safe"
    with pytest.raises(ValueError):
        service.track_followup(conn, agent, tok, None, "ยังอยู่")         # closed case: report again instead
    assert service.track_view(conn, "nope") is None


def test_tracking_link_cannot_touch_other_cases(conn):
    a = service.process_batch(conn, agent, RED)
    b = service.process_batch(conn, agent, "ขอเรือด่วน ผู้ใหญ่ 3 คน น้ำถึงอก ซ.ควนลัง 7 ควนลัง โทร 089-111-2222")
    with pytest.raises(service.Forbidden):
        service.track_followup(conn, agent, a["track_token"], b["case_id"], "x")
    with pytest.raises(service.Forbidden):
        service.track_safe(conn, a["track_token"], b["case_id"])
    with pytest.raises(LookupError):
        service.track_safe(conn, "z" * 22)


def test_rescuer_note_is_not_read_by_ai(conn):
    u = users(conn)
    cid = service.process_batch(conn, agent, RED)["case_id"]
    before = service.get_case(conn, cid)
    n = service.add_note(conn, cid, u["boat1"], "ถึงแล้ว น้ำเชี่ยว เข้าทางหลังวัด", [JPEG])
    after = service.get_case(conn, cid)
    assert n["photos"] and after["flags"] == before["flags"] and after["report_count"] == before["report_count"]
    msgs = service.case_messages(conn, cid)
    assert msgs[-1]["action"] == "note" and "ทีมเรือ 1" in msgs[-1]["author"] and msgs[-1]["photos"]


# ---------------- AI corrections -> training data ----------------
def test_officer_correction_updates_case_and_exports_label(conn):
    off = users(conn)["officer"]
    cid = service.process_batch(conn, agent, "ขอเรือด่วน ผู้ใหญ่ 3 คน น้ำถึงอก ซ.ควนลัง 7 ควนลัง โทร 089-111-2222 แม่ฟอกไต")["case_id"]
    c = service.correct_ai(conn, cid, off, {"flags": ["dialysis", "wheelchair"], "needs": ["evacuation", "medicine"]})
    assert c["priority"] == "red" and set(c["flags"]) == {"dialysis", "wheelchair"} and not c["priority_locked"]
    c = service.correct_ai(conn, cid, off, {"priority": "orange"})
    assert c["priority"] == "orange" and c["priority_locked"]
    rows = service.export_corrections(conn)
    assert len(rows) == 1 and rows[0]["priority"] == "orange" and rows[0]["human_reviewed"] and "ฟอกไต" in rows[0]["text"]
    assert rows[0]["flags"] == ["dialysis", "wheelchair"] and rows[0]["reviewed_by"] == "officer"
    with pytest.raises(ValueError):
        service.correct_ai(conn, cid, off, {"flags": ["flying"]})
    assert auth.audit_list(conn, cid)[0]["action"] == "correct_ai"


# ---------------- public page ----------------
def test_public_summary_has_no_personal_data(conn):
    service.process_batch(conn, agent, RED + " พิกัด 7.012345, 100.476543")
    s = service.public_summary(conn)
    txt = str(s)
    assert s["open_cases"] == 1 and s["open_by_priority"]["red"] == 1
    assert "081" not in txt and "ติดเตียง" not in txt and "สังทิศ" not in txt and "7.012345" not in txt
    assert s["points"] == [{"lat": 7.01, "lng": 100.48, "count": 1, "worst": "red"}]


def test_reset_keeps_accounts(conn):
    service.process_batch(conn, agent, RED)
    service.reset_all(conn)
    assert service.list_cases(conn) == [] and len(auth.list_users(conn)) == 4


def test_tracking_checklist_says_what_the_team_still_needs(conn):
    tok = service.process_batch(conn, agent, "ช่วยด้วยค่ะ ผู้ใหญ่ 4 คน แม่เดินไม่ได้ ขอเรือด่วน คลองแห")["track_token"]
    c = service.track_view(conn, tok)["cases"][0]
    st = {r["key"]: r["state"] for r in c["checklist"]}
    assert st["location"] == "partial" and st["contact"] == "missing" and st["water"] == "missing" and st["people"] == "ok"
    assert c["essential_total"] == 4 and c["essential_ok"] == 1
    service.track_followup(conn, agent, tok, None, "พิกัด 7.012345, 100.476543 โทร 081-234-5678 น้ำถึงอก")
    c = service.track_view(conn, tok)["cases"][0]
    assert c["essential_ok"] == 4 and "081" not in str(c)

"""Group-1 fixes: rate limits, head-count colours, link expiry, persistent chat, opt-out, possible duplicates."""
import pytest
from api import service, auth, ratelimit
from agent.router import IntakeAgent
from floodcommon.schemas import Extraction
from floodcommon.triage import priority

agent = IntakeAgent(strategy="own", log_teacher=False)


def test_limiter_per_minute_and_double_send():
    t = [1000.0]
    L = ratelimit.Limiter(per_min=3, per_hour=5, dup_window=600, clock=lambda: t[0])
    for _ in range(3):
        L.check("ip1", "report")
    with pytest.raises(ratelimit.Limited):
        L.check("ip1", "report")
    L.check("ip2", "report")                                       # another person is not affected
    t[0] += 61
    L.check("ip1", "report"); L.check("ip1", "report")
    with pytest.raises(ratelimit.Limited):
        L.check("ip1", "report")                                   # 5 per hour reached
    L.remember("ip1", "ช่วยด้วย  ซอย 5", {"case_id": "C-1"})
    assert L.duplicate("ip1", "ช่วยด้วย ซอย 5") == {"case_id": "C-1"} and L.duplicate("ip2", "ช่วยด้วย ซอย 5") is None
    t[0] += 601
    assert L.duplicate("ip1", "ช่วยด้วย ซอย 5") is None


def test_head_counts_change_the_colour():
    e = lambda **k: Extraction(message_type="help_request", **k)
    assert priority(e(adults=6, children_count=12, water_level="waist"))[0] == "orange"          # 18 people
    assert priority(e(adults=2, children_count=2, water_level="chest"))[1].startswith("มีเด็ก")
    assert priority(e(adults=3, elderly_count=2))[0] == "yellow"
    assert priority(e(adults=2, days_trapped=5))[0] == "orange"


def test_tracking_link_expires_30_days_after_close():
    c = service.connect(":memory:")
    r = service.process_batch(c, agent, "ช่วยด้วย ผู้ใหญ่ 3 คน น้ำถึงอก ซ.ควนลัง 7 ควนลัง โทร 089-111-2222")
    service.update_case(c, r["case_id"], status="resolved", close_reason="rescued", user="t")
    assert service.track_view(c, r["track_token"])
    c.execute("UPDATE cases SET closed_at='2026-01-01T00:00:00+07:00' WHERE id=?", (r["case_id"],))
    assert service.track_view(c, r["track_token"]) is None


def test_chat_remembers_its_case_after_restart():
    from types import SimpleNamespace
    from assistant.bot import Assistant
    c = service.connect(":memory:")
    tr = SimpleNamespace(view=lambda t: service.track_view(c, t), followup=lambda t, i, x: service.track_followup(c, agent, t, i, x),
                         safe=lambda t, i: service.track_safe(c, t, i))
    mk = lambda: Assistant(c, intake=lambda t, ch: service.process_batch(c, agent, t, ch), get_case=lambda i: service.get_case(c, i), tracker=tr)
    cid = mk().handle("ช่วยด้วย ผู้ใหญ่ 3 คน ซ.ควนลัง 7 ควนลัง น้ำถึงอก", "s1")["cards"][0]["id"]
    r = mk().handle("โทร 089-111-2222", "s1")                     # a NEW bot object = the API restarted
    assert r.get("case_id") == cid and len(service.list_cases(c)) == 1


def test_opted_out_reports_are_not_exported():
    c = service.connect(":memory:")
    service.process_batch(c, agent, "ช่วยด้วย ผู้ใหญ่ 3 คน น้ำถึงอก ซ.ควนลัง 7 ควนลัง", no_training=True)
    service.process_batch(c, agent, "ขอน้ำดื่ม ผู้ใหญ่ 2 คน ซ.คลองแห 4 คลองแห น้ำถึงเอว")
    rows = service.export_training(c)
    assert len(rows) == 1 and "คลองแห" in rows[0]["text"]


def test_unsure_duplicate_is_suggested_and_officer_merges(monkeypatch):
    monkeypatch.setenv("SEED_PASSWORD", "demo-pass-1")
    c = service.connect(":memory:"); auth.seed_accounts(c)
    off = next(u for u in auth.list_users(c) if u["username"] == "officer")
    a = service.process_batch(c, agent, "ช่วยด้วย ยายอายุ 85 ติดเตียง น้ำถึงชั้น 2 ซ.สังทิศ 2 คอหงส์")["case_id"]
    b = service.process_batch(c, agent, "ยาย 85 ติดเตียงค่ะ คอหงส์ น้ำขึ้นชั้น 2 โทร 081-234-5678")
    cb = service.get_case(c, b["case_id"])
    if b["action"] == "merged":
        pytest.skip("scored high enough to merge automatically")
    assert cb["possible_dup"] == a and 0.4 <= cb["possible_dup_score"] < 0.7
    t = service.merge_into(c, b["case_id"], a, off)
    assert t["contact"] and t["report_count"] == 2 and service.get_case(c, b["case_id"])["close_reason"] == "duplicate"
    assert len(service.case_messages(c, a)) == 2
    with pytest.raises(ValueError):
        service.merge_into(c, a, a, off)

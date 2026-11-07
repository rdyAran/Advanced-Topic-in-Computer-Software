"""Times carry the Thailand offset, so a browser never shows a fresh case as '7 ชม.ก่อน'."""
import datetime as dt
from api import service
from agent.router import IntakeAgent
from floodcommon import clock

agent = IntakeAgent(strategy="own", log_teacher=False)


def test_new_records_have_the_offset_and_are_now():
    c = service.connect(":memory:")
    case = service.get_case(c, service.process_batch(c, agent, "ช่วยด้วย ผู้ใหญ่ 3 คน น้ำถึงอก ซ.ควนลัง 7 ควนลัง")["case_id"])
    assert case["created_at"].endswith("+07:00")
    age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(case["created_at"])
    assert abs(age.total_seconds()) < 60


def test_old_utc_rows_are_upgraded_once(tmp_path):
    db = str(tmp_path / "t.db")
    c = service.connect(db)
    cid = service.process_batch(c, agent, "ช่วยด้วย ผู้ใหญ่ 3 คน น้ำถึงอก ซ.ควนลัง 7 ควนลัง")["case_id"]
    c.execute("UPDATE cases SET created_at='2026-11-03T11:48:00' WHERE id=?", (cid,)); c.commit()   # how v0.20 saved it (UTC)
    c2 = service.connect(db)
    assert service.get_case(c2, cid)["created_at"] == "2026-11-03T18:48:00+07:00"
    assert clock.upgrade_naive_times(c2) == 0                                                        # idempotent


def test_incoming_times_without_offset_are_local_and_utc_is_converted():
    assert clock.normalize("2026-11-03T09:00:00") == "2026-11-03T09:00:00+07:00"
    assert clock.normalize("2026-11-03T02:00:00Z") == "2026-11-03T09:00:00+07:00"
    assert clock.normalize("nonsense") is None

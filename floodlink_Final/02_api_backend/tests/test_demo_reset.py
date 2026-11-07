"""Demo data can be removed without touching real reports; a full reset clears everything."""
import base64
from api import service
from agent.router import IntakeAgent

agent = IntakeAgent(strategy="own", log_teacher=False)
DEMO = [{"text": "ช่วยด้วยค่ะ บ้านเลขที่ 3 ซ.ทุ่งเสา 5 ทุ่งเสา ยายอายุ 80 ติดเตียง น้ำถึงชั้น 2", "channel": "facebook_page", "timestamp": "2025-11-24T10:00:00"},
        {"text": "ขอเรือด่วน บ้านเลขที่ 77 ซ.น้ำน้อย 2 น้ำน้อย ผู้ใหญ่ 4 คน น้ำถึงอก", "channel": "line_group", "timestamp": "2025-11-24T10:05:00"}]
REAL = "ช่วยด้วยค่ะ บ้านเลขที่ 12 ซ.ควนลัง 7 ควนลัง ยายอายุ 85 น้ำถึงเอว โทร 081-234-5678"
JPEG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff" + b"\x00" * 50).decode()


def test_delete_demo_keeps_real_cases(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    conn = service.connect(":memory:")
    service.seed_demo(conn, agent, DEMO)
    service.process_batch(conn, agent, REAL, photos=[JPEG])
    assert len(service.list_cases(conn)) == 3
    r = service.delete_demo(conn)
    assert r["cases"] == 2
    left = service.list_cases(conn)
    assert len(left) == 1 and "ควนลัง" in left[0]["first_text"] and len(left[0]["photos"]) == 1


def test_legacy_demo_rows_found_by_text(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    conn = service.connect(":memory:")
    for d in DEMO:                                    # loaded by an older version: no demo marker
        service.process_message(conn, agent, d["text"], d["channel"], d["timestamp"])
    assert service.delete_demo(conn, [d["text"] for d in DEMO])["cases"] == 2
    assert service.list_cases(conn) == []


def test_seed_twice_does_not_duplicate_and_reset_clears_all(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    conn = service.connect(":memory:")
    service.seed_demo(conn, agent, DEMO); service.seed_demo(conn, agent, DEMO)
    assert len(service.list_cases(conn)) == 2
    service.process_batch(conn, agent, REAL, photos=[JPEG])
    assert service.reset_all(conn)["cases"] == 3
    assert service.list_cases(conn) == [] and not list(tmp_path.glob("P-*"))

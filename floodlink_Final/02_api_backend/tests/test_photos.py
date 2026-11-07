"""Photos attached to a report: validated, stored once, shown on every case made from the report."""
import base64
import pytest
from api import service, media
from agent.router import IntakeAgent

agent = IntakeAgent(strategy="own", log_teacher=False)
JPEG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 200).decode()
PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50).decode()


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path / "media"))
    return service.connect(":memory:")


def test_photos_are_stored_and_listed_on_every_case(conn):
    text = """ฝากแชร์ด่วน คลองแห โทร 081-234-5678
เคส 1 บ้านเลขที่ 12 ซ.คลองแห 2 ยายอายุ 85 ติดเตียง น้ำถึงชั้น 2
เคส 2 บ้านเลขที่ 40 ซ.คลองแห 4 ผู้ใหญ่ 3 คน เด็ก 2 ขวบ น้ำถึงอก ไม่มีอาหาร"""
    r = service.process_batch(conn, agent, text, photos=[JPEG, PNG])
    assert len(r["photos"]) == 2 and r["photos"][0]["mime"] == "image/jpeg" and r["n_cases"] == 2
    cases = service.list_cases(conn)
    assert all(len(c["photos"]) == 2 for c in cases)
    msgs = service.case_messages(conn, cases[0]["id"])
    assert len(msgs[0]["photos"]) == 2
    path, mime = media.get(conn, r["photos"][1]["id"])
    assert path.read_bytes().startswith(b"\x89PNG") and mime == "image/png"


def test_bad_photos_are_rejected_before_anything_is_saved(conn):
    with pytest.raises(media.PhotoError):
        service.process_batch(conn, agent, "ช่วยด้วย ซ.ควนลัง 7", photos=["data:text/plain;base64," + base64.b64encode(b"<script>").decode()])
    with pytest.raises(media.PhotoError):
        service.process_batch(conn, agent, "ช่วยด้วย ซ.ควนลัง 7", photos=[JPEG] * 5)
    assert service.list_cases(conn) == []
    assert conn.execute("SELECT COUNT(*) FROM submissions").fetchone()[0] == 0


def test_media_ids_cannot_escape_the_folder(conn):
    assert media.get(conn, "../floodlink.db") is None and media.get(conn, "P-XYZ") is None


def test_report_without_photos_still_works(conn):
    r = service.process_batch(conn, agent, "ช่วยด้วยค่ะ บ้านเลขที่ 12 ซ.ควนลัง 7 ควนลัง ยายอายุ 85 น้ำถึงเอว")
    assert r["photos"] == [] and service.list_cases(conn)[0]["photos"] == []

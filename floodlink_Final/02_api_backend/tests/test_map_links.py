"""A Google Maps link IS a location: no "missing location", short links resolved to a pin, pin gets an area name."""
import pytest
from api import service
from agent.router import IntakeAgent
from floodcommon import location
from floodcommon.triage import nearest_area

agent = IntakeAgent(strategy="own", log_teacher=False)
MSG = "บ้านชั้นเดียว\nตำแหน่ง: https://maps.app.goo.gl/wNqRmZvBPcTXz1sm8\nผู้ใหญ่ 1 คน มีโรคประจำตัว น้ำถึงเอว ขอเรือ น้ำดื่ม"


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    location._cache.clear()
    return service.connect(":memory:")


def test_unresolved_short_link_still_counts_as_location(conn, monkeypatch):
    monkeypatch.setattr(service, "resolve_map_link", lambda url: None)
    r = service.process_batch(conn, agent, MSG)
    c = service.get_case(conn, r["case_id"])
    assert "area" not in c["missing_fields"] and "area" not in r["missing_fields"]
    assert c["nav"]["precision"] == "link" and c["nav"]["url"].startswith("https://maps.app.goo.gl/")
    assert all(n["key"] != "location" for n in r["needs_info"])


def test_short_link_resolved_to_exact_pin_with_area(conn, monkeypatch):
    monkeypatch.setattr(service, "resolve_map_link", lambda url: (7.0081, 100.4975))
    c = service.get_case(conn, service.process_batch(conn, agent, MSG)["case_id"])
    assert c["geo_precision"] == "exact" and c["lat"] == 7.0081 and c["area"] == "คอหงส์"
    assert c["nav"]["url"].startswith("https://www.google.com/maps/dir/") and "area" not in c["missing_fields"]


def test_resolver_parses_final_url_and_never_leaves_google(monkeypatch):
    assert location.coords_in_url("https://www.google.com/maps/place/x/@7.0081,100.4975,17z/data=!3m1") == (7.0081, 100.4975)
    assert location.coords_in_url("https://www.google.com/maps?q=7.0123,100.4712") == (7.0123, 100.4712)
    assert location.resolve_map_link("https://evil.example.com/@7.0081,100.4975") == (7.0081, 100.4975)         # parsed, not fetched
    assert location.resolve_map_link("https://evil.example.com/abc") is None                          # foreign host: no request
    assert location._ALLOWED.match("maps.app.goo.gl") and not location._ALLOWED.match("google.com.evil.io")


def test_old_cases_are_fixed_on_start(tmp_path, monkeypatch):
    db = str(tmp_path / "t.db")
    c = service.connect(db)
    monkeypatch.setattr(service, "resolve_map_link", lambda url: None)
    cid = service.process_batch(c, agent, MSG)["case_id"]
    c.execute("UPDATE cases SET missing_fields='[\"area\",\"contact\"]' WHERE id=?", (cid,)); c.commit()
    assert service.get_case(service.connect(db), cid)["missing_fields"] == ["contact"]


def test_nearest_area():
    assert nearest_area(7.0081, 100.4975) == "คอหงส์" and nearest_area(13.75, 100.5) is None

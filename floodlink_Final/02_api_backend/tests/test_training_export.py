"""Every report is kept and can be exported as training data — personal data masked, demo / team notes left out."""
from api import service, auth
from agent.router import IntakeAgent

agent = IntakeAgent(strategy="own", log_teacher=False)
RED = "ช่วยด้วย นายสมชาย ใจดี ยายอายุ 85 ติดเตียง น้ำถึงชั้น 2 บ้านเลขที่ 9 ซ.สังทิศ 2 คอหงส์ โทร 081-234-5678"


def test_export_masks_pii_and_uses_officer_labels(monkeypatch):
    monkeypatch.setenv("SEED_PASSWORD", "demo-pass-1")
    c = service.connect(":memory:"); auth.seed_accounts(c)
    off = next(u for u in auth.list_users(c) if u["username"] == "officer")
    cid = service.process_batch(c, agent, RED)["case_id"]
    service.process_batch(c, agent, "ขอให้ทุกคนปลอดภัยนะคะ เป็นกำลังใจให้")                       # not a help request: kept too
    service.add_note(c, cid, off, "ถึงแล้ว โทร 089-000-0000")                                    # team note: left out
    service.seed_demo(c, agent, [{"text": "ช่วยด้วย น้ำถึงอก ซ.คลองแห 2 คลองแห", "channel": "web_form", "timestamp": "2026-11-03T09:00:00"}])
    service.add_feedback(c, cid, None, "AI ไม่เห็นว่ายายติดเตียง")
    rows = service.export_training(c)
    assert len(rows) == 2 and {r["message_type"] for r in rows} == {"help_request", rows[1]["message_type"]}
    txt = str(rows)
    assert "081-234-5678" not in txt and "สมชาย" not in txt and "[เบอร์1]" in rows[0]["text"] and "ติดเตียง" in rows[0]["text"]
    assert rows[0]["human_reviewed"] is False and rows[0]["ai_feedback"] == ["AI ไม่เห็นว่ายายติดเตียง"]
    service.correct_ai(c, cid, off, {"flags": ["bedridden"], "priority": "red"})
    r0 = service.export_training(c)[0]
    assert r0["human_reviewed"] and r0["label_source"] == "officer:officer" and r0["flags"] == ["bedridden"]
    assert "081-234-5678" in service.export_training(c, mask_pii=False)[0]["text"]
    assert len(service.export_training(c, include_demo=True)) == 3
    st = service.training_stats(c)
    assert st["rows"] == 2 and st["human_reviewed"] == 1 and st["with_ai_feedback"] == 1

import hashlib, hmac, json
from api import service, facebook
from agent.router import IntakeAgent

AGENT = IntakeAgent(strategy="own", log_teacher=False)
PAGE = "100"


def _comment(cid, text, frm="555", verb="add"):
    return {"object": "page", "entry": [{"id": PAGE, "changes": [{"field": "feed", "value": {
        "item": "comment", "verb": verb, "comment_id": cid, "post_id": PAGE + "_1", "from": {"id": frm, "name": "สมชาย"},
        "message": text, "created_time": 1700000000}}]}]}


def _dm(mid, text, echo=False):
    return {"object": "page", "entry": [{"id": PAGE, "messaging": [{"sender": {"id": "4242"}, "timestamp": 1700000000000,
            "message": {"mid": mid, "text": text, **({"is_echo": True} if echo else {})}}]}]}


def test_signature():
    body = b'{"a":1}'
    sig = "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    assert facebook.verify_signature(body, sig, "s3cret")
    assert not facebook.verify_signature(body, "sha256=00", "s3cret")
    assert not facebook.verify_signature(body, None, "s3cret")


def test_parse_skips_page_own_echo_and_edits():
    assert facebook.parse_events(_comment("c1", "ทดสอบ", frm=PAGE)) == []          # the Page's own comment
    assert facebook.parse_events(_comment("c1", "ทดสอบ", verb="edited")) == []
    assert facebook.parse_events(_dm("m1", "hi", echo=True)) == []
    ev = facebook.parse_events(_comment("1_2", "ช่วยด้วย"))[0]
    assert ev["kind"] == "comment" and ev["author"] == "สมชาย" and ev["url"].endswith("1_2")


def test_webhook_creates_cases_keeps_original_and_dedupes():
    conn = service.connect(":memory:")
    text = "ฝากด้วยครับ คลองแห\nเคส 1 บ้านเลขที่ 12 ซ.คลองแห 2 ยายอายุ 85 ติดเตียง น้ำถึงชั้น 2\nเคส 2 ซ.คลองแห 6 ผู้ใหญ่ 3 คน อาหารหมด น้ำถึงอก"
    events = facebook.parse_events(_comment("111_9", text))
    sent = []
    out = facebook.handle_events(conn, AGENT, events, service, send=lambda ev, t: sent.append(t))
    cases = [c for c in out[0]["cases"] if c]
    assert len(cases) == 2 and sent and "C-" in sent[0]
    msgs = service.case_messages(conn, cases[0])
    assert msgs[0]["raw_text"] == text and msgs[0]["was_split"] and msgs[0]["author"] == "สมชาย"
    assert msgs[0]["source_url"].endswith("111_9") and msgs[0]["channel"] == "fb_comment"
    assert msgs[0]["extraction"]["message_type"] == "help_request"
    # Meta retries the same delivery -> ignored
    assert facebook.handle_events(conn, AGENT, events, service) == []
    assert len(service.list_cases(conn)) == 2


def test_messenger_non_help_goes_to_chatbot():
    class Bot:
        def handle(self, text, sid, *a):
            return {"reply": "**ส่งที่** จุด A", "cards": [{"title": "จุด A", "nav_url": "https://maps/x", "tel": "1"}]}
    conn = service.connect(":memory:")
    out = facebook.handle_events(conn, AGENT, facebook.parse_events(_dm("m9", "มีน้ำ 200 แพ็ค ส่งที่ไหนดี")), service, Bot())
    assert "จุด A" in out[0]["reply"] and "**" not in out[0]["reply"] and "https://maps/x" in out[0]["reply"]


def test_case_messages_and_feedback_web_form():
    conn = service.connect(":memory:")
    r = service.process_batch(conn, AGENT, "ช่วยด้วย บ้านพรุ ผู้ใหญ่ 2 คน น้ำถึงเอว อาหารหมด โทร 081-111-2222")
    cid = r["case_id"]
    m = service.case_messages(conn, cid)
    assert len(m) == 1 and not m[0]["was_split"] and m[0]["raw_text"].startswith("ช่วยด้วย")
    f = service.add_feedback(conn, cid, m[0]["id"], "AI ไม่เห็นว่ามีเด็ก")
    row = conn.execute("SELECT text, note FROM ai_feedback WHERE id=?", (f["id"],)).fetchone()
    assert row["note"] == "AI ไม่เห็นว่ามีเด็ก" and row["text"].startswith("ช่วยด้วย")

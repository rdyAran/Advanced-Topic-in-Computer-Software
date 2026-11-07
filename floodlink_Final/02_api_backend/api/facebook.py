"""Facebook Page webhook -> FloodLink intake (real time).

Page inbox (Messenger) messages and new comments / visitor posts on the Page are pushed here by Meta,
split + read by the Intake AI, and turned into cases. Original text, author and a link back to the
Facebook post/comment are stored with every case.

Pure-Python helpers (parse / verify / handle) are kept separate from the FastAPI router so they can be
unit-tested without FastAPI.

.env:
  FB_VERIFY_TOKEN   any string you choose; type the same string in the Meta dashboard
  FB_APP_SECRET     App settings > Basic > App secret   (used to check X-Hub-Signature-256)
  FB_PAGE_TOKEN     Page access token (only needed for auto-replies)
  FB_AUTO_REPLY     1 = reply in Messenger with the case number / missing info (default 1 when a token is set)
  FB_REPLY_COMMENTS 1 = also reply publicly under comments (default 0)
  FB_GRAPH_VERSION  default v21.0
"""
import hashlib, hmac, json, logging, os, re, threading, urllib.request
from datetime import datetime

log = logging.getLogger("facebook")
_lock = threading.Lock()          # SQLite connection is shared; webhook work runs in a thread pool


def verify_signature(body: bytes, header: str | None, secret: str | None) -> bool:
    if not secret:                # no secret configured -> accept (local testing only; README says to set it)
        return True
    if not header or not header.startswith("sha256="):
        return False
    good = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(good, header[7:])


def parse_events(payload: dict) -> list[dict]:
    """Normalise a Page webhook payload into [{kind, ref, text, author, author_id, reply_to, url, ts}]."""
    out = []
    if payload.get("object") != "page":
        return out
    for entry in payload.get("entry", []):
        page_id = str(entry.get("id", ""))
        for m in entry.get("messaging", []) or []:                 # Messenger inbox
            msg = m.get("message") or {}
            if msg.get("is_echo") or not msg.get("text"):
                continue                                           # our own replies / stickers / images
            psid = str((m.get("sender") or {}).get("id", ""))
            out.append({"kind": "messenger", "ref": "fb:" + msg.get("mid", ""), "text": msg["text"],
                        "author": f"Messenger ผู้ใช้ …{psid[-4:]}", "author_id": psid, "reply_to": psid,
                        "url": None, "ts": _ts(m.get("timestamp"), ms=True)})
        for ch in entry.get("changes", []) or []:                  # Page feed: comments + visitor posts
            v = ch.get("value") or {}
            if ch.get("field") != "feed" or v.get("verb") != "add" or not v.get("message"):
                continue
            item = v.get("item")
            if item not in ("comment", "post", "status"):
                continue
            frm = v.get("from") or {}
            if str(frm.get("id", "")) == page_id and os.getenv("FB_INCLUDE_PAGE_POSTS", "0") != "1":
                continue                                           # the Page's own posts/replies
            ref_id = v.get("comment_id") if item == "comment" else v.get("post_id")
            out.append({"kind": "comment" if item == "comment" else "post", "ref": f"fb:{ref_id}", "text": v["message"],
                        "author": frm.get("name") or "ผู้ใช้ Facebook", "author_id": str(frm.get("id", "")),
                        "reply_to": ref_id, "url": f"https://www.facebook.com/{ref_id}" if ref_id else None,
                        "ts": _ts(v.get("created_time"))})
    return out


def _ts(v, ms: bool = False) -> str | None:
    try:
        return datetime.fromtimestamp(int(v) / (1000 if ms else 1)).isoformat(timespec="seconds") if v else None
    except (TypeError, ValueError):
        return None


CHANNEL = {"messenger": "fb_messenger", "comment": "fb_comment", "post": "fb_post"}
PRIO_TH = {"red": "แดง · วิกฤต", "orange": "ส้ม · เร่งด่วน", "yellow": "เหลือง", "green": "เขียว"}


def handle_events(conn, agent, events: list[dict], service, assistant=None, send=None) -> list[dict]:
    """Process each new event once (Meta retries deliveries -> dedupe on the message/comment id)."""
    done = []
    for ev in events:
        with _lock:
            if conn.execute("SELECT 1 FROM submissions WHERE source_ref=?", (ev["ref"],)).fetchone():
                continue
            try:
                res = service.process_batch(conn, agent, ev["text"], CHANNEL[ev["kind"]], ev["ts"],
                                            author=ev["author"], source_ref=ev["ref"], source_url=ev["url"])
            except Exception as e:                                 # agent down: keep the text so nothing is lost
                log.exception("intake failed for %s", ev["ref"])
                service.save_submission(conn, ev["text"], CHANNEL[ev["kind"]], ev["ts"] or service.now(), 0,
                                        ev["author"], ev["ref"], ev["url"]); conn.commit()
                done.append({"ref": ev["ref"], "error": str(e)}); continue
        reply = build_reply(res, ev, assistant, conn)
        done.append({"ref": ev["ref"], "cases": [r.get("case_id") for r in res.get("results", [])], "reply": reply})
        if reply and send:
            try:
                send(ev, reply)
            except Exception:
                log.exception("reply failed for %s", ev["ref"])
    return done


def build_reply(res: dict, ev: dict, assistant=None, conn=None) -> str | None:
    results = res.get("results") or [res]
    cases = [r for r in results if r.get("action") in ("created", "merged")]
    if cases:
        lines = ["✅ FloodLink รับเรื่องแล้ว"]
        for r in cases:
            row = conn.execute("SELECT priority FROM cases WHERE id=?", (r["case_id"],)).fetchone() if conn else None
            p = PRIO_TH.get(row[0] if row else "", "")
            lines.append(f"• เคส {r['case_id']}" + (" (มีในระบบแล้ว — บันทึกข้อมูลเพิ่มให้)" if r["action"] == "merged" else "")
                         + (f" ระดับ {p}" if p else ""))
        fu = next((r.get("followup") for r in cases if r.get("followup")), None)
        if fu and ev["kind"] == "messenger":                       # ask for missing info privately, not under a public comment
            lines.append("\n" + fu)
        web = os.getenv("PUBLIC_WEB_URL", "").rstrip("/")
        if ev["kind"] == "messenger" and web and res.get("track_token"):   # private chat only — never under a public comment
            lines.append(f"\n🔗 ติดตามเคส / ส่งข้อมูลเพิ่ม: {web}/track/{res['track_token']}")
        lines.append("\nถ้ามีคนอยู่ในอันตรายถึงชีวิต โทร 1669 หรือ 1784 ทันที")
        return "\n".join(lines)
    if ev["kind"] == "messenger" and assistant is not None:       # not a help request -> answer like the web chatbot
        a = assistant.handle(ev["text"], "fb-" + ev["author_id"])
        text = re.sub(r"\*\*|__", "", a.get("reply") or "")
        for c in (a.get("cards") or [])[:3]:
            text += f"\n\n📍 {c['title']}" + (f"\n🧭 {c['nav_url']}" if c.get("nav_url") else "") + (f"\n☎ {c['tel']}" if c.get("tel") else "")
        return text[:1900]                                          # Messenger text limit is 2000 chars
    return None


def graph_sender():
    """Return send(ev, text) that replies through the Graph API, or None if no Page token is configured."""
    token, ver = os.getenv("FB_PAGE_TOKEN"), os.getenv("FB_GRAPH_VERSION", "v21.0")
    if not token or os.getenv("FB_AUTO_REPLY", "1") != "1":
        return None
    reply_comments = os.getenv("FB_REPLY_COMMENTS", "0") == "1"

    def send(ev, text):
        if ev["kind"] == "messenger":
            url, body = f"https://graph.facebook.com/{ver}/me/messages", {
                "recipient": {"id": ev["reply_to"]}, "messaging_type": "RESPONSE", "message": {"text": text}}
        elif reply_comments and ev["kind"] == "comment":
            url, body = f"https://graph.facebook.com/{ver}/{ev['reply_to']}/comments", {"message": text}
        else:
            return
        req = urllib.request.Request(url + f"?access_token={token}", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
    return send


def router(conn, agent, service, assistant=None):
    """FastAPI routes: GET = Meta's one-time verification, POST = events."""
    from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
    r = APIRouter()
    send = graph_sender()

    @r.get("/webhooks/facebook")
    def verify(request: Request):
        q = request.query_params
        if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == os.getenv("FB_VERIFY_TOKEN", "floodlink-dev"):
            return Response(q.get("hub.challenge", ""), media_type="text/plain")
        raise HTTPException(403, "verify token ไม่ตรง")

    @r.post("/webhooks/facebook")
    async def receive(request: Request, bg: BackgroundTasks):
        body = await request.body()
        if not verify_signature(body, request.headers.get("x-hub-signature-256"), os.getenv("FB_APP_SECRET")):
            raise HTTPException(403, "signature ไม่ถูกต้อง")
        events = parse_events(json.loads(body or b"{}"))
        if events:                     # answer Meta within a few seconds; the AI reads in the background
            bg.add_task(handle_events, conn, agent, events, service, assistant, send)
        return {"received": len(events)}

    @r.get("/api/facebook/status")
    def status():
        n = conn.execute("SELECT COUNT(*) FROM submissions WHERE source_ref LIKE 'fb:%'").fetchone()[0]
        last = conn.execute("SELECT received_at FROM submissions WHERE source_ref LIKE 'fb:%' ORDER BY received_at DESC LIMIT 1").fetchone()
        return {"verify_token_set": bool(os.getenv("FB_VERIFY_TOKEN")), "app_secret_set": bool(os.getenv("FB_APP_SECRET")),
                "auto_reply": send is not None, "received": n, "last_received_at": last[0] if last else None}
    return r

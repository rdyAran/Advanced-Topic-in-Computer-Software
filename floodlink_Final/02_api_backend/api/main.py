"""FloodLink API.

Who can call what (see auth.py for the roles):
  public (no login)  report a case, private tracking link, public summary, chatbot, places, intake guide, login
  rescuer            the cases assigned to its team: view, status (in_progress / resolved), notes + photos
  coordinator        whole queue, assign teams, close with a reason, correct the AI, follow-up from a phone call
  admin              + accounts, demo / reset, audit log, training-data export
"""
import json, os, logging
from types import SimpleNamespace
from dotenv import load_dotenv
load_dotenv()
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from floodcommon.schemas import IncomingMessage
from .agent_client import AgentClient
from . import service, facebook, media, auth, teams, ratelimit
from assistant.bot import Assistant
from assistant import places as places_mod

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="FloodLink API Backend", version="0.16.0")
WEB_URL = os.getenv("PUBLIC_WEB_URL", "http://localhost:5173")
# the web app is served from the same origin through the Vite proxy; cookies are never sent cross-site
app.add_middleware(CORSMiddleware, allow_origins=[WEB_URL], allow_methods=["*"], allow_headers=["*"])
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"          # set 1 when served over https

conn = service.connect(os.getenv("DB_PATH", "floodlink.db"))
auth.seed_accounts(conn)
agent = AgentClient()          # 03_intake_ai_agent service

assistant = Assistant(conn, intake=lambda text, ch: service.process_batch(conn, agent, text, ch),
                      get_case=lambda cid: service.get_case(conn, cid),
                      llm_json=agent.llm_json if os.getenv("CHAT_USE_LLM", "1") == "1" else None, web_url=WEB_URL,
                      tracker=SimpleNamespace(view=lambda t: service.track_view(conn, t),
                                              followup=lambda t, cid, text: service.track_followup(conn, agent, t, cid, text),
                                              safe=lambda t, cid: service.track_safe(conn, t, cid)))
app.include_router(facebook.router(conn, agent, service, assistant))     # Facebook Page webhook (real time)
DATASET = Path(os.getenv("DEMO_DATASET", Path(__file__).resolve().parents[2] / "05_evaluation" / "data" / "flood_messages.jsonl"))


# ---------------- auth helpers ----------------
def current_user(request: Request) -> dict | None:
    tok = request.cookies.get(auth.COOKIE)
    h = request.headers.get("authorization", "")
    if not tok and h.lower().startswith("bearer "):
        tok = h[7:].strip()
    return auth.read_token(conn, tok)


def need(role: str):
    def dep(user: dict | None = Depends(current_user)) -> dict:
        if not user:
            raise HTTPException(401, "กรุณาเข้าสู่ระบบ")
        if not auth.has_role(user, role):
            raise HTTPException(403, "บัญชีนี้ไม่มีสิทธิ์ทำรายการนี้")
        return user
    return dep


STAFF, COORD, ADMIN = Depends(need("rescuer")), Depends(need("coordinator")), Depends(need("admin"))


def _case_or_404(cid: str, user: dict) -> dict:
    c = service.get_case(conn, cid)
    if not c or not service.can_see_case(user, c):        # a rescuer gets 404 for other teams' cases (does not leak ids)
        raise HTTPException(404, "case not found")
    return c


class LoginIn(BaseModel):
    username: str
    password: str


@app.post("/api/auth/login")
def login(body: LoginIn, response: Response):
    try:
        u = auth.login(conn, body.username, body.password)
    except auth.AuthError as e:
        raise HTTPException(401, str(e))
    response.set_cookie(auth.COOKIE, auth.make_token(conn, u), httponly=True, samesite="lax", secure=COOKIE_SECURE,
                        max_age=auth.SESSION_HOURS * 3600, path="/")
    auth.audit(conn, u, "login")
    return {"user": u}


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: dict | None = Depends(current_user)):
    return {"user": user}


class PasswordIn(BaseModel):
    old_password: str
    new_password: str


@app.post("/api/auth/password")
def change_password(body: PasswordIn, response: Response, user: dict = STAFF):
    try:
        auth.login(conn, user["username"], body.old_password)
        u = auth.update_user(conn, user["id"], password=body.new_password)
    except auth.AuthError as e:
        raise HTTPException(400, str(e))
    response.set_cookie(auth.COOKIE, auth.make_token(conn, u), httponly=True, samesite="lax", secure=COOKIE_SECURE,
                        max_age=auth.SESSION_HOURS * 3600, path="/")
    auth.audit(conn, user, "change_password")
    return {"user": u}


# ---------------- public ----------------
@app.get("/api/health")
def health():
    return {"ok": True, "agent": agent.health()}


@app.post("/api/messages")
def post_message(msg: IncomingMessage, request: Request, user: dict | None = Depends(current_user)):
    """รับเรื่อง (ผู้ประสบภัย ญาติ หรือเจ้าหน้าที่ที่รับสายโทรศัพท์) — 1 ข้อความอาจมีหลายเคส. คำตอบมี track_token = ลิงก์ติดตามส่วนตัว"""
    client = None if user else ratelimit.client_id(request)
    if client:                                            # public: limits + "pressed send twice" protection
        again = report_limiter.duplicate(client, msg.text)
        if again:
            return {**again, "duplicate_submit": True}
        _limit(report_limiter, client, "report")
    try:
        out = service.process_batch(conn, agent, msg.text, msg.channel, msg.timestamp, photos=msg.photos,
                                    author=user["username"] if user else None, no_training=msg.no_training)
    except media.PhotoError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(503, f"Intake AI Agent ไม่ตอบ: {e}")
    if not auth.has_role(user, "coordinator"):            # a merged case may hold another reporter's exact location
        out.pop("nav", None)
        for r in out.get("results", []):
            r.pop("nav", None)
    if client:
        report_limiter.remember(client, msg.text, out)
    return out


report_limiter = ratelimit.Limiter()
chat_limiter = ratelimit.Limiter(per_min=int(os.getenv("CHAT_PER_MIN", "20")), per_hour=int(os.getenv("CHAT_PER_HOUR", "200")))


def _limit(limiter, client, kind):
    try:
        limiter.check(client, kind)
    except ratelimit.Limited as e:
        raise HTTPException(429, str(e), headers={"Retry-After": str(e.retry_after)})


@app.get("/api/track/{token}")
def track(token: str):
    v = service.track_view(conn, token)
    if not v:
        raise HTTPException(404, "ไม่พบลิงก์ติดตามนี้")
    return v


class TrackFollowupIn(BaseModel):
    case_id: str | None = None
    text: str = ""
    photos: list[str] = []


@app.post("/api/track/{token}/followup")
def track_followup(token: str, body: TrackFollowupIn, request: Request):
    _limit(report_limiter, ratelimit.client_id(request), "track")
    try:
        return service.track_followup(conn, agent, token, body.case_id, body.text, body.photos)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except service.Forbidden as e:
        raise HTTPException(403, str(e))
    except (media.PhotoError, ValueError) as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(503, f"Intake AI Agent ไม่ตอบ: {e}")


class TrackSafeIn(BaseModel):
    case_id: str | None = None


@app.post("/api/track/{token}/safe")
def track_safe(token: str, body: TrackSafeIn):
    try:
        return service.track_safe(conn, token, body.case_id)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except service.Forbidden as e:
        raise HTTPException(403, str(e))


@app.get("/api/media/{pid}")
def get_media(pid: str, track: str | None = None, user: dict | None = Depends(current_user)):
    """Photos are private: staff with access to the case, or the reporter's own tracking link (?track=...)."""
    hit = media.get(conn, pid)
    if not hit or not service.media_allowed(conn, pid, user, track):
        raise HTTPException(404, "photo not found")
    path, mime = hit
    return FileResponse(path, media_type=mime, headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/public/summary")
def public_summary():
    """ตัวเลขสรุป + แผนที่แบบหยาบ (ปัดพิกัด ~1 กม.) — ไม่มีชื่อ เบอร์ บ้านเลขที่ หรือข้อความ"""
    return service.public_summary(conn)


# ---------------- staff: cases ----------------
@app.get("/api/cases")
def get_cases(status: str | None = None, user: dict = STAFF):
    return service.visible_cases(conn, user, status)


@app.get("/api/cases/{cid}")
def get_case(cid: str, user: dict = STAFF):
    return {**_case_or_404(cid, user), "messages": service.case_messages(conn, cid)}


@app.get("/api/cases/{cid}/timeline")
def case_timeline(cid: str, user: dict = STAFF):
    _case_or_404(cid, user)
    return auth.audit_list(conn, cid)


class CasePatch(BaseModel):
    status: str | None = None
    assigned_team: str | None = None
    priority: str | None = None
    close_reason: str | None = None


@app.patch("/api/cases/{cid}")
def patch_case(cid: str, body: CasePatch, user: dict = STAFF):
    c = _case_or_404(cid, user)
    try:
        service.check_update(user, c, body.status, body.assigned_team, body.priority, body.close_reason)
        return service.update_case(conn, cid, body.status, body.assigned_team, body.priority, body.close_reason, user=user)
    except service.Forbidden as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


class NoteIn(BaseModel):
    text: str = ""
    photos: list[str] = []


@app.post("/api/cases/{cid}/note")
def case_note(cid: str, body: NoteIn, user: dict = STAFF):
    """บันทึกจากทีม/เจ้าหน้าที่ (AI ไม่อ่าน ไม่เปลี่ยนข้อมูลเคส) เช่น 'ถึงแล้ว น้ำเชี่ยว เข้าทางหลังวัด' + รูป"""
    _case_or_404(cid, user)
    try:
        return service.add_note(conn, cid, user, body.text, body.photos)
    except (media.PhotoError, ValueError) as e:
        raise HTTPException(400, str(e))


class FollowupIn(BaseModel):
    text: str = ""
    channel: str = "phone_call"
    photos: list[str] = []


@app.post("/api/cases/{cid}/followup")
def case_followup(cid: str, body: FollowupIn, user: dict = COORD):
    """เจ้าหน้าที่ใส่ข้อมูลเพิ่ม (เช่น จากการโทรกลับ) — AI อ่านแล้วรวมเข้าเคสนี้ ตอบว่ายังขาดอะไร"""
    try:
        out = service.add_followup(conn, agent, cid, body.text, body.channel, body.photos, actor=user)
    except (media.PhotoError, ValueError) as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(503, f"Intake AI Agent ไม่ตอบ: {e}")
    if out is None:
        raise HTTPException(404, "case not found")
    return out


class CorrectIn(BaseModel):
    flags: list[str] | None = None
    needs: list[str] | None = None
    water_level: str | None = None
    priority: str | None = None
    adults: int | None = None
    lost_contact: bool | None = None


@app.patch("/api/cases/{cid}/ai")
def correct_ai(cid: str, body: CorrectIn, user: dict = COORD):
    """เจ้าหน้าที่แก้สิ่งที่ AI อ่านผิด -> เคสอัปเดต + เก็บเป็นป้ายสำหรับเทรนรอบหน้า (export ที่ /api/admin/export/corrections.jsonl)"""
    try:
        c = service.correct_ai(conn, cid, user, body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not c:
        raise HTTPException(404, "case not found")
    return c


class FeedbackIn(BaseModel):
    note: str
    message_id: str | None = None


@app.post("/api/cases/{cid}/ai-feedback")
def ai_feedback(cid: str, body: FeedbackIn, user: dict = STAFF):
    """ผู้ช่วยเหลือแจ้งว่า AI อ่านข้อความผิด (ข้อความอิสระ) -> เก็บไว้วิเคราะห์"""
    _case_or_404(cid, user)
    if not body.note.strip():
        raise HTTPException(400, "กรุณาบอกว่าผิดตรงไหน")
    return service.add_feedback(conn, cid, body.message_id, body.note.strip(), user["username"])


class MergeIn(BaseModel):
    target: str


@app.post("/api/cases/{cid}/merge-into")
def merge_into(cid: str, body: MergeIn, user: dict = COORD):
    """เจ้าหน้าที่ยืนยันว่าเป็นบ้านเดียวกัน: ย้ายทุกรายงานไปเคส target รวมข้อมูล แล้วปิดเคสนี้เป็น 'เคสซ้ำ'"""
    try:
        return service.merge_into(conn, cid, body.target, user)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/cases/{cid}/not-duplicate")
def not_duplicate(cid: str, user: dict = COORD):
    c = service.not_duplicate(conn, cid, user)
    if not c:
        raise HTTPException(404, "case not found")
    return c


@app.get("/api/teams")
def get_teams(user: dict = COORD):
    used = [r[0] for r in conn.execute("SELECT DISTINCT assigned_team FROM cases WHERE assigned_team IS NOT NULL")]
    return {"teams": auth.teams(conn), "used": sorted(set(used) - set(auth.teams(conn)))}


@app.get("/api/hazards")
def get_hazards(user: dict = STAFF):
    return [dict(r) for r in conn.execute("SELECT * FROM hazards ORDER BY created_at DESC")]


@app.get("/api/stats")
def get_stats(user: dict = COORD):
    return service.stats(conn)


@app.get("/api/messages")
def get_messages(limit: int = 50, user: dict = COORD):
    return [dict(r) for r in conn.execute("SELECT id, received_at, channel, text, message_type, case_id, action FROM messages ORDER BY received_at DESC LIMIT ?", (limit,))]


@app.get("/api/ai-feedback")
def list_ai_feedback(user: dict = COORD):
    rows = [dict(r) for r in conn.execute("SELECT * FROM ai_feedback ORDER BY created_at DESC")]
    for r in rows:
        r["extraction"] = json.loads(r["extraction"] or "{}")
    return rows


# ---------------- field teams: one team-lead account per team ----------------
def _team_of(user: dict) -> str:
    if not user.get("team"):
        raise HTTPException(400, "บัญชีนี้ไม่ได้ผูกกับชุดปฏิบัติการ")
    return user["team"]


@app.get("/api/team-board")
def team_board(user: dict = COORD):
    """กระดานชุด: สถานะ ตำแหน่งล่าสุด ความจุ งานที่ถืออยู่ + เคสที่มอบหมายแล้วแต่ทีมยังไม่ตอบรับ"""
    return {"teams": teams.board(conn), "late": teams.late(conn), "accept_minutes": teams.ACCEPT_MINUTES,
            "statuses": teams.STATUSES, "kinds": teams.KINDS}


@app.get("/api/cases/{cid}/suggest-teams")
def suggest_teams(cid: str, user: dict = COORD):
    c = _case_or_404(cid, user)
    return teams.suggest_teams(conn, c)


class TeamAccountIn(BaseModel):
    username: str
    password: str
    team: str
    display_name: str = ""
    org: str | None = None
    kind: str | None = None
    phone: str | None = None
    boats: int | None = None
    seats: int | None = None
    has_medic: bool | None = None


class TeamAccountPatch(BaseModel):
    display_name: str | None = None
    active: bool | None = None
    password: str | None = None


class TeamProfileIn(BaseModel):
    org: str | None = None
    kind: str | None = None
    status: str | None = None
    phone: str | None = None
    boats: int | None = None
    seats: int | None = None
    has_medic: bool | None = None
    note: str | None = None
    lat: float | None = None
    lng: float | None = None


@app.get("/api/team-accounts")
def team_accounts(user: dict = COORD):
    return teams.lead_accounts(conn)


@app.post("/api/team-accounts")
def create_team_account(body: TeamAccountIn, user: dict = COORD):
    """ศูนย์สร้างชุด + บัญชีหัวหน้าชุด (1 ชุด = 1 บัญชี หัวหน้าชุดประสานกับลูกทีมเอง)"""
    d = body.model_dump()
    try:
        return teams.create_team(conn, user, d.pop("username"), d.pop("password"), d.pop("team"), d.pop("display_name"), **d)
    except (auth.AuthError, ValueError) as e:
        raise HTTPException(400, str(e))


@app.patch("/api/team-accounts/{uid}")
def update_team_account(uid: str, body: TeamAccountPatch, user: dict = COORD):
    """ศูนย์ตั้งรหัสใหม่ / ปิด-เปิดบัญชีหัวหน้าชุดได้ (แก้บัญชีเจ้าหน้าที่หรือแอดมินไม่ได้)"""
    try:
        teams.check_lead_account(conn, uid)
        u = auth.update_user(conn, uid, **body.model_dump(exclude_unset=True))
    except LookupError as e:
        raise HTTPException(404, str(e))
    except auth.AuthError as e:
        raise HTTPException(400, str(e))
    d = body.model_dump(exclude_unset=True)
    if "password" in d:
        d["password"] = "(changed)"
    auth.audit(conn, user, "user_update", detail={"username": u["username"], **d})
    return u


@app.patch("/api/teams/{name}")
def update_team(name: str, body: TeamProfileIn, user: dict = COORD):
    try:
        return teams.update_profile(conn, name, body.model_dump(exclude_unset=True), user)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/my-team")
def my_team(user: dict = STAFF):
    name = _team_of(user)
    return next((t for t in teams.board(conn) if t["name"] == name), teams._row(conn, name))


@app.patch("/api/my-team")
def update_my_team(body: TeamProfileIn, user: dict = STAFF):
    """หัวหน้าชุดอัปเดต: สถานะชุด (ว่าง/กำลังช่วย/พัก) ตำแหน่งชุด จำนวนเรือ ที่นั่ง มีพยาบาลไหม เบอร์ติดต่อ"""
    try:
        return teams.update_profile(conn, _team_of(user), body.model_dump(exclude_unset=True), user)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/nearby")
def nearby(lat: float | None = None, lng: float | None = None, user: dict = STAFF):
    """เคสที่ยังไม่มีทีม ใกล้ชุด — แสดงเท่าที่ใช้ตัดสินใจ (ไม่มีเบอร์ บ้านเลขที่ ข้อความ รูป) จนกว่าจะกดรับ"""
    _team_of(user)
    return teams.nearby(conn, user, lat, lng)


class DeclineIn(BaseModel):
    reason: str


def _dispatch(fn, *a):
    try:
        return fn(conn, *a)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except service.Forbidden as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/api/cases/{cid}/claim")
def claim_case(cid: str, user: dict = STAFF):
    _team_of(user)
    return _dispatch(teams.claim, user, cid)


@app.post("/api/cases/{cid}/accept")
def accept_case(cid: str, user: dict = STAFF):
    _team_of(user)
    return _dispatch(teams.accept, user, cid)


@app.post("/api/cases/{cid}/decline")
def decline_case(cid: str, body: DeclineIn, user: dict = STAFF):
    _team_of(user)
    return _dispatch(teams.decline, user, cid, body.reason)


# ---------------- admin ----------------
class UserIn(BaseModel):
    username: str
    password: str
    role: str
    display_name: str = ""
    team: str | None = None


class UserPatch(BaseModel):
    role: str | None = None
    team: str | None = None
    display_name: str | None = None
    active: bool | None = None
    password: str | None = None


@app.get("/api/admin/users")
def admin_users(user: dict = ADMIN):
    return auth.list_users(conn)


@app.post("/api/admin/users")
def admin_create_user(body: UserIn, user: dict = ADMIN):
    try:
        u = auth.create_user(conn, body.username, body.password, body.role, body.display_name, body.team)
    except auth.AuthError as e:
        raise HTTPException(400, str(e))
    auth.audit(conn, user, "user_create", detail={"username": u["username"], "role": u["role"], "team": u["team"]})
    return u


@app.patch("/api/admin/users/{uid}")
def admin_update_user(uid: str, body: UserPatch, user: dict = ADMIN):
    try:
        u = auth.update_user(conn, uid, **body.model_dump(exclude_unset=True))
    except auth.AuthError as e:
        raise HTTPException(400, str(e))
    if not u:
        raise HTTPException(404, "user not found")
    d = body.model_dump(exclude_unset=True); d.pop("password", None) and d.update(password="(changed)")
    auth.audit(conn, user, "user_update", detail={"username": u["username"], **d})
    return u


@app.get("/api/admin/audit")
def admin_audit(case_id: str | None = None, limit: int = 300, user: dict = ADMIN):
    return auth.audit_list(conn, case_id, min(limit, 2000))


@app.get("/api/admin/export/corrections.jsonl")
def export_corrections(user: dict = ADMIN):
    rows = service.export_corrections(conn)
    auth.audit(conn, user, "export_corrections", detail={"rows": len(rows)})
    body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    return Response(body, media_type="application/x-ndjson",
                    headers={"Content-Disposition": 'attachment; filename="officer_corrections.jsonl"'})


@app.get("/api/admin/export/training.jsonl")
def export_training(mask: int = 1, demo: int = 0, user: dict = ADMIN):
    """ทุกข้อความที่ AI อ่าน -> ไฟล์ข้อมูลเทรน (ป้ายจาก AI หรือที่เจ้าหน้าที่แก้) — ปิดบังเบอร์/บ้านเลขที่/พิกัด/ชื่อเป็นค่าเริ่มต้น"""
    rows = service.export_training(conn, mask_pii=bool(mask), include_demo=bool(demo))
    auth.audit(conn, user, "export_training", detail={"rows": len(rows), "masked": bool(mask), "demo": bool(demo)})
    body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    return Response(body, media_type="application/x-ndjson",
                    headers={"Content-Disposition": 'attachment; filename="floodlink_training.jsonl"'})


@app.get("/api/admin/system")
def admin_system(user: dict = ADMIN):
    n = lambda t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    return {"agent": agent.health(), "training": service.training_stats(conn), "counts": {t: n(t) for t in ("cases", "messages", "submissions", "attachments", "corrections",
                                                                   "ai_feedback", "users", "audit_log")}}


def _demo_rows(limit: int | None = None) -> list[dict]:
    rows = [json.loads(l) for l in DATASET.open(encoding="utf-8") if l.strip()]
    return rows[:limit] if limit else rows


@app.post("/api/demo/seed")
def seed(limit: int = 40, user: dict = ADMIN):
    """โหลดข้อความจำลองจาก dataset เข้าระบบ (สำหรับเดโม) — ลบเฉพาะเดโมชุดเก่า เคสจริงไม่ถูกลบ. ใช้ LLM จะเสียโควตาตาม limit."""
    out = service.seed_demo(conn, agent, _demo_rows(limit))
    out["scenario"] = teams.demo_scenario(conn, user)          # teams located, 1 in progress, 1 waiting to accept, 2 checked
    auth.audit(conn, user, "demo_seed", detail=out)
    return {**out, "stats": service.stats(conn)}


@app.delete("/api/demo")
def delete_demo(user: dict = ADMIN):
    """ลบเคสเดโมทั้งหมด (รวมที่โหลดจากเวอร์ชันเก่า) — เคสเดโมที่มีรายงานจริงรวมเข้ามาจะไม่ถูกลบ"""
    out = service.delete_demo(conn, [r["text"] for r in _demo_rows()])
    auth.audit(conn, user, "demo_delete", detail=out)
    return {**out, "stats": service.stats(conn)}


@app.post("/api/admin/reset")
def reset(confirm: str = "", user: dict = ADMIN):
    """ล้างข้อมูลทั้งหมด (เคส ข้อความ รูป) — ต้องส่ง ?confirm=DELETE-ALL กันกดพลาด. บัญชีผู้ใช้และ audit log ยังอยู่"""
    if confirm != "DELETE-ALL":
        raise HTTPException(400, "ต้องส่ง confirm=DELETE-ALL")
    out = service.reset_all(conn)
    auth.audit(conn, user, "reset_all", detail=out)
    return {**out, "stats": service.stats(conn)}


# ---------------- public info ----------------
@app.get("/api/intake-guide")
def intake_guide():
    """ข้อมูลที่ควรกรอกเพื่อให้ช่วยได้เร็วที่สุด (หน้าเว็บ / LINE bot ใช้แสดงคำแนะนำ)"""
    return INTAKE_GUIDE


INTAKE_GUIDE = {
    "title": "ข้อมูลที่ทำให้ทีมไปถึงเร็วที่สุด",
    "items": [
        {"key": "location", "label": "ตำแหน่ง", "why": "สำคัญที่สุด — ทีมต้องรู้ว่าจะไปที่ไหน",
         "examples": ["แชร์พิกัด/ลิงก์ Google Maps", "บ้านเลขที่ ซอย ถนน", "จุดสังเกต เช่น ตรงข้ามเซเว่น หลังวัด"]},
        {"key": "contact", "label": "เบอร์โทรที่ติดต่อได้ + แบตเหลือเท่าไหร่", "why": "ทีมโทรยืนยันจุดและนัดเวลาได้",
         "examples": ["081-234-5678 แบตเหลือ 20%", "เบอร์ญาติที่อยู่นอกพื้นที่"]},
        {"key": "people", "label": "จำนวนคน", "why": "เลือกขนาดเรือ/จำนวนรอบ",
         "examples": ["ผู้ใหญ่ 4 เด็ก 2 (1 ขวบ, 5 ขวบ)", "ผู้สูงอายุ 85 ปี 1 คน"]},
        {"key": "vulnerable", "label": "ผู้ป่วย / กลุ่มเปราะบาง", "why": "ใช้จัดลำดับเร่งด่วน (สีแดง)",
         "examples": ["ติดเตียง", "ฟอกไต", "โรคหัวใจ", "ตั้งครรภ์", "บาดเจ็บ", "ทารก", "พิการ/เดินไม่ได้"]},
        {"key": "water", "label": "ระดับน้ำตอนนี้", "why": "บอกว่าอันตรายแค่ไหน และเรือแบบไหนเข้าได้",
         "examples": ["เข่า / เอว / อก", "มิดชั้น 1", "ถึงชั้น 2", "อยู่บนหลังคา"]},
        {"key": "building", "label": "ที่พักเป็นแบบไหน กี่ชั้น", "why": "บ้านชั้นเดียวน้ำถึงเอวอันตรายกว่าบ้าน 2 ชั้นที่ยังขึ้นชั้นบนได้ — ทีมใช้จัดลำดับและเลือกเรือ",
         "examples": ["บ้านชั้นเดียว น้ำท่วมเอว", "บ้าน 2 ชั้น น้ำท่วมชั้น 1 ยังไม่ถึงชั้น 2", "ตึกแถว 3 ชั้น อยู่ชั้น 3", "คอนโด ชั้น 5 ลงมาไม่ได้"]},
        {"key": "needs", "label": "สิ่งที่ต้องการ", "why": "ทีมเตรียมของไปถูกตั้งแต่รอบแรก",
         "examples": ["ขอเรืออพยพ", "อาหาร น้ำดื่ม", "นมเด็ก", "ยาประจำตัว", "พาวเวอร์แบงค์"]},
        {"key": "access", "label": "ทางเข้า / อุปสรรค", "why": "ทีมไม่ต้องเสียเวลาหาทาง",
         "examples": ["ซอยตัน น้ำเชี่ยว", "มีรถจมขวางปากซอย", "เข้าทางหลังวัดได้"]},
        {"key": "time", "label": "ติดมานานแค่ไหน", "why": "ยิ่งนาน อาหาร/ยา ยิ่งวิกฤต", "examples": ["ติดมา 3 วัน"]},
    ],
    "multi_case_tip": "มีหลายบ้านในข้อความเดียวได้ — ขึ้นบรรทัดใหม่แล้วใส่ 'เคส 1', 'เคส 2' หน้าแต่ละบ้าน",
    "template": "ตำแหน่ง: \nเบอร์ติดต่อ: (แบตเหลือ  %)\nจำนวนคน: ผู้ใหญ่  เด็ก  ผู้สูงอายุ \nผู้ป่วย/กลุ่มเปราะบาง: \nที่พัก: \nระดับน้ำ: \nต้องการ: \nทางเข้า/อุปสรรค: \nติดมาแล้ว:  วัน",
}


# ---------------- chatbot + places ----------------
class ChatIn(BaseModel):
    message: str
    session_id: str = "anon"
    lat: float | None = None
    lng: float | None = None


@app.post("/api/chat")
def chat(body: ChatIn, request: Request, user: dict | None = Depends(current_user)):
    """FloodLink Assistant: donors, victims, relatives, volunteers. Replies carry map/page links."""
    if not user:
        _limit(chat_limiter, ratelimit.client_id(request), "chat")
    return assistant.handle(body.message, body.session_id, body.lat, body.lng)


@app.get("/api/places")
def get_places(type: str | None = None):
    return places_mod.list_places(conn, type)


@app.post("/api/places")
def add_place(place: dict, user: dict = COORD):
    """เพิ่ม/แก้จุดรับของ ศูนย์พักพิง จุดแจกของ (ศูนย์บัญชาการใช้) — ต้องมี id, type, name และ lat/lng หรือ area"""
    if not place.get("id") or place.get("type") not in places_mod.TYPES or not place.get("name"):
        raise HTTPException(400, f"ต้องมี id, name และ type หนึ่งใน {list(places_mod.TYPES)}")
    auth.audit(conn, user, "place_upsert", detail={"id": place["id"], "name": place["name"]})
    return places_mod.upsert(conn, place)


@app.get("/api/needs-summary")
def needs_summary():
    return places_mod.needs_summary(conn, top=20)

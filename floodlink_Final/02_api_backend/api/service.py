"""Pipeline + storage (SQLite, stdlib only).

process_message():  raw text -> Intake AI Agent (03) -> route by type
    help_request            -> Verify Agent -> merge into existing case OR create new case
    status_update_resolved  -> close the matching open case
    hazard_report           -> pin on hazard map
    donation_offer/irrelevant -> keep in log only
"""
import json, secrets, sqlite3, uuid, datetime as dt
from floodcommon.schemas import Extraction, MessageType, WaterLevel, Flag
from floodcommon.triage import priority, missing_fields, followup_message, geocode, nearest_area, people_total, clean_form_text, form_water, WATER_SEVERITY, PRIORITY_RANK
from floodcommon.location import extract_location, nav_url, resolve_map_link
from floodcommon import clock
from .verify import CaseView, find_duplicate, find_case_for_update, best_match, SUGGEST_THRESHOLD
from . import media, auth
from .db import LockedConnection

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
  id TEXT PRIMARY KEY, created_at TEXT, updated_at TEXT,
  status TEXT DEFAULT 'new', priority TEXT, priority_reason TEXT, priority_locked INTEGER DEFAULT 0,
  area TEXT, street TEXT, landmark TEXT, house_no TEXT, lat REAL, lng REAL,
  adults INTEGER, children_ages TEXT, elderly_ages TEXT, flags TEXT, needs TEXT,
  water_level TEXT, days_trapped INTEGER, contact TEXT, summary TEXT,
  missing_fields TEXT, report_count INTEGER DEFAULT 1, assigned_team TEXT, first_text TEXT,
  geo_precision TEXT, map_url TEXT, close_reason TEXT, closed_at TEXT, children_count INTEGER, elderly_count INTEGER,
  building_floors INTEGER, possible_dup TEXT, possible_dup_score REAL
);
CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY, received_at TEXT, channel TEXT, text TEXT,
  message_type TEXT, case_id TEXT, action TEXT, extraction TEXT,
  provider TEXT, escalated INTEGER, confidence REAL, latency_ms INTEGER, batch_id TEXT
);
CREATE TABLE IF NOT EXISTS submissions (
  id TEXT PRIMARY KEY, received_at TEXT, channel TEXT, raw_text TEXT, n_cases INTEGER,
  author TEXT, source_ref TEXT, source_url TEXT, track_token TEXT, no_training INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_sub_ref ON submissions(source_ref);
CREATE TABLE IF NOT EXISTS corrections (
  id TEXT PRIMARY KEY, created_at TEXT, case_id TEXT, actor TEXT, texts TEXT, before TEXT, after TEXT
);
CREATE TABLE IF NOT EXISTS ai_feedback (
  id TEXT PRIMARY KEY, created_at TEXT, case_id TEXT, message_id TEXT, text TEXT, extraction TEXT, note TEXT, reporter TEXT
);
CREATE TABLE IF NOT EXISTS hazards (
  id TEXT PRIMARY KEY, created_at TEXT, area TEXT, lat REAL, lng REAL, text TEXT
);
"""
JSON_COLS = ("children_ages", "elderly_ages", "flags", "needs", "missing_fields")
OPEN = ("new", "verified", "assigned", "in_progress")


def now() -> str:
    return clock.now_iso()                 # Thailand time with +07:00 (see floodcommon/clock.py)


def connect(path: str = "floodlink.db") -> sqlite3.Connection:
    conn = LockedConnection(sqlite3.connect(path, check_same_thread=False))   # thread-safe: see db.py
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    migrations = {"messages": [("provider", "TEXT"), ("escalated", "INTEGER"), ("confidence", "REAL"), ("latency_ms", "INTEGER"), ("batch_id", "TEXT"),
                             ("submission_id", "TEXT")],
                  "cases": [("geo_precision", "TEXT"), ("map_url", "TEXT"), ("close_reason", "TEXT"), ("closed_at", "TEXT"),
                            ("assign_state", "TEXT"), ("assigned_at", "TEXT"), ("accepted_at", "TEXT"),
                            ("children_count", "INTEGER"), ("elderly_count", "INTEGER"), ("building_floors", "INTEGER"),
                            ("possible_dup", "TEXT"), ("possible_dup_score", "REAL")],
                  "submissions": [("track_token", "TEXT"), ("no_training", "INTEGER DEFAULT 0")]}
    for table, cols in migrations.items():   # upgrade databases created by older versions
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, typ in cols:
            if col not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_sub_track ON submissions(track_token)")
    media.init(conn)
    auth.init(conn)
    _fix_link_locations(conn)
    clock.upgrade_naive_times(conn)       # older versions saved UTC without an offset -> looked 7 h old in Thailand
    return conn


def _fix_link_locations(conn):
    """Cases saved by older versions said "missing location" although the reporter sent a map link / GPS."""
    for cid, miss in conn.execute("""SELECT id, missing_fields FROM cases WHERE (map_url IS NOT NULL OR geo_precision='exact')
                                     AND missing_fields LIKE '%"area"%'""").fetchall():
        conn.execute("UPDATE cases SET missing_fields=? WHERE id=?", (json.dumps([m for m in json.loads(miss) if m != "area"]), cid))
    conn.commit()


def row_to_case(r: sqlite3.Row) -> dict:
    d = dict(r)
    for k in JSON_COLS:
        d[k] = json.loads(d[k] or "[]")
    d["nav"] = nav_url(d)       # Google Maps directions for the rescue team
    d["people_total"] = people_total(d)
    return d


def list_cases(conn, status: str | None = None) -> list[dict]:
    q, args = "SELECT * FROM cases", ()
    if status == "open":
        q += f" WHERE status IN ({','.join('?' * len(OPEN))})"; args = OPEN
    elif status:
        q += " WHERE status = ?"; args = (status,)
    rows = [row_to_case(r) for r in conn.execute(q, args)]
    photos = media.for_cases(conn)
    t_now = clock.now()
    for c in rows:
        c["photos"] = photos.get(c["id"], [])
        c["waiting_accept_min"] = None              # minutes a team has not answered an assignment
        if c.get("assign_state") == "pending" and c.get("assigned_at") and c["status"] != "resolved":
            c["waiting_accept_min"] = max(int((t_now - clock.parse(c["assigned_at"])).total_seconds() // 60), 0)
    rank = {"red": 0, "orange": 1, "yellow": 2, "green": 3}
    return sorted(rows, key=lambda c: (c["status"] == "resolved", rank.get(c["priority"], 9), c["created_at"]))


def _open_views(conn) -> list[CaseView]:
    return [CaseView(case_id=c["id"], area=c["area"], text=c["first_text"] or "", adults=c["adults"],
                     elderly_ages=c["elderly_ages"], children_ages=c["children_ages"], flags=c["flags"],
                     house_no=c["house_no"], street=c["street"]) for c in list_cases(conn, "open")]


def _locate(e: Extraction, text: str):
    """Exact GPS / map link from the message if present, otherwise the area centroid."""
    loc = extract_location(text)
    if loc["precision"] == "link":                       # short maps.app.goo.gl link: ask Google where it points
        hit = resolve_map_link(loc["map_url"])
        if hit:
            return hit[0], hit[1], "exact", loc["map_url"]
    if loc["precision"] == "exact":
        return loc["lat"], loc["lng"], "exact", loc["map_url"]
    lat, lng = geocode(e.area)
    return lat, lng, (loc["precision"] or ("area" if lat is not None else None)), loc["map_url"]


def _create_case(conn, e: Extraction, text: str, ts: str) -> str:
    cid = "C-" + uuid.uuid4().hex[:6].upper()
    color, reason = priority(e)
    lat, lng, prec, map_url = _locate(e, text)
    if not e.area and prec == "exact":
        e.area = nearest_area(lat, lng)                  # a pin from a map link still gets an area name
    conn.execute(
        """INSERT INTO cases (id, created_at, updated_at, priority, priority_reason, area, street, landmark, house_no,
           lat, lng, adults, children_ages, elderly_ages, flags, needs, water_level, days_trapped, contact, summary,
           missing_fields, first_text, geo_precision, map_url) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (cid, ts, ts, color, reason, e.area, e.street, e.landmark, e.house_no, lat, lng, e.adults,
         json.dumps(e.children_ages), json.dumps(e.elderly_ages), json.dumps([f.value for f in e.flags]),
         json.dumps([n.value for n in e.needs]), e.water_level.value if e.water_level else None, e.days_trapped,
         e.contact, e.summary, json.dumps(missing_fields(e, prec in ("exact", "link"))), text, prec, map_url))
    conn.execute("UPDATE cases SET children_count=?, elderly_count=?, building_floors=? WHERE id=?",
                 (e.children_count, e.elderly_count, e.building_floors, cid))
    return cid


def _merge_case(conn, cid: str, e: Extraction, ts: str, text: str = ""):
    """A new report about an existing case: combine info, keep the worst condition."""
    c = row_to_case(conn.execute("SELECT * FROM cases WHERE id=?", (cid,)).fetchone())
    merged = Extraction(
        message_type=MessageType.help_request,
        area=c["area"] or e.area, street=c["street"] or e.street, landmark=c["landmark"] or e.landmark,
        house_no=c["house_no"] or e.house_no,
        adults=max(filter(None, [c["adults"], e.adults]), default=None),
        children_ages=sorted(set(c["children_ages"]) | set(e.children_ages)),
        elderly_ages=sorted(set(c["elderly_ages"]) | set(e.elderly_ages)),
        children_count=max(filter(None, [c.get("children_count"), e.children_count]), default=None),
        elderly_count=max(filter(None, [c.get("elderly_count"), e.elderly_count]), default=None),
        building_floors=e.building_floors or c.get("building_floors"),       # the latest report knows best
        flags=sorted(set(c["flags"]) | {f.value for f in e.flags}),
        needs=sorted(set(c["needs"]) | {n.value for n in e.needs}),
        water_level=max(filter(None, [c["water_level"] and WaterLevel(c["water_level"]), e.water_level]),
                        key=lambda w: WATER_SEVERITY[w], default=None),
        days_trapped=max(filter(None, [c["days_trapped"], e.days_trapped]), default=None),
        contact=c["contact"] or e.contact, summary=c["summary"] or e.summary,
        lost_contact=e.lost_contact, priority_hint=e.priority_hint, priority_hint_reason=e.priority_hint_reason,
    )
    color, reason = priority(merged)
    if (c["priority_reason"] or "").startswith("AI:") and PRIORITY_RANK.get(c["priority"], 9) < PRIORITY_RANK[color]:
        color, reason = c["priority"], c["priority_reason"]      # an earlier report's AI-raised colour is kept
    if c["priority_locked"]:
        color, reason = c["priority"], c["priority_reason"]
    lat, lng, prec, map_url = c["lat"], c["lng"], c["geo_precision"], c["map_url"]
    nlat, nlng, nprec, nurl = _locate(merged, text)
    if (nprec == "exact" and prec != "exact") or lat is None:   # a later report brought a better location
        lat, lng, prec = nlat, nlng, nprec
    map_url = map_url or nurl
    if not merged.area and prec == "exact":
        merged.area = nearest_area(lat, lng)
    conn.execute("UPDATE cases SET geo_precision=?, map_url=?, children_count=?, elderly_count=?, building_floors=? WHERE id=?",
                 (prec, map_url, merged.children_count, merged.elderly_count, merged.building_floors, cid))
    conn.execute(
        """UPDATE cases SET updated_at=?, priority=?, priority_reason=?, area=?, street=?, landmark=?, house_no=?,
           lat=?, lng=?, adults=?, children_ages=?, elderly_ages=?, flags=?, needs=?, water_level=?, days_trapped=?,
           contact=?, missing_fields=?, report_count=report_count+1 WHERE id=?""",
        (ts, color, reason, merged.area, merged.street, merged.landmark, merged.house_no, lat, lng, merged.adults,
         json.dumps(merged.children_ages), json.dumps(merged.elderly_ages), json.dumps([f.value for f in merged.flags]),
         json.dumps([n.value for n in merged.needs]), merged.water_level.value if merged.water_level else None,
         merged.days_trapped, merged.contact, json.dumps(missing_fields(merged, prec in ("exact", "link") or bool(map_url))), cid))


def save_submission(conn, raw_text: str, channel: str, ts: str, n_cases: int = 1, author: str | None = None,
                    source_ref: str | None = None, source_url: str | None = None) -> str:
    """Keep the ORIGINAL text exactly as received (before splitting / AI reading) — for rescuers and for auditing AI mistakes."""
    sid = "S-" + uuid.uuid4().hex[:8].upper()
    conn.execute("""INSERT INTO submissions (id, received_at, channel, raw_text, n_cases, author, source_ref, source_url, track_token)
                    VALUES (?,?,?,?,?,?,?,?,?)""", (sid, ts, channel, raw_text, n_cases, author, source_ref, source_url, new_track_token()))
    return sid


def new_track_token() -> str:
    """Private link for the reporter (no login): 128 random bits, URL-safe."""
    return secrets.token_urlsafe(16)


def process_message(conn, agent, text: str, channel: str = "web_form", ts: str | None = None, batch_id: str | None = None,
                    submission_id: str | None = None) -> dict:
    ts = clock.normalize(ts) or now()
    submission_id = submission_id or save_submission(conn, text, channel, ts)
    e = agent.run(clean_form_text(text))               # blank template lines removed for the AI only
    fw = form_water(text)
    if fw and e.message_type == MessageType.help_request:
        e.water_level = fw                                # the form answer is explicit — fixed rule beats the model
    case_id, action, followup, dup_score = None, "logged", None, None

    if e.message_type == MessageType.help_request:
        views = _open_views(conn)
        case_id, dup_score = find_duplicate(e, text, views)
        if case_id:
            _merge_case(conn, case_id, e, ts, text); action = "merged"
        else:
            maybe, maybe_score = best_match(e, text, views)
            case_id = _create_case(conn, e, text, ts); action = "created"
            if maybe and maybe_score >= SUGGEST_THRESHOLD:     # not sure enough to merge: the officer decides
                conn.execute("UPDATE cases SET possible_dup=?, possible_dup_score=? WHERE id=?", (maybe, round(maybe_score, 2), case_id))
        auth.audit(conn, f"reporter:{channel}", action, case_id, {"submission": submission_id}, commit=False)
        stored = json.loads(conn.execute("SELECT missing_fields FROM cases WHERE id=?", (case_id,)).fetchone()[0] or "[]")
        followup = followup_message(stored) if action == "created" else None
    elif e.message_type == MessageType.status_update_resolved:
        cid, _ = find_case_for_update(e, text, _open_views(conn))
        if cid:
            conn.execute("UPDATE cases SET status='resolved', close_reason='self_safe', closed_at=?, updated_at=? WHERE id=?", (ts, ts, cid))
            case_id, action = cid, "resolved"
            auth.audit(conn, f"reporter:{channel}", "close", cid, {"close_reason": "self_safe", "via": "message"}, commit=False)
    elif e.message_type == MessageType.hazard_report:
        lat, lng, _, _ = _locate(e, text)
        conn.execute("INSERT INTO hazards VALUES (?,?,?,?,?,?)", ("H-" + uuid.uuid4().hex[:6].upper(), ts, e.area, lat, lng, text))
        action = "hazard"

    mid = "M-" + uuid.uuid4().hex[:8].upper()
    meta = getattr(agent, "last", None) or {}
    conn.execute("""INSERT INTO messages (id, received_at, channel, text, message_type, case_id, action, extraction,
                    provider, escalated, confidence, latency_ms, batch_id, submission_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (mid, ts, channel, text, e.message_type.value, case_id, action, e.model_dump_json(),
                  meta.get("provider_used"), int(bool(meta.get("escalated"))), meta.get("confidence"), meta.get("latency_ms"), batch_id,
                  submission_id))
    conn.commit()
    return {"message_id": mid, "submission_id": submission_id, "message_type": e.message_type.value, "action": action, "case_id": case_id,
            "duplicate_score": round(dup_score, 2) if dup_score is not None else None,
            "extraction": json.loads(e.model_dump_json()), "followup": followup,
            "missing_fields": (stored if action == "created" else []) if e.message_type == MessageType.help_request else [],
            **_case_brief(conn, case_id),
            "nav": nav_url(row_to_case(conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone())) if case_id else None,
            **{k: v for k, v in (getattr(agent, "last", None) or {}).items()}}


STATUSES = ("new", "verified", "assigned", "in_progress", "resolved")
CLOSE_REASONS = {"rescued": "ช่วยแล้ว", "duplicate": "เคสซ้ำ", "not_found": "ไปแล้วไม่พบ", "self_safe": "ปลอดภัยเอง/ผู้แจ้งแจ้งว่าปลอดภัย"}
PRIORITIES = ("red", "orange", "yellow", "green")
RESCUER_STATUSES = ("in_progress", "resolved")
RESCUER_CLOSE = ("rescued", "not_found")


class Forbidden(PermissionError):
    pass


def _case_brief(conn, cid: str | None) -> dict:
    """For the reporter's screen right after sending: the colour and what the team still needs (readiness)."""
    if not cid:
        return {}
    c = get_case(conn, cid)
    if not c:
        return {}
    need = [r for r in readiness(c) if r["level"] == "need" and r["state"] != "ok"]
    return {"priority": c["priority"], "status": c["status"], "needs_info": need}


def update_case(conn, cid: str, status=None, assigned_team=None, priority_override=None, close_reason=None,
                user: dict | str | None = None) -> dict | None:
    """Status / team / colour change by staff. Every change goes to the audit log (who, what, before -> after)."""
    c = conn.execute("SELECT * FROM cases WHERE id=?", (cid,)).fetchone()
    if not c:
        return None
    ts = now()
    if status is not None and status not in STATUSES:
        raise ValueError(f"status ต้องเป็นหนึ่งใน {STATUSES}")
    if close_reason is not None and close_reason not in CLOSE_REASONS:
        raise ValueError(f"close_reason ต้องเป็นหนึ่งใน {list(CLOSE_REASONS)}")
    if priority_override is not None and priority_override not in PRIORITIES:
        raise ValueError(f"priority ต้องเป็นหนึ่งใน {PRIORITIES}")
    if assigned_team is not None:
        team = assigned_team.strip() or None
        new_status = "assigned" if team and c["status"] in ("new", "verified") else ("verified" if not team and c["status"] == "assigned" else c["status"])
        # a newly assigned team must ACCEPT (or decline) — see teams.accept / teams.decline
        conn.execute("UPDATE cases SET assigned_team=?, status=?, assign_state=?, assigned_at=?, accepted_at=NULL WHERE id=?",
                     (team, new_status, "pending" if team else None, ts if team else None, cid))
        auth.audit(conn, user, "assign", cid, {"from": c["assigned_team"], "to": team}, commit=False)
    if status == "in_progress" and c["assigned_team"] and c["assign_state"] == "pending":
        conn.execute("UPDATE cases SET assign_state='accepted', accepted_at=? WHERE id=?", (ts, cid))   # starting = accepting
    if status and status != c["status"]:
        if status == "resolved":
            reason = close_reason or "rescued"
            conn.execute("UPDATE cases SET status='resolved', close_reason=?, closed_at=? WHERE id=?", (reason, ts, cid))
            auth.audit(conn, user, "close", cid, {"from": c["status"], "close_reason": reason}, commit=False)
        else:
            conn.execute("UPDATE cases SET status=?, close_reason=NULL, closed_at=NULL WHERE id=?", (status, cid))
            auth.audit(conn, user, "reopen" if c["status"] == "resolved" else "status", cid, {"from": c["status"], "to": status}, commit=False)
    elif close_reason and c["status"] == "resolved" and close_reason != c["close_reason"]:
        conn.execute("UPDATE cases SET close_reason=? WHERE id=?", (close_reason, cid))
        auth.audit(conn, user, "close", cid, {"close_reason": close_reason}, commit=False)
    if priority_override:
        conn.execute("UPDATE cases SET priority=?, priority_reason=?, priority_locked=1 WHERE id=?",
                     (priority_override, "เจ้าหน้าที่ปรับระดับเอง", cid))
        auth.audit(conn, user, "priority", cid, {"from": c["priority"], "to": priority_override}, commit=False)
    conn.execute("UPDATE cases SET updated_at=? WHERE id=?", (ts, cid))
    conn.commit()
    return get_case(conn, cid)


def get_case(conn, cid: str) -> dict | None:
    return next((c for c in list_cases(conn) if c["id"] == cid), None)


# ---------------- who may see / change what ----------------
def visible_cases(conn, user: dict, status: str | None = None) -> list[dict]:
    """coordinator/admin: every case. rescuer: only the cases assigned to its team (open AND closed, so it sees its history)."""
    rows = list_cases(conn, status)
    if auth.has_role(user, "coordinator"):
        return rows
    return [c for c in rows if user.get("team") and c["assigned_team"] == user["team"]]


def can_see_case(user: dict | None, case: dict | None) -> bool:
    if not user or not case:
        return False
    return auth.has_role(user, "coordinator") or bool(user.get("team") and case.get("assigned_team") == user["team"])


def check_update(user: dict, case: dict, status=None, assigned_team=None, priority=None, close_reason=None):
    """Rescuers may only move THEIR case to in_progress / resolved(rescued|not_found). Raises Forbidden."""
    if auth.has_role(user, "coordinator"):
        return
    if not can_see_case(user, case):
        raise Forbidden("เคสนี้ไม่ได้มอบหมายให้ทีมของคุณ")
    if assigned_team is not None or priority is not None:
        raise Forbidden("ทีมกู้ภัยเปลี่ยนทีมหรือสีของเคสไม่ได้ (ให้ศูนย์ประสานทำ)")
    if status is not None and status not in RESCUER_STATUSES:
        raise Forbidden("ทีมกู้ภัยตั้งได้แค่ 'กำลังช่วย' หรือ 'ปิดเคส'")
    if (status == "resolved" or close_reason) and (close_reason or "rescued") not in RESCUER_CLOSE:
        raise Forbidden("ทีมกู้ภัยปิดเคสได้แค่ 'ช่วยแล้ว' หรือ 'ไม่พบ'")


def media_allowed(conn, pid: str, user: dict | None = None, track: str | None = None) -> bool:
    """A photo is shown to: coordinator/admin; the team assigned to a case it belongs to; the reporter who sent it (track link)."""
    r = conn.execute("SELECT submission_id FROM attachments WHERE id=?", (pid,)).fetchone()
    if not r:
        return False
    if auth.has_role(user, "coordinator"):
        return True
    if user and user.get("team"):
        if conn.execute("""SELECT 1 FROM messages m JOIN cases c ON c.id=m.case_id
                           WHERE m.submission_id=? AND c.assigned_team=? LIMIT 1""", (r[0], user["team"])).fetchone():
            return True
    if track:
        sub = conn.execute("SELECT id FROM submissions WHERE track_token=?", (track,)).fetchone()
        if sub and (sub[0] == r[0] or r[0] in _track_followup_sids(conn, track)):
            return True
    return False


# ---------------- reporter tracking link (no login) ----------------
TIMELINE_TH = {"created": "รับเรื่องแล้ว — เข้าคิวศูนย์ประสาน", "merged": "มีคนแจ้งบ้านนี้เพิ่ม — รวมข้อมูลให้แล้ว",
               "followup": "ได้รับข้อมูลเพิ่มเติม", "note": "ทีมบันทึกความคืบหน้า"}
STATUS_TH = {"new": "รอเจ้าหน้าที่ตรวจ", "verified": "เจ้าหน้าที่ตรวจแล้ว รอทีม", "assigned": "มีทีมรับเคสแล้ว",
             "in_progress": "ทีมกำลังเข้าช่วย", "resolved": "ปิดเคสแล้ว"}


TRACK_DAYS_AFTER_CLOSE = int(__import__("os").getenv("TRACK_DAYS_AFTER_CLOSE", "30"))


def _submission_by_token(conn, token: str):
    """The reporter's private link. It stops working TRACK_DAYS_AFTER_CLOSE days after ALL its cases were closed,
    so an old link found later in a chat history no longer shows the case."""
    if not token or len(token) < 16:
        return None
    s = conn.execute("SELECT * FROM submissions WHERE track_token=?", (token,)).fetchone()
    if not s:
        return None
    rows = conn.execute("""SELECT c.status, c.closed_at FROM cases c WHERE c.id IN
                           (SELECT DISTINCT case_id FROM messages WHERE submission_id=? AND case_id IS NOT NULL)""", (s["id"],)).fetchall()
    if rows and all(r["status"] == "resolved" for r in rows):
        closed = [clock.parse(r["closed_at"]) for r in rows if r["closed_at"]]
        if closed and (clock.now() - max(closed)).days >= TRACK_DAYS_AFTER_CLOSE:
            return None
    return s


def track_case_ids(conn, token: str) -> list[str]:
    s = _submission_by_token(conn, token)
    if not s:
        return []
    return [r[0] for r in conn.execute("SELECT DISTINCT case_id FROM messages WHERE submission_id=? AND case_id IS NOT NULL "
                                       "ORDER BY rowid", (s["id"],))]


def _track_followup_sids(conn, token: str) -> set[str]:
    return {r[0] for r in conn.execute("SELECT id FROM submissions WHERE source_ref=?", (f"track:{token}",))}


def public_timeline(conn, cid: str) -> list[dict]:
    """Case history in plain words for the reporter: no staff names, no other reporters' text."""
    out = []
    for a in reversed(auth.audit_list(conn, cid, 100)):
        d, act = a["detail"], a["action"]
        if act in TIMELINE_TH:
            text = TIMELINE_TH[act]
        elif act == "assign":
            text = f"มอบหมายให้ {d['to']}" if d.get("to") else "ยกเลิกทีมที่รับ — รอทีมใหม่"
        elif act == "accept":
            text = f"{d.get('team', 'ทีม')} ตอบรับเคสแล้ว"
        elif act == "claim":
            text = f"{d.get('team', 'ทีม')} รับเคสนี้ — กำลังเตรียมเข้าไป"
        elif act == "decline":
            text = "ทีมที่ได้รับมอบหมายเข้าไม่ได้ — ศูนย์กำลังหาทีมใหม่"
        elif act in ("status", "reopen"):
            text = STATUS_TH.get(d.get("to"), d.get("to"))
        elif act == "close":
            text = "ปิดเคส: " + CLOSE_REASONS.get(d.get("close_reason"), "")
        else:
            continue
        out.append({"ts": a["ts"], "text": text})
    return out


def readiness(c: dict) -> list[dict]:
    """What the rescue team still needs, in the reporter's words. level: need = essential, help = speeds things up.
    state: ok | partial (we have something, not enough to find the house) | missing."""
    prec = (c.get("nav") or {}).get("precision")
    if prec in ("exact", "link") or (prec == "address" and (c.get("house_no") or c.get("landmark"))):
        loc = "ok"
    elif c.get("area") or c.get("street"):
        loc = "partial"
    else:
        loc = "missing"
    people = c.get("adults") is not None or bool(people_total(c))
    st = lambda ok: "ok" if ok else "missing"
    items = [
        ("location", "ตำแหน่งที่ทีมหาบ้านเจอ", "need", loc,
         "กด 📍 ส่งพิกัด หรือบอกบ้านเลขที่ + ซอย + จุดสังเกต (เช่น ตรงข้ามเซเว่น หลังวัด)" if loc == "partial"
         else "ยังไม่รู้ว่าอยู่ที่ไหน — บอกซอย ถนน หมู่บ้าน หรือกด 📍 ส่งพิกัด"),
        ("contact", "เบอร์โทรที่ติดต่อได้", "need", st(c.get("contact")), "เบอร์ที่ทีมโทรกลับได้ (หรือเบอร์ญาติ) และแบตเหลือเท่าไหร่"),
        ("people", "จำนวนคน", "need", st(people), "ผู้ใหญ่กี่คน เด็ก/ผู้สูงอายุ อายุเท่าไหร่ — ใช้เลือกขนาดเรือ"),
        ("water", "ระดับน้ำตอนนี้", "need", st(c.get("water_level")), "เข่า / เอว / อก / มิดชั้น 1 / ถึงชั้น 2 / บนหลังคา"),
        ("vulnerable", "ผู้ป่วยหรือคนที่เคลื่อนย้ายยาก", "help", st(c.get("flags") or c.get("elderly_ages") or c.get("children_ages")
                                                                   or c.get("children_count") or c.get("elderly_count")),
         "ติดเตียง ฟอกไต ตั้งครรภ์ บาดเจ็บ เด็กเล็ก — ถ้าไม่มี ข้ามข้อนี้ได้"),
        ("building", "ที่พักมีกี่ชั้น", "help", st(c.get("building_floors")),
         "บ้านชั้นเดียว / บ้าน 2 ชั้น / ตึก-คอนโด — บ้านชั้นเดียวน้ำถึงเอวอันตรายกว่า เพราะไม่มีชั้นบนให้หนี"),
        ("needs", "สิ่งที่ต้องการ", "help", st(c.get("needs")), "เรืออพยพ / อาหาร / น้ำดื่ม / ยา / นมเด็ก / แบตสำรอง"),
        ("photo", "รูปบ้านหรือระดับน้ำ", "help", st(c.get("photos")), "รูปช่วยให้ทีมเลือกเรือและเส้นทางได้ถูก"),
    ]
    return [{"key": k, "label": l, "level": lv, "state": s, "hint": h} for k, l, lv, s, h in items]


def public_case(conn, c: dict) -> dict:
    ready = readiness(c)
    return {"checklist": ready, "essential_ok": sum(1 for r in ready if r["level"] == "need" and r["state"] == "ok"),
            "essential_total": sum(1 for r in ready if r["level"] == "need"),"id": c["id"], "status": c["status"], "status_th": STATUS_TH.get(c["status"]), "priority": c["priority"],
            "close_reason": c.get("close_reason"), "close_reason_th": CLOSE_REASONS.get(c.get("close_reason")),
            "assigned_team": c["assigned_team"], "area": c["area"], "street": c["street"], "summary": c["summary"],
            "missing_fields": c["missing_fields"], "report_count": c["report_count"], "updated_at": c["updated_at"],
            "created_at": c["created_at"], "timeline": public_timeline(conn, c["id"])}


def track_view(conn, token: str) -> dict | None:
    s = _submission_by_token(conn, token)
    if not s:
        return None
    ids = track_case_ids(conn, token)
    cases = {c["id"]: c for c in list_cases(conn) if c["id"] in ids}
    sids = [s["id"], *_track_followup_sids(conn, token)]
    photos = media.for_submissions(conn, sids)
    mine = [dict(r) for r in conn.execute(
        f"SELECT id, received_at, raw_text FROM submissions WHERE id IN ({','.join('?' * len(sids))}) ORDER BY received_at, rowid", sids)]
    for m in mine:
        m["photos"] = [{**p, "url": p["url"] + f"?track={token}"} for p in photos.get(m["id"], [])]
    return {"received_at": s["received_at"], "channel": s["channel"], "my_reports": mine,
            "cases": [public_case(conn, cases[i]) for i in ids if i in cases]}


def _tracked_case(conn, token: str, case_id: str | None) -> str:
    ids = track_case_ids(conn, token)
    if not ids:
        raise LookupError("ไม่พบลิงก์ติดตามนี้ หรือข้อความนี้ไม่ได้สร้างเคส")
    cid = case_id or ids[0]
    if cid not in ids:
        raise Forbidden("เคสนี้ไม่ได้มาจากรายงานของคุณ")
    return cid


def track_followup(conn, agent, token: str, case_id: str | None, text: str, photos: list[str] | None = None) -> dict:
    """The reporter comes back later (from the private link) with more info for one of THEIR cases."""
    cid = _tracked_case(conn, token, case_id)
    st = conn.execute("SELECT status FROM cases WHERE id=?", (cid,)).fetchone()
    if st and st[0] == "resolved":
        raise ValueError("เคสนี้ปิดแล้ว ถ้ายังต้องการความช่วยเหลือ กรุณาแจ้งเรื่องใหม่ หรือโทร 1784")
    out = add_followup(conn, agent, cid, text, "track_link", photos, source_ref=f"track:{token}", actor="reporter")
    return {**out, "case": public_case(conn, get_case(conn, cid))}


def track_safe(conn, token: str, case_id: str | None = None) -> dict:
    """Reporter presses 'ปลอดภัยแล้ว' -> the case closes as self_safe (staff can reopen)."""
    cid = _tracked_case(conn, token, case_id)
    c = get_case(conn, cid)
    if c["status"] != "resolved":
        update_case(conn, cid, status="resolved", close_reason="self_safe", user="reporter")
    return public_case(conn, get_case(conn, cid))


# ---------------- notes from rescue teams / officers (not read by the AI) ----------------
def add_note(conn, cid: str, user: dict, text: str, photos: list[str] | None = None) -> dict | None:
    if not conn.execute("SELECT 1 FROM cases WHERE id=?", (cid,)).fetchone():
        return None
    decoded = media.validate(photos)
    text = (text or "").strip()
    if not text and not decoded:
        raise ValueError("ใส่ข้อความหรือรูปอย่างน้อย 1 อย่าง")
    ts = now()
    label = f"{user.get('display_name') or user.get('username')}" + (f" ({user['team']})" if user.get("team") else "")
    sid = save_submission(conn, text or "(รูปจากทีม)", "staff_note", ts, author=label, source_ref=f"note:{cid}")
    saved = media.save(conn, sid, decoded, ts) if decoded else []
    mid = "M-" + uuid.uuid4().hex[:8].upper()
    conn.execute("""INSERT INTO messages (id, received_at, channel, text, message_type, case_id, action, extraction, submission_id)
                    VALUES (?,?,?,?,?,?,?,?,?)""", (mid, ts, "staff_note", text or "(รูปจากทีม)", "note", cid, "note", "{}", sid))
    conn.execute("UPDATE cases SET updated_at=? WHERE id=?", (ts, cid))
    auth.audit(conn, user, "note", cid, {"text": text[:200], "photos": len(saved)}, commit=False)
    conn.commit()
    return {"message_id": mid, "case_id": cid, "photos": saved}


# ---------------- officer corrects what the AI read -> labelled data for the next training round ----------------
CORRECTABLE = ("flags", "needs", "water_level", "priority", "adults", "lost_contact")


def merge_into(conn, src: str, target: str, user) -> dict:
    """Officer confirms two cases are the same household: every report of `src` moves to `target`, the information is
    combined (worst condition kept), and `src` is closed as a duplicate. Photos follow their reports."""
    if src == target:
        raise ValueError("รวมเคสเข้ากับตัวเองไม่ได้")
    a, b = get_case(conn, src), get_case(conn, target)
    if not a or not b:
        raise LookupError("case not found")
    if b["status"] == "resolved":
        raise ValueError(f"เคส {target} ปิดแล้ว — เปิดเคสใหม่ก่อน หรือรวมกลับด้านกัน")
    ts = now()
    e = Extraction(message_type="help_request", area=a["area"], street=a["street"], landmark=a["landmark"], house_no=a["house_no"],
                   adults=a["adults"], children_ages=a["children_ages"], elderly_ages=a["elderly_ages"], flags=a["flags"],
                   needs=a["needs"], water_level=a["water_level"], days_trapped=a["days_trapped"], contact=a["contact"],
                   children_count=a.get("children_count"), elderly_count=a.get("elderly_count"), building_floors=a.get("building_floors"))
    n = conn.execute("SELECT COUNT(*) FROM messages WHERE case_id=?", (src,)).fetchone()[0]
    _merge_case(conn, target, e, ts, a["first_text"] or "")
    conn.execute("UPDATE messages SET case_id=? WHERE case_id=?", (target, src))
    conn.execute("UPDATE cases SET report_count=report_count+? WHERE id=?", (max(n - 1, 0), target))
    conn.execute("""UPDATE cases SET status='resolved', close_reason='duplicate', closed_at=?, updated_at=?, possible_dup=NULL,
                    report_count=0 WHERE id=?""", (ts, ts, src))
    conn.execute("UPDATE cases SET possible_dup=NULL WHERE possible_dup=?", (src,))
    auth.audit(conn, user, "merge", target, {"from": src, "reports": n}, commit=False)
    auth.audit(conn, user, "close", src, {"close_reason": "duplicate", "merged_into": target}, commit=False)
    conn.commit()
    return get_case(conn, target)


def not_duplicate(conn, cid: str, user) -> dict | None:
    c = get_case(conn, cid)
    if not c:
        return None
    conn.execute("UPDATE cases SET possible_dup=NULL, possible_dup_score=NULL WHERE id=?", (cid,))
    auth.audit(conn, user, "not_duplicate", cid, {"was": c.get("possible_dup")})
    return get_case(conn, cid)


def correct_ai(conn, cid: str, user: dict, fields: dict) -> dict | None:
    from floodcommon.schemas import Need
    c = get_case(conn, cid)
    if not c:
        return None
    fields = {k: v for k, v in fields.items() if k in CORRECTABLE and v is not None}
    if not fields:
        raise ValueError(f"ไม่มีอะไรให้แก้ (แก้ได้: {', '.join(CORRECTABLE)})")
    flags = fields.get("flags", c["flags"]); needs = fields.get("needs", c["needs"])
    bad = [f for f in flags if f not in {x.value for x in Flag}] + [n for n in needs if n not in {x.value for x in Need}]
    wl = fields.get("water_level", c["water_level"]) or None
    if wl and wl not in {w.value for w in WaterLevel}:
        bad.append(wl)
    if fields.get("priority") and fields["priority"] not in PRIORITIES:
        bad.append(fields["priority"])
    if bad:
        raise ValueError(f"ค่าไม่ถูกต้อง: {bad}")
    texts = [r[0] for r in conn.execute("SELECT text FROM messages WHERE case_id=? AND action IN ('created','merged','followup') "
                                        "ORDER BY received_at, rowid", (cid,))]
    before = {k: c.get(k) for k in CORRECTABLE if k != "lost_contact"}
    e = Extraction(message_type="help_request", area=c["area"], street=c["street"], house_no=c["house_no"],
                   adults=fields.get("adults", c["adults"]), children_ages=c["children_ages"], elderly_ages=c["elderly_ages"],
                   children_count=c.get("children_count"), elderly_count=c.get("elderly_count"), building_floors=c.get("building_floors"),
                   flags=flags, needs=needs, water_level=wl, days_trapped=c["days_trapped"], contact=c["contact"],
                   lost_contact=bool(fields.get("lost_contact")))
    if fields.get("priority"):
        color, reason, lock = fields["priority"], "เจ้าหน้าที่แก้ผล AI", 1
    elif c["priority_locked"]:
        color, reason, lock = c["priority"], c["priority_reason"], 1
    else:
        color, reason = priority(e); lock = 0
    conn.execute("""UPDATE cases SET flags=?, needs=?, water_level=?, adults=?, priority=?, priority_reason=?, priority_locked=?,
                    missing_fields=?, updated_at=? WHERE id=?""",
                 (json.dumps(sorted(set(flags))), json.dumps(sorted(set(needs))), wl, e.adults, color, reason, lock,
                  json.dumps(missing_fields(e, c["geo_precision"] in ("exact", "link") or bool(c["map_url"]))), now(), cid))
    after = {"flags": sorted(set(flags)), "needs": sorted(set(needs)), "water_level": wl, "priority": color, "adults": e.adults,
             "lost_contact": e.lost_contact}
    conn.execute("INSERT INTO corrections VALUES (?,?,?,?,?,?,?)", ("K-" + uuid.uuid4().hex[:8].upper(), now(), cid,
                 user.get("username"), json.dumps(texts, ensure_ascii=False), json.dumps(before, ensure_ascii=False),
                 json.dumps(after, ensure_ascii=False)))
    auth.audit(conn, user, "correct_ai", cid, {"before": before, "after": after}, commit=False)
    conn.commit()
    return get_case(conn, cid)


def export_corrections(conn) -> list[dict]:
    """One training row per corrected case (latest correction wins), in the same shape as realdata/labels*.jsonl."""
    latest = {}
    for r in conn.execute("SELECT * FROM corrections ORDER BY created_at, rowid"):
        latest[r["case_id"]] = r
    out = []
    for cid, r in latest.items():
        a, texts = json.loads(r["after"]), json.loads(r["texts"])
        if not texts:
            continue
        out.append({"id": f"officer-{cid}", "text": "\n".join(texts), "message_type": "help_request", "flags": a["flags"],
                    "needs": a["needs"], "water_level": a["water_level"], "lost_contact": a.get("lost_contact", False),
                    "priority": a["priority"], "source": "officer_correction", "human_reviewed": True,
                    "reviewed_by": r["actor"], "reviewed_at": r["created_at"]})
    return out


# ---------------- every report received -> data for the next training round ----------------
def export_training(conn, mask_pii: bool = True, include_demo: bool = False) -> list[dict]:
    """One row per message the AI read (help requests AND other messages, so the type classifier learns both), in the
    realdata/labels*.jsonl shape. Labels = what the AI said (human_reviewed False), or the officer's correction when the
    case was corrected (human_reviewed True). Personal data (phones, house no., GPS, links, names) is masked by default.
    Rescue-team notes and demo data are left out."""
    from floodcommon.pii import mask
    corrected = {}
    for r in conn.execute("SELECT * FROM corrections ORDER BY created_at, rowid"):
        corrected[r["case_id"]] = r
    feedback = {}
    for r in conn.execute("SELECT message_id, case_id, note FROM ai_feedback"):
        feedback.setdefault(r["message_id"] or r["case_id"], []).append(r["note"])
    cases = {c["id"]: c for c in list_cases(conn)}
    opted_out = {r[0]: True for r in conn.execute("""SELECT DISTINCT m.case_id FROM messages m JOIN submissions s ON s.id = m.submission_id
                                                     WHERE s.no_training = 1 AND m.case_id IS NOT NULL""")}
    q = """SELECT m.id, m.received_at, m.channel, m.text, m.message_type, m.case_id, m.action, m.extraction, m.provider, m.confidence,
                  m.escalated, s.source_ref, s.no_training FROM messages m LEFT JOIN submissions s ON s.id = m.submission_id
           WHERE m.action <> 'note' AND m.channel <> 'staff_note' ORDER BY m.received_at, m.rowid"""
    out = []
    for r in conn.execute(q):
        if not include_demo and (r["source_ref"] or "") == DEMO_REF:
            continue
        if r["no_training"] or opted_out.get(r["case_id"]):      # the reporter said no (PDPA) — never exported
            continue
        ex = json.loads(r["extraction"] or "{}")
        c = cases.get(r["case_id"]) or {}
        row = {"id": r["id"], "text": mask(r["text"])[0] if mask_pii else r["text"], "message_type": ex.get("message_type") or r["message_type"],
               "flags": ex.get("flags") or [], "needs": ex.get("needs") or [], "water_level": ex.get("water_level"),
               "lost_contact": bool(ex.get("lost_contact")), "priority": c.get("priority"), "human_reviewed": False,
               "label_source": f"ai:{r['provider'] or '?'}" + (" (escalated)" if r["escalated"] else ""),
               "ai_confidence": r["confidence"], "case_id": r["case_id"], "action": r["action"], "channel": r["channel"],
               "received_at": r["received_at"], "pii_masked": mask_pii}
        k = corrected.get(r["case_id"])
        if k and r["action"] in ("created", "merged", "followup"):
            a = json.loads(k["after"])
            row.update(flags=a["flags"], needs=a["needs"], water_level=a["water_level"], priority=a["priority"],
                       lost_contact=a.get("lost_contact", row["lost_contact"]), human_reviewed=True, label_source=f"officer:{k['actor']}")
        notes = feedback.get(r["id"]) or (feedback.get(r["case_id"]) if r["action"] == "created" else None)
        if notes:
            row["ai_feedback"] = notes                     # "the AI read this wrongly" — review these first
        out.append(row)
    return out


def training_stats(conn) -> dict:
    rows = export_training(conn, mask_pii=False)
    return {"rows": len(rows), "help_requests": sum(1 for r in rows if r["message_type"] == "help_request"),
            "human_reviewed": sum(1 for r in rows if r["human_reviewed"]), "with_ai_feedback": sum(1 for r in rows if r.get("ai_feedback")),
            "escalated_to_llm": sum(1 for r in rows if "escalated" in r["label_source"])}


# ---------------- public page: numbers + rough map, no personal data ----------------
def public_summary(conn) -> dict:
    cases = list_cases(conn)
    open_ = [c for c in cases if c["status"] in OPEN]
    areas: dict[str, dict] = {}
    for c in open_:
        a = areas.setdefault(c["area"] or "ไม่ระบุพื้นที่", {"area": c["area"] or "ไม่ระบุพื้นที่", "open": 0, "red": 0, "orange": 0,
                                                        "yellow": 0, "green": 0, "needs": {}})
        a["open"] += 1; a[c["priority"]] = a.get(c["priority"], 0) + 1
        for n in c["needs"]:
            a["needs"][n] = a["needs"].get(n, 0) + 1
    # points rounded to 2 decimals (~1 km) so no house can be found from the public map
    pts: dict[tuple, dict] = {}
    for c in open_:
        if c["lat"] is None:
            continue
        k = (round(c["lat"], 2), round(c["lng"], 2))
        p = pts.setdefault(k, {"lat": k[0], "lng": k[1], "count": 0, "worst": "green"})
        p["count"] += 1
        if PRIORITY_RANK.get(c["priority"], 9) < PRIORITY_RANK.get(p["worst"], 9):
            p["worst"] = c["priority"]
    closed = [c for c in cases if c["status"] == "resolved"]
    return {"updated_at": now(), "open_cases": len(open_), "resolved_cases": len(closed),
            "open_by_priority": {k: sum(1 for c in open_ if c["priority"] == k) for k in PRIORITIES},
            "by_status": {k: sum(1 for c in cases if c["status"] == k) for k in STATUSES},
            "closed_by_reason": {k: sum(1 for c in closed if c.get("close_reason") == k) for k in CLOSE_REASONS},
            "areas": sorted(areas.values(), key=lambda a: (-a["red"], -a["open"])), "points": list(pts.values()),
            "hazards": conn.execute("SELECT COUNT(*) FROM hazards").fetchone()[0]}


def stats(conn) -> dict:
    cases = list_cases(conn)
    open_ = [c for c in cases if c["status"] in OPEN]
    by = lambda key, rows: {k: sum(1 for c in rows if c[key] == k) for k in sorted({c[key] for c in rows if c[key]})}
    return {
        "total_cases": len(cases), "open_cases": len(open_),
        "open_by_priority": by("priority", open_), "by_status": by("status", cases),
        "unassigned_red": sum(1 for c in open_ if c["priority"] == "red" and not c["assigned_team"]),
        "messages": conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
        "duplicates_merged": conn.execute("SELECT COUNT(*) FROM messages WHERE action='merged'").fetchone()[0],
        "hazards": conn.execute("SELECT COUNT(*) FROM hazards").fetchone()[0],
        "ai": _ai_stats(conn),
    }


def _ai_stats(conn) -> dict:
    """Who handled the messages: our own model vs escalated to the LLM."""
    n, esc, own, avg = conn.execute(
        "SELECT COUNT(*), SUM(escalated), SUM(provider LIKE 'own_model%'), AVG(latency_ms) FROM messages").fetchone()
    return {"handled_by_own_model": own or 0, "escalated_to_llm": esc or 0,
            "own_model_share": round((own or 0) / n, 3) if n else None, "avg_latency_ms": round(avg) if avg else None}


def process_batch(conn, agent, text: str, channel: str = "web_form", ts: str | None = None, author: str | None = None,
                  source_ref: str | None = None, source_url: str | None = None, photos: list[str] | None = None,
                  no_training: bool = False) -> dict:
    """One submitted text may contain several cases -> the agent splits it, each part is processed on its own.
    The full original text is stored once in `submissions`; every case made from it links back to it.
    Photos (validated first: media.PhotoError on a bad one) are stored once and shown on every case of the submission."""
    decoded = media.validate(photos)
    ts = clock.normalize(ts) or now()
    split = agent.split(text) if hasattr(agent, "split") else {"segments": [text], "method": "none"}
    segs = split.get("segments") or [text]
    batch_id = "B-" + uuid.uuid4().hex[:8].upper() if len(segs) > 1 else None
    sid = save_submission(conn, text, channel, ts, len(segs), author, source_ref, source_url)
    if no_training:
        conn.execute("UPDATE submissions SET no_training=1 WHERE id=?", (sid,))
    saved = media.save(conn, sid, decoded, ts) if decoded else []
    results = [process_message(conn, agent, s, channel, ts, batch_id, sid) for s in segs]
    first = results[0] if results else {}
    token = conn.execute("SELECT track_token FROM submissions WHERE id=?", (sid,)).fetchone()[0]
    return {**first, "batch_id": batch_id, "n_cases": len(results), "split_method": split.get("method"),
            "split_note": split.get("note"), "results": results, "photos": saved,
            "track_token": token, "track_path": f"/track/{token}"}


def case_messages(conn, cid: str) -> list[dict]:
    """Every report linked to a case: the part the AI read, what it extracted, and the full original submission."""
    out = []
    for r in conn.execute("""SELECT m.id, m.received_at, m.channel, m.text, m.action, m.message_type, m.extraction, m.provider,
                                    m.escalated, m.confidence, m.submission_id, s.raw_text, s.n_cases, s.author, s.source_url
                             FROM messages m LEFT JOIN submissions s ON s.id = m.submission_id
                             WHERE m.case_id=? ORDER BY m.received_at, m.rowid""", (cid,)):
        d = dict(r)
        d["extraction"] = json.loads(d["extraction"] or "{}")
        d["raw_text"] = d["raw_text"] or d["text"]                # rows from before v0.8 have no submission
        d["was_split"] = (d["n_cases"] or 1) > 1 and d["raw_text"] != d["text"]
        d["escalated"] = bool(d["escalated"])
        out.append(d)
    photos = media.for_submissions(conn, [d["submission_id"] for d in out])
    for d in out:
        d["photos"] = photos.get(d["submission_id"], [])
    return out


def add_feedback(conn, cid: str, message_id: str | None, note: str, reporter: str | None = None) -> dict:
    """A rescuer says the AI read a message wrongly -> stored with the text + extraction, exportable as training/eval data."""
    row = conn.execute("SELECT text, extraction FROM messages WHERE id=? OR (? IS NULL AND case_id=?) ORDER BY rowid LIMIT 1",
                       (message_id, message_id, cid)).fetchone()
    fid = "F-" + uuid.uuid4().hex[:6].upper()
    conn.execute("INSERT INTO ai_feedback VALUES (?,?,?,?,?,?,?,?)", (fid, now(), cid, message_id, row["text"] if row else None,
                                                                        row["extraction"] if row else None, note, reporter))
    conn.commit()
    return {"id": fid, "case_id": cid, "message_id": message_id, "note": note}


# ---------------- demo data / reset ----------------
DEMO_REF = "demo"
DATA_TABLES = ("cases", "messages", "hazards", "submissions", "ai_feedback", "attachments", "corrections")


def seed_demo(conn, agent, rows: list[dict]) -> dict:
    """Load demo messages, marked source_ref='demo' so they can be removed later without touching real reports.
    Old demo data is removed first; real cases stay."""
    removed = delete_demo(conn, [r["text"] for r in rows])
    for r in rows:
        sid = save_submission(conn, r["text"], r["channel"], clock.normalize(r["timestamp"]) or now(), source_ref=DEMO_REF)
        process_message(conn, agent, r["text"], r["channel"], r["timestamp"], submission_id=sid)
    return {"processed": len(rows), "removed_old_demo": removed["cases"]}


def delete_demo(conn, demo_texts: list[str] | None = None) -> dict:
    """Remove demo reports and the cases made ONLY from them. A demo case that a real report was merged into is kept.
    demo_texts also catches demo rows loaded by versions before this marker existed (same text as the demo dataset)."""
    media.init(conn)
    texts = list(set(demo_texts or []))
    q = "SELECT id FROM submissions WHERE source_ref=?" + (f" OR raw_text IN ({','.join('?' * len(texts))})" if texts else "")
    sids = {r[0] for r in conn.execute(q, [DEMO_REF, *texts])}
    q = "SELECT id FROM messages WHERE submission_id IN ({0})".format(",".join("?" * len(sids))) if sids else None
    mids = {r[0] for r in conn.execute(q, list(sids))} if q else set()
    if texts:                                        # pre-v0.8 messages without a submission row
        mids |= {r[0] for r in conn.execute(f"SELECT id FROM messages WHERE submission_id IS NULL AND text IN ({','.join('?' * len(texts))})", texts)}
    if not mids and not sids:
        return {"cases": 0, "messages": 0}
    ph = lambda xs: ",".join("?" * len(xs))
    case_ids = {r[0] for r in conn.execute(f"SELECT DISTINCT case_id FROM messages WHERE id IN ({ph(mids)}) AND case_id IS NOT NULL", list(mids))} if mids else set()
    keep = {r[0] for r in conn.execute(f"SELECT DISTINCT case_id FROM messages WHERE case_id IN ({ph(case_ids)}) AND id NOT IN ({ph(mids)})",
                                       [*case_ids, *mids])} if case_ids else set()
    drop = case_ids - keep
    hazard_texts = [r[0] for r in conn.execute(f"SELECT text FROM messages WHERE id IN ({ph(mids)}) AND action='hazard'", list(mids))] if mids else []
    for pid, path in conn.execute(f"SELECT id, path FROM attachments WHERE submission_id IN ({ph(sids)})", list(sids)).fetchall() if sids else []:
        (media.media_dir() / path).unlink(missing_ok=True)
    if sids:
        conn.execute(f"DELETE FROM attachments WHERE submission_id IN ({ph(sids)})", list(sids))
        conn.execute(f"DELETE FROM submissions WHERE id IN ({ph(sids)})", list(sids))
    if mids:
        conn.execute(f"DELETE FROM messages WHERE id IN ({ph(mids)})", list(mids))
    if drop:
        conn.execute(f"DELETE FROM ai_feedback WHERE case_id IN ({ph(drop)})", list(drop))
        conn.execute(f"DELETE FROM corrections WHERE case_id IN ({ph(drop)})", list(drop))
        conn.execute(f"DELETE FROM audit_log WHERE case_id IN ({ph(drop)})", list(drop))
        conn.execute(f"DELETE FROM cases WHERE id IN ({ph(drop)})", list(drop))
    if hazard_texts:
        conn.execute(f"DELETE FROM hazards WHERE text IN ({ph(hazard_texts)})", hazard_texts)
    conn.commit()
    return {"cases": len(drop), "messages": len(mids), "kept_cases_with_real_reports": len(keep)}


def reset_all(conn) -> dict:
    """Delete EVERYTHING (all cases, messages, photos). Places and the knowledge base are not touched."""
    media.init(conn)
    n = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
    for (path,) in conn.execute("SELECT path FROM attachments").fetchall():
        (media.media_dir() / path).unlink(missing_ok=True)
    conn.executescript("".join(f"DELETE FROM {t};" for t in DATA_TABLES))
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='chat_sessions'").fetchone():
        conn.execute("DELETE FROM chat_sessions")
    conn.commit()
    return {"cases": n}


def add_followup(conn, agent, cid: str, text: str, channel: str = "web_form", photos: list[str] | None = None,
                 ts: str | None = None, source_ref: str | None = None, actor: dict | str | None = "reporter") -> dict | None:
    """The reporter (or an officer after a call-back) sends MORE information for a case that already exists:
    a clearer location, the water level, a phone number, photos. It is merged into THAT case directly
    (no duplicate search, no splitting) and the reply says what is still missing."""
    row = conn.execute("SELECT * FROM cases WHERE id=?", (cid,)).fetchone()
    if not row:
        return None
    decoded = media.validate(photos)
    text = (text or "").strip()
    if not text and not decoded:
        raise ValueError("ใส่ข้อความหรือรูปอย่างน้อย 1 อย่าง")
    ts = ts or now()
    sid = save_submission(conn, text or "(ส่งรูปเพิ่ม)", channel, ts, source_ref=source_ref or f"followup:{cid}")
    saved = media.save(conn, sid, decoded, ts) if decoded else []
    meta, e = {}, None
    if text:
        try:
            e = agent.run(text, force_help=True)
        except TypeError:                                   # an agent without follow-up support
            e = agent.run(text)
        meta = getattr(agent, "last", None) or {}
        e = e if e.message_type == MessageType.help_request else Extraction(**{**e.model_dump(), "message_type": "help_request"})
        _merge_case(conn, cid, e, ts, text)
    else:
        conn.execute("UPDATE cases SET updated_at=?, report_count=report_count+1 WHERE id=?", (ts, cid))
    mid = "M-" + uuid.uuid4().hex[:8].upper()
    conn.execute("""INSERT INTO messages (id, received_at, channel, text, message_type, case_id, action, extraction,
                    provider, escalated, confidence, latency_ms, batch_id, submission_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (mid, ts, channel, text or "(ส่งรูปเพิ่ม)", "help_request", cid, "followup", e.model_dump_json() if e else "{}",
                  meta.get("provider_used"), int(bool(meta.get("escalated"))), meta.get("confidence"), meta.get("latency_ms"), None, sid))
    auth.audit(conn, actor, "followup", cid, {"submission": sid, "photos": len(saved), "has_text": bool(text)}, commit=False)
    conn.commit()
    case = next(c for c in list_cases(conn) if c["id"] == cid)
    missing = case["missing_fields"]
    return {"message_id": mid, "case_id": cid, "action": "followup", "case": case, "missing_fields": missing,
            "followup": followup_message(missing), "photos": saved,
            "extraction": json.loads(e.model_dump_json()) if e else None, **meta}

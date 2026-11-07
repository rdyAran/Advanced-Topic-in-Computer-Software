"""Field teams (ชุดปฏิบัติการ) — one login per team: the TEAM LEAD (role 'rescuer'), who coordinates their own crew.

  * the coordination centre (officer) creates the team + its lead account, and can reset / disable it
  * a team keeps a small profile the centre uses to pick who to send: status, last GPS, boats, seats, medic, phone
  * dispatch, two ways:
      push  - officer assigns -> the team ACCEPTS or DECLINES with a reason (declined -> back to the queue)
      pull  - the team sees open UNASSIGNED cases near it (no phone / house no. / message text) and CLAIMS one;
              first claim wins (atomic UPDATE), full details are shown only after that
  * an assignment nobody answered for ACCEPT_MINUTES shows up as late on the centre's screen
"""
import math, os
from . import auth, service
from .db import ensure

ACCEPT_MINUTES = int(os.getenv("ACCEPT_MINUTES", "10"))
STATUSES = {"available": "ว่าง พร้อมรับงาน", "busy": "กำลังช่วยเหลือ", "offline": "พัก / ออฟไลน์"}
KINDS = {"gov": "หน่วยงานรัฐ", "volunteer": "อาสา / มูลนิธิ"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
  name TEXT PRIMARY KEY, org TEXT, kind TEXT, status TEXT DEFAULT 'available', lat REAL, lng REAL, located_at TEXT,
  boats INTEGER, seats INTEGER, has_medic INTEGER DEFAULT 0, phone TEXT, note TEXT, updated_at TEXT
);
"""
PROFILE = ("org", "kind", "status", "boats", "seats", "has_medic", "phone", "note")


def init(conn):
    ensure(conn, "teams", SCHEMA)


def _row(conn, name: str) -> dict:
    init(conn)
    r = conn.execute("SELECT * FROM teams WHERE name=?", (name,)).fetchone()
    if r:
        d = dict(r)
    else:
        d = {"name": name, "org": None, "kind": None, "status": "available", "lat": None, "lng": None, "located_at": None,
             "boats": None, "seats": None, "has_medic": 0, "phone": None, "note": None, "updated_at": None}
    d["has_medic"] = bool(d["has_medic"])
    d["status_th"] = STATUSES.get(d["status"], d["status"])
    d["kind_th"] = KINDS.get(d["kind"])
    return d


def update_profile(conn, name: str, fields: dict, user=None) -> dict:
    init(conn)
    f = {k: v for k, v in fields.items() if k in PROFILE}
    if "status" in f and f["status"] not in STATUSES:
        raise ValueError(f"status ต้องเป็นหนึ่งใน {list(STATUSES)}")
    if "kind" in f and f["kind"] not in KINDS:
        raise ValueError(f"kind ต้องเป็นหนึ่งใน {list(KINDS)}")
    for k in ("boats", "seats"):
        if f.get(k) is not None and not (0 <= int(f[k]) <= 500):
            raise ValueError(f"{k} ต้องอยู่ระหว่าง 0–500")
    if "has_medic" in f:
        f["has_medic"] = int(bool(f["has_medic"]))
    loc = {}
    if fields.get("lat") is not None and fields.get("lng") is not None:
        lat, lng = float(fields["lat"]), float(fields["lng"])
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise ValueError("พิกัดไม่ถูกต้อง")
        loc = {"lat": lat, "lng": lng, "located_at": service.now()}
    data = {**f, **loc, "updated_at": service.now()}
    conn.execute("INSERT OR IGNORE INTO teams (name) VALUES (?)", (name,))
    conn.execute(f"UPDATE teams SET {', '.join(k + '=?' for k in data)} WHERE name=?", [*data.values(), name])
    auth.audit(conn, user, "team_update", detail={"team": name, **{k: v for k, v in data.items() if k not in ("lat", "lng")}}, commit=False)
    conn.commit()
    return _row(conn, name)


# ---------------- team-lead accounts (managed by the centre) ----------------
def create_team(conn, by: dict, username: str, password: str, team: str, display_name: str = "", **profile) -> dict:
    team = (team or "").strip()
    if not team:
        raise auth.AuthError("ต้องระบุชื่อชุด")
    if team in auth.teams(conn):
        raise auth.AuthError("มีชุดชื่อนี้แล้ว (1 ชุดมีบัญชีหัวหน้าชุด 1 บัญชี)")
    u = auth.create_user(conn, username, password, "rescuer", display_name or f"หัวหน้า{team}", team)
    update_profile(conn, team, {k: v for k, v in profile.items() if v is not None}, by)
    auth.audit(conn, by, "user_create", detail={"username": u["username"], "role": "rescuer", "team": team})
    return u


def lead_accounts(conn) -> list[dict]:
    return [u for u in auth.list_users(conn) if u["role"] == "rescuer"]


def check_lead_account(conn, uid: str) -> dict:
    """Officers may manage team-lead accounts only (never other officers or admins)."""
    u = auth.get_user(conn, uid)
    if not u or u["role"] != "rescuer":
        raise LookupError("ไม่พบบัญชีหัวหน้าชุดนี้")
    return u


# ---------------- the centre's team board ----------------
def board(conn) -> list[dict]:
    cases = service.list_cases(conn, "open")
    leads = {u["team"]: u for u in lead_accounts(conn)}
    names = sorted(set(leads) | {c["assigned_team"] for c in cases if c["assigned_team"]})
    out = []
    for n in names:
        mine = [c for c in cases if c["assigned_team"] == n]
        lead = leads.get(n)
        out.append({**_row(conn, n), "lead": {k: lead[k] for k in ("id", "username", "display_name", "active", "last_login")} if lead else None,
                    "open_cases": len(mine), "pending": sum(1 for c in mine if c.get("assign_state") == "pending"),
                    "red_cases": sum(1 for c in mine if c["priority"] == "red"), "case_ids": [c["id"] for c in mine]})
    order = {"available": 0, "busy": 1, "offline": 2}
    return sorted(out, key=lambda t: (not (t["lead"] and t["lead"]["active"]), order.get(t["status"], 3), t["open_cases"], t["name"]))


def km(a_lat, a_lng, b_lat, b_lng) -> float | None:
    if None in (a_lat, a_lng, b_lat, b_lng):
        return None
    p = math.pi / 180
    h = math.sin((b_lat - a_lat) * p / 2) ** 2 + math.cos(a_lat * p) * math.cos(b_lat * p) * math.sin((b_lng - a_lng) * p / 2) ** 2
    return round(12742 * math.asin(math.sqrt(h)), 1)


def suggest_teams(conn, case: dict, top: int = 3) -> list[dict]:
    """Rank active teams for a case: available first, then distance, then fewer open cases. Medic preferred for medical flags."""
    medical = bool(set(case.get("flags") or []) & {"bedridden", "dialysis", "heart", "in_labor", "sick_now", "injured"})
    cand = []
    for t in board(conn):
        if not (t["lead"] and t["lead"]["active"]) or t["status"] == "offline":
            continue
        d = km(t["lat"], t["lng"], case.get("lat"), case.get("lng"))
        score = (0 if t["status"] == "available" else 1, 0 if (t["has_medic"] or not medical) else 1, d if d is not None else 99, t["open_cases"])
        cand.append((score, {"team": t["name"], "status": t["status"], "km": d, "open_cases": t["open_cases"], "has_medic": t["has_medic"]}))
    return [c for _, c in sorted(cand, key=lambda x: x[0])[:top]]


# ---------------- dispatch: accept / decline / claim ----------------
def _own(conn, user, cid):
    c = service.get_case(conn, cid)
    if not c:
        raise LookupError("case not found")
    if c["assigned_team"] != user.get("team"):
        raise service.Forbidden("เคสนี้ไม่ได้มอบหมายให้ชุดของคุณ")
    return c


def accept(conn, user: dict, cid: str) -> dict:
    c = _own(conn, user, cid)
    if c["status"] == "resolved":
        raise ValueError("เคสนี้ปิดแล้ว")
    if c.get("assign_state") != "accepted":
        conn.execute("UPDATE cases SET assign_state='accepted', accepted_at=?, updated_at=? WHERE id=?", (service.now(), service.now(), cid))
        auth.audit(conn, user, "accept", cid, {"team": user["team"]}, commit=False)
        conn.commit()
    return service.get_case(conn, cid)


def decline(conn, user: dict, cid: str, reason: str) -> dict:
    """The team cannot take it (boat cannot get in, too far, full) -> unassigned, back to the centre's queue."""
    c = _own(conn, user, cid)
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("กรุณาบอกเหตุผล เช่น เรือเข้าไม่ได้ น้ำเชี่ยว ชุดเต็ม")
    if c["status"] == "resolved":
        raise ValueError("เคสนี้ปิดแล้ว")
    back = "verified" if c["status"] in ("assigned", "in_progress") else c["status"]
    conn.execute("""UPDATE cases SET assigned_team=NULL, assign_state=NULL, assigned_at=NULL, accepted_at=NULL, status=?, updated_at=?
                    WHERE id=?""", (back, service.now(), cid))
    auth.audit(conn, user, "decline", cid, {"team": user["team"], "reason": reason[:300]}, commit=False)
    conn.commit()
    return service.get_case(conn, cid)


def nearby(conn, user: dict, lat: float | None = None, lng: float | None = None, limit: int = 30) -> list[dict]:
    """Open cases with NO team yet, for a team to claim. Only what is needed to decide: no phone, house no., text or photos."""
    t = _row(conn, user["team"])
    lat = lat if lat is not None else t["lat"]
    lng = lng if lng is not None else t["lng"]
    rank = {"red": 0, "orange": 1, "yellow": 2, "green": 3}
    out = []
    for c in service.list_cases(conn, "open"):
        if c["assigned_team"]:
            continue
        n = c.get("people_total")
        out.append({"id": c["id"], "priority": c["priority"], "status": c["status"], "area": c["area"], "street": c["street"],
                    "km": km(lat, lng, c["lat"], c["lng"]), "people": n or None, "flags": c["flags"], "needs": c["needs"],
                    "water_level": c["water_level"], "created_at": c["created_at"], "geo_precision": c["geo_precision"]})
    out.sort(key=lambda c: (rank.get(c["priority"], 9), c["km"] if c["km"] is not None else 99, c["created_at"]))
    return out[:limit]


def claim(conn, user: dict, cid: str) -> dict:
    """First team to claim gets it (the UPDATE only succeeds while assigned_team is still empty)."""
    ts = service.now()
    cur = conn.execute("""UPDATE cases SET assigned_team=?, assign_state='accepted', assigned_at=?, accepted_at=?, updated_at=?,
                          status=CASE WHEN status IN ('new','verified') THEN 'assigned' ELSE status END
                          WHERE id=? AND assigned_team IS NULL AND status<>'resolved'""", (user["team"], ts, ts, ts, cid))
    if cur.rowcount != 1:
        conn.commit()
        if not service.get_case(conn, cid):
            raise LookupError("case not found")
        raise ValueError("มีชุดอื่นรับเคสนี้ไปแล้ว หรือเคสปิดแล้ว")
    auth.audit(conn, user, "claim", cid, {"team": user["team"]}, commit=False)
    conn.commit()
    return service.get_case(conn, cid)


def late(conn) -> list[dict]:
    """Assignments a team has not answered for ACCEPT_MINUTES — shown to the centre."""
    return [{"id": c["id"], "team": c["assigned_team"], "minutes": c["waiting_accept_min"], "priority": c["priority"]}
            for c in service.list_cases(conn, "open") if (c["waiting_accept_min"] or 0) >= ACCEPT_MINUTES]


# ---------------- demo scenario (admin "โหลดข้อมูลเดโม") ----------------
DEMO_TEAMS = {"ทีมเรือ 1": {"lat": 7.0086, "lng": 100.4747, "boats": 2, "seats": 12, "has_medic": True, "org": "มูลนิธิ (เดโม)",
                            "kind": "volunteer", "phone": "080-000-0001", "status": "available"},
              "ทีมเรือ 2": {"lat": 7.0301, "lng": 100.4862, "boats": 1, "seats": 6, "has_medic": False, "org": "เทศบาล (เดโม)",
                            "kind": "gov", "phone": "080-000-0002", "status": "available"}}


def demo_scenario(conn, user=None) -> dict:
    """Make the demo look like a running operation: teams with a location, one case in progress, one waiting for
    the team to accept, two checked by the centre, the rest new. Touches DEMO cases only."""
    for name, prof in DEMO_TEAMS.items():
        if name in auth.teams(conn) and _row(conn, name)["lat"] is None:
            update_profile(conn, name, prof, "demo")
    demo_ids = {r[0] for r in conn.execute("""SELECT DISTINCT m.case_id FROM messages m JOIN submissions s ON s.id = m.submission_id
                                              WHERE s.source_ref = ? AND m.case_id IS NOT NULL""", (service.DEMO_REF,))}
    cases = [c for c in service.list_cases(conn, "open") if c["id"] in demo_ids and c["status"] == "new"]
    teams_ok = [n for n in DEMO_TEAMS if n in auth.teams(conn)]
    done = {"in_progress": None, "pending": None, "verified": []}
    if len(teams_ok) >= 1 and cases:
        c = cases.pop(0)
        service.update_case(conn, c["id"], assigned_team=teams_ok[0], user=user or "demo")
        service.update_case(conn, c["id"], status="in_progress", user=teams_ok[0])
        done["in_progress"] = c["id"]
    if len(teams_ok) >= 2 and cases:
        c = cases.pop(0)
        service.update_case(conn, c["id"], assigned_team=teams_ok[1], user=user or "demo")
        done["pending"] = c["id"]
    for c in cases[:2]:
        service.update_case(conn, c["id"], status="verified", user=user or "demo")
        done["verified"].append(c["id"])
    return done

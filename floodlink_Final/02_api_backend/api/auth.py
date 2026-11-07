"""Accounts, roles, sessions and the audit log (Python stdlib only, so it is testable without FastAPI).

Roles (higher includes lower):
  rescuer      1  ทีมกู้ภัย/อาสา — sees ONLY the cases assigned to its team, updates their status, adds notes/photos
  coordinator  2  เจ้าหน้าที่ศูนย์ประสาน — the whole queue, corrects the AI, assigns teams, closes cases
  admin        3  ผู้ดูแลระบบ — + accounts, demo/reset, exports, audit log
Reporters never log in: each report gets a private tracking link (submissions.track_token, see service.py).

Passwords: PBKDF2-SHA256 (200k rounds, random salt).  Sessions: an HMAC-signed token in an HttpOnly cookie
(also accepted as "Authorization: Bearer ..."). Changing a password / role / disabling an account bumps
token_version, which logs that user out everywhere.
"""
import base64, hashlib, hmac, json, logging, os, re, secrets, threading, time, uuid, datetime as dt
from .db import ensure

log = logging.getLogger(__name__)
ROLES = {"rescuer": 1, "coordinator": 2, "admin": 3}
ROLE_TH = {"rescuer": "หัวหน้าชุด (ทีมกู้ภัย/อาสา/หน่วยงาน)", "coordinator": "เจ้าหน้าที่ศูนย์ประสาน", "admin": "ผู้ดูแลระบบ"}
COOKIE = "fl_session"
SESSION_HOURS = int(os.getenv("SESSION_HOURS", "12"))
USER_RX = re.compile(r"^[a-z0-9_.-]{3,32}$")
MAX_FAILS, LOCK_SECONDS = 5, 300

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, username TEXT UNIQUE, display_name TEXT, role TEXT, team TEXT,
  pw_hash TEXT, active INTEGER DEFAULT 1, token_version INTEGER DEFAULT 0, created_at TEXT, last_login TEXT
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT, role TEXT, action TEXT, case_id TEXT, detail TEXT
);
CREATE INDEX IF NOT EXISTS ix_audit_case ON audit_log(case_id);
"""


class AuthError(ValueError):
    pass


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def init(conn):
    ensure(conn, "auth", SCHEMA)


# ---------------- passwords ----------------
def hash_password(pw: str, salt: bytes | None = None, rounds: int = 200_000) -> str:
    salt = salt or secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, rounds)
    return f"pbkdf2${rounds}${salt.hex()}${h.hex()}"


def check_password(pw: str, stored: str | None) -> bool:
    try:
        _, rounds, salt, h = (stored or "").split("$")
        got = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(got.hex(), h)
    except (ValueError, TypeError):
        return False


# ---------------- tokens ----------------
def _secret(conn) -> bytes:
    if os.getenv("AUTH_SECRET"):
        return os.getenv("AUTH_SECRET").encode()
    init(conn)
    r = conn.execute("SELECT value FROM settings WHERE key='auth_secret'").fetchone()
    if not r:                                    # generated once, kept in the DB so restarts keep people logged in
        conn.execute("INSERT OR IGNORE INTO settings VALUES ('auth_secret', ?)", (secrets.token_hex(32),)); conn.commit()
        r = conn.execute("SELECT value FROM settings WHERE key='auth_secret'").fetchone()
    return r[0].encode()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(conn, user: dict, hours: int = SESSION_HOURS) -> str:
    body = _b64(json.dumps({"u": user["id"], "v": user["token_version"], "exp": int(time.time()) + hours * 3600}).encode())
    sig = _b64(hmac.new(_secret(conn), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_token(conn, token: str | None) -> dict | None:
    """-> the user (public fields) if the token is valid, not expired, and the account is active."""
    try:
        body, sig = (token or "").split(".")
        if not hmac.compare_digest(_b64(hmac.new(_secret(conn), body.encode(), hashlib.sha256).digest()), sig):
            return None
        p = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if p.get("exp", 0) < time.time():
        return None
    init(conn)
    r = conn.execute("SELECT * FROM users WHERE id=?", (p.get("u"),)).fetchone()
    if not r or not r["active"] or r["token_version"] != p.get("v"):
        return None
    return public_user(r)


def public_user(r) -> dict:
    d = dict(r)
    return {k: d.get(k) for k in ("id", "username", "display_name", "role", "team", "active", "created_at", "last_login")} | \
           {"role_th": ROLE_TH.get(d.get("role"), d.get("role")), "token_version": d.get("token_version")}


def has_role(user: dict | None, need: str) -> bool:
    return bool(user) and ROLES.get(user.get("role"), 0) >= ROLES[need]


# ---------------- login (with a small lock-out against password guessing) ----------------
_fails: dict[str, list[float]] = {}
_lock = threading.Lock()


def login(conn, username: str, password: str) -> dict:
    u = (username or "").strip().lower()
    with _lock:
        recent = [t for t in _fails.get(u, []) if time.time() - t < LOCK_SECONDS]
        _fails[u] = recent
        if len(recent) >= MAX_FAILS:
            raise AuthError(f"ใส่รหัสผิดหลายครั้ง ลองใหม่ใน {LOCK_SECONDS // 60} นาที")
    init(conn)
    r = conn.execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()
    if not r or not r["active"] or not check_password(password or "", r["pw_hash"]):
        with _lock:
            _fails.setdefault(u, []).append(time.time())
        raise AuthError("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    with _lock:
        _fails.pop(u, None)
    conn.execute("UPDATE users SET last_login=? WHERE id=?", (now(), r["id"])); conn.commit()
    return public_user(conn.execute("SELECT * FROM users WHERE id=?", (r["id"],)).fetchone())


# ---------------- accounts ----------------
def _check(username=None, password=None, role=None, team=None, for_role=None):
    if username is not None and not USER_RX.match(username):
        raise AuthError("ชื่อผู้ใช้ 3–32 ตัว ใช้ a-z 0-9 . _ - เท่านั้น")
    if password is not None and len(password) < 8:
        raise AuthError("รหัสผ่านอย่างน้อย 8 ตัวอักษร")
    if role is not None and role not in ROLES:
        raise AuthError(f"role ต้องเป็นหนึ่งใน {list(ROLES)}")
    if (for_role or role) == "rescuer" and not (team or "").strip():
        raise AuthError("บัญชีทีมกู้ภัยต้องระบุชื่อทีม")


def create_user(conn, username: str, password: str, role: str, display_name: str = "", team: str | None = None) -> dict:
    username = (username or "").strip().lower()
    _check(username, password, role, team)
    init(conn)
    if conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
        raise AuthError("มีชื่อผู้ใช้นี้แล้ว")
    uid = "U-" + uuid.uuid4().hex[:8].upper()
    conn.execute("INSERT INTO users (id, username, display_name, role, team, pw_hash, created_at) VALUES (?,?,?,?,?,?,?)",
                 (uid, username, display_name or username, role, (team or "").strip() or None, hash_password(password), now()))
    conn.commit()
    return get_user(conn, uid)


def get_user(conn, uid: str) -> dict | None:
    init(conn)
    r = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    return public_user(r) if r else None


def list_users(conn) -> list[dict]:
    init(conn)
    return [public_user(r) for r in conn.execute("SELECT * FROM users ORDER BY role DESC, username")]


def update_user(conn, uid: str, *, role=None, team=None, display_name=None, active=None, password=None) -> dict | None:
    cur = get_user(conn, uid)
    if not cur:
        return None
    new_role = role or cur["role"]
    _check(password=password, role=role, team=team if team is not None else cur["team"], for_role=new_role)
    if cur["role"] == "admin" and (new_role != "admin" or active is False):
        n = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1 AND id<>?", (uid,)).fetchone()[0]
        if n == 0:
            raise AuthError("ต้องมีผู้ดูแลระบบที่ใช้งานได้อย่างน้อย 1 บัญชี")
    sets, args, bump = [], [], False
    for col, val in (("role", role), ("team", team), ("display_name", display_name)):
        if val is not None:
            sets.append(f"{col}=?"); args.append(val.strip() or None if isinstance(val, str) else val)
    if active is not None:
        sets.append("active=?"); args.append(int(bool(active)))
    if password:
        sets.append("pw_hash=?"); args.append(hash_password(password))
    bump = bool(password) or (role and role != cur["role"]) or (active is not None and not active)
    if bump:
        sets.append("token_version=token_version+1")
    if sets:
        conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id=?", [*args, uid]); conn.commit()
    return get_user(conn, uid)


def teams(conn) -> list[str]:
    init(conn)
    return [r[0] for r in conn.execute("SELECT DISTINCT team FROM users WHERE role='rescuer' AND active=1 AND team IS NOT NULL ORDER BY team")]


DEMO_ACCOUNTS = [("admin", "admin", "ผู้ดูแลระบบ", None), ("officer", "coordinator", "เจ้าหน้าที่ศูนย์ (เดโม)", None),
                 ("boat1", "rescuer", "ทีมเรือ 1 (เดโม)", "ทีมเรือ 1"), ("boat2", "rescuer", "ทีมเรือ 2 (เดโม)", "ทีมเรือ 2")]


def seed_accounts(conn) -> str | None:
    """First start only (no users yet): create the 4 demo accounts. The password is SEED_PASSWORD from .env,
    otherwise a random one that is printed ONCE in the API log. Returns the password used (None if nothing was created)."""
    init(conn)
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        return None
    pw = os.getenv("SEED_PASSWORD") or secrets.token_urlsafe(9)
    for username, role, name, team in DEMO_ACCOUNTS:
        create_user(conn, username, pw, role, name, team)
    log.warning("FloodLink: created accounts %s with password %s  (set SEED_PASSWORD in .env / change it in Admin)",
                ", ".join(a[0] for a in DEMO_ACCOUNTS), pw if not os.getenv("SEED_PASSWORD") else "(from SEED_PASSWORD)")
    return pw


# ---------------- audit log ----------------
def audit(conn, user: dict | str | None, action: str, case_id: str | None = None, detail: dict | None = None, commit=True):
    """Who did what. user = a user dict, or a label like 'reporter' / 'system'."""
    init(conn)
    actor, role = (user.get("username"), user.get("role")) if isinstance(user, dict) else (user or "system", None)
    conn.execute("INSERT INTO audit_log (ts, actor, role, action, case_id, detail) VALUES (?,?,?,?,?,?)",
                 (now(), actor, role, action, case_id, json.dumps(detail or {}, ensure_ascii=False)))
    if commit:
        conn.commit()


def audit_list(conn, case_id: str | None = None, limit: int = 200) -> list[dict]:
    init(conn)
    q, a = "SELECT * FROM audit_log", []
    if case_id:
        q += " WHERE case_id=?"; a.append(case_id)
    rows = [dict(r) for r in conn.execute(q + " ORDER BY id DESC LIMIT ?", [*a, limit])]
    for r in rows:
        r["detail"] = json.loads(r["detail"] or "{}")
    return rows

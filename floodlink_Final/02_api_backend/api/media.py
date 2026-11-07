"""Photos attached to a report (people mostly report from phones: a picture of the water level, the house, the patient).

* the browser shrinks each photo first (longest side 1600 px, JPEG) — see 01_web_app/src/photos.js
* here we only accept real JPEG / PNG / WebP bytes (checked by magic number, not by the name), at most MAX_PHOTOS
  per report and MAX_BYTES each, and store them as files next to the database (MEDIA_DIR)
* photos belong to the SUBMISSION (the original report); every case made from that report shows them
"""
import base64, binascii, hashlib, os, re, uuid
from .db import ensure
from pathlib import Path

MAX_PHOTOS = 4
MAX_BYTES = 3 * 1024 * 1024
MAGIC = {b"\xff\xd8\xff": ("image/jpeg", "jpg"), b"\x89PNG\r\n\x1a\n": ("image/png", "png")}
ID_RX = re.compile(r"^P-[0-9A-F]{10}$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS attachments (
  id TEXT PRIMARY KEY, submission_id TEXT, created_at TEXT, mime TEXT, size INTEGER, sha256 TEXT, path TEXT
);
CREATE INDEX IF NOT EXISTS ix_att_sub ON attachments(submission_id);
"""


def init(conn):
    ensure(conn, "media", SCHEMA)


class PhotoError(ValueError):
    pass


def media_dir() -> Path:
    d = Path(os.getenv("MEDIA_DIR") or Path(os.getenv("DB_PATH", "floodlink.db")).resolve().parent / "media")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sniff(b: bytes):
    for sig, kind in MAGIC.items():
        if b.startswith(sig):
            return kind
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


def decode(photo: str) -> tuple[bytes, str, str]:
    """'data:image/jpeg;base64,...' (or bare base64) -> (bytes, mime, ext). Raises PhotoError on anything else."""
    data = photo.split(",", 1)[1] if photo.startswith("data:") else photo
    if len(data) > MAX_BYTES * 4 // 3 + 16:
        raise PhotoError(f"รูปใหญ่เกิน {MAX_BYTES // 1024 // 1024} MB")
    try:
        b = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise PhotoError("ไฟล์รูปเสีย (base64 ไม่ถูกต้อง)")
    if len(b) > MAX_BYTES:
        raise PhotoError(f"รูปใหญ่เกิน {MAX_BYTES // 1024 // 1024} MB")
    kind = _sniff(b)
    if not kind:
        raise PhotoError("รับเฉพาะรูป JPEG / PNG / WebP")
    return b, kind[0], kind[1]


def validate(photos: list[str] | None) -> list[tuple[bytes, str, str]]:
    """Check every photo BEFORE anything is stored, so a bad photo never leaves half a report behind."""
    photos = photos or []
    if len(photos) > MAX_PHOTOS:
        raise PhotoError(f"แนบรูปได้ไม่เกิน {MAX_PHOTOS} รูปต่อครั้ง")
    return [decode(p) for p in photos]


def save(conn, submission_id: str, decoded: list[tuple[bytes, str, str]], ts: str) -> list[dict]:
    init(conn)
    out, d = [], media_dir()
    for b, mime, ext in decoded:
        pid = "P-" + uuid.uuid4().hex[:10].upper()
        path = d / f"{pid}.{ext}"
        path.write_bytes(b)
        conn.execute("INSERT INTO attachments VALUES (?,?,?,?,?,?,?)",
                     (pid, submission_id, ts, mime, len(b), hashlib.sha256(b).hexdigest(), path.name))
        out.append({"id": pid, "url": url(pid), "mime": mime, "size": len(b)})
    return out


def url(pid: str) -> str:
    return f"/api/media/{pid}"


def get(conn, pid: str):
    """-> (absolute file path, mime) or None. The id is checked strictly so no path can be smuggled in."""
    if not ID_RX.match(pid or ""):
        return None
    init(conn)
    r = conn.execute("SELECT path, mime FROM attachments WHERE id=?", (pid,)).fetchone()
    if not r:
        return None
    p = media_dir() / r["path"]
    return (p, r["mime"]) if p.is_file() else None


def for_submissions(conn, sids: list[str]) -> dict[str, list[dict]]:
    init(conn)
    sids = [s for s in set(sids) if s]
    if not sids:
        return {}
    out: dict[str, list[dict]] = {}
    for r in conn.execute(f"SELECT id, submission_id, mime FROM attachments WHERE submission_id IN ({','.join('?' * len(sids))}) "
                          "ORDER BY created_at, rowid", sids):
        out.setdefault(r["submission_id"], []).append({"id": r["id"], "url": url(r["id"]), "mime": r["mime"]})
    return out


def for_cases(conn) -> dict[str, list[dict]]:
    """case id -> photos from every report merged into it (no duplicates)."""
    init(conn)
    out: dict[str, list[dict]] = {}
    seen = set()
    for r in conn.execute("""SELECT DISTINCT m.case_id, a.id, a.mime FROM attachments a
                             JOIN messages m ON m.submission_id = a.submission_id
                             WHERE m.case_id IS NOT NULL ORDER BY a.created_at, a.rowid"""):
        if (r["case_id"], r["id"]) not in seen:
            seen.add((r["case_id"], r["id"]))
            out.setdefault(r["case_id"], []).append({"id": r["id"], "url": url(r["id"]), "mime": r["mime"]})
    return out

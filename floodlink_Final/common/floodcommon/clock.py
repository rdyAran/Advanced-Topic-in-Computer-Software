"""One clock for the whole system: Thailand time WITH the offset (2026-11-04T02:13:20+07:00).

Why: Docker containers run in UTC. Older versions saved "2026-11-03T19:13:20" (UTC, no offset); a browser reads a
time without an offset as ITS local time, so in Thailand every case looked 7 hours older ("7 ชม.ก่อน" for a case sent
a minute ago). With the offset in the string every browser shows the right time.

APP_UTC_OFFSET   hours of the local time zone (default 7 = Thailand, no daylight saving)
LEGACY_TZ_OFFSET hours of the times saved WITHOUT an offset by older versions (default 0 = UTC, the Docker default;
                 set 7 if you ran the API directly on a Windows PC in Thailand)
"""
import datetime as dt
import os, re

TZ = dt.timezone(dt.timedelta(hours=float(os.getenv("APP_UTC_OFFSET", "7"))))
LEGACY = dt.timezone(dt.timedelta(hours=float(os.getenv("LEGACY_TZ_OFFSET", "0"))))
NAIVE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$")


def now() -> dt.datetime:
    return dt.datetime.now(TZ)


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def parse(ts: str | None, naive_tz: dt.tzinfo = LEGACY) -> dt.datetime | None:
    """ISO text -> aware datetime. A time without an offset is taken as naive_tz."""
    if not ts:
        return None
    try:
        d = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=naive_tz)


def normalize(ts: str | None, naive_tz: dt.tzinfo = TZ) -> str | None:
    """Any incoming timestamp -> local time with offset. A timestamp WITHOUT an offset coming in from outside
    (a client, a dataset row) is taken as local time — that is what a person in Thailand typed."""
    d = parse(ts, naive_tz)
    return d.astimezone(TZ).isoformat(timespec="seconds") if d else None


def from_epoch(seconds: float) -> str:
    return dt.datetime.fromtimestamp(seconds, TZ).isoformat(timespec="seconds")


# columns that hold timestamps (used by the one-time upgrade of old databases)
TIME_COLUMNS = {
    "cases": ["created_at", "updated_at", "closed_at", "assigned_at", "accepted_at"],
    "messages": ["received_at"], "submissions": ["received_at"], "hazards": ["created_at"],
    "ai_feedback": ["created_at"], "attachments": ["created_at"], "corrections": ["created_at"],
    "audit_log": ["ts"], "users": ["created_at", "last_login"], "teams": ["located_at", "updated_at"],
}


def upgrade_naive_times(conn) -> int:
    """Rewrite times saved without an offset (older versions) as local time with offset. Idempotent."""
    n = 0
    for table, cols in TIME_COLUMNS.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col in [c for c in cols if c in have]:
            for rowid, v in conn.execute(f"SELECT rowid, {col} FROM {table} WHERE {col} IS NOT NULL AND {col} NOT LIKE '%+%' "
                                         f"AND {col} NOT LIKE '%Z'").fetchall():
                if NAIVE.match(str(v)):
                    conn.execute(f"UPDATE {table} SET {col}=? WHERE rowid=?", (parse(v, LEGACY).astimezone(TZ).isoformat(timespec="seconds"), rowid))
                    n += 1
    if n:
        conn.commit()
    return n

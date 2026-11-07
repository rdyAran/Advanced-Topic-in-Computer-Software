"""One SQLite connection shared by all FastAPI worker threads — made thread-safe.

FastAPI runs sync endpoints AND sync dependencies (e.g. reading the login cookie) in a thread pool, so several
requests use the connection at the same moment. sqlite3 with check_same_thread=False does not serialise that, and
under load it fails with "sqlite3.InterfaceError: bad parameter or other API misuse".

LockedConnection runs every statement under one lock and reads the rows immediately, so a cursor is never
shared between threads. The demo load is small, so serialising is cheaper than a pool.
"""
import sqlite3, threading


class _Rows:
    """The part of sqlite3.Cursor the code uses: fetchone / fetchall / iteration (rows already read)."""
    __slots__ = ("_rows", "_i", "lastrowid", "rowcount")

    def __init__(self, rows, lastrowid=None, rowcount=-1):
        self._rows, self._i, self.lastrowid, self.rowcount = rows, 0, lastrowid, rowcount

    def fetchone(self):
        if self._i >= len(self._rows):
            return None
        self._i += 1
        return self._rows[self._i - 1]

    def fetchall(self):
        out, self._i = self._rows[self._i:], len(self._rows)
        return out

    def __iter__(self):
        return iter(self.fetchall())


class LockedConnection:
    def __init__(self, raw: sqlite3.Connection):
        self.raw = raw
        self.lock = threading.RLock()
        self.ready: set[str] = set()        # schemas already created on this connection (see ensure())

    @property
    def row_factory(self):
        return self.raw.row_factory

    @row_factory.setter
    def row_factory(self, v):
        self.raw.row_factory = v

    def execute(self, sql, args=()):
        with self.lock:
            cur = self.raw.execute(sql, args)
            return _Rows(cur.fetchall(), cur.lastrowid, cur.rowcount)

    def executescript(self, sql):
        with self.lock:
            self.raw.executescript(sql)

    def commit(self):
        with self.lock:
            self.raw.commit()

    def close(self):
        with self.lock:
            self.raw.close()


def ensure(conn, key: str, schema: str):
    """Create a module's tables once per connection (executescript also COMMITs, so not on every request)."""
    ready = getattr(conn, "ready", None)
    if ready is not None and key in ready:
        return
    conn.executescript(schema)
    if ready is not None:
        ready.add(key)

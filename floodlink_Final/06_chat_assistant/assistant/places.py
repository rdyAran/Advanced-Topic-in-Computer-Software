"""Places (donation hubs, shelters, distribution points, kitchens, medical) + recommendation tools.

Everything the chatbot says about WHERE to go comes from this table — never invented by an LLM.
"""
import json, math, sqlite3
from pathlib import Path
from urllib.parse import quote
from floodcommon.triage import geocode, normalize_area

DEMO = Path(__file__).resolve().parent.parent / "data" / "places_demo.json"
TYPES = {"donation_hub": "จุดรับของบริจาค", "kitchen": "ครัวกลาง", "shelter": "ศูนย์พักพิง",
         "distribution": "จุดแจกของ/ถุงยังชีพ", "medical": "หน่วยปฐมพยาบาล"}
ITEM_TH = {"water": "น้ำดื่ม", "food": "อาหาร", "milk": "นมเด็ก", "medicine": "ยา", "power": "พาวเวอร์แบงค์/ไฟฉาย",
           "hygiene": "ของใช้สุขอนามัย", "clothes": "เสื้อผ้า", "sandbags": "กระสอบทราย", "boat": "เรือ/อุปกรณ์กู้ภัย"}
CASE_NEED = {"water": "water", "food": "food", "milk": "milk", "medicine": "medicine", "power": "power"}   # item -> case need

SCHEMA = """CREATE TABLE IF NOT EXISTS places (
  id TEXT PRIMARY KEY, type TEXT, name TEXT, area TEXT, lat REAL, lng REAL, address TEXT,
  accepts TEXT, short_of TEXT, services TEXT, capacity INTEGER, occupancy INTEGER,
  hours TEXT, contact TEXT, status TEXT DEFAULT 'open', is_demo INTEGER DEFAULT 0, updated_at TEXT)"""
JSON_COLS = ("accepts", "short_of", "services")


def init(conn: sqlite3.Connection, seed_demo: bool = True):
    conn.execute(SCHEMA)
    if seed_demo and conn.execute("SELECT COUNT(*) FROM places").fetchone()[0] == 0:
        for p in json.loads(DEMO.read_text(encoding="utf-8"))["places"]:
            upsert(conn, {**p, "is_demo": 1})
    conn.commit()


def upsert(conn, p: dict) -> dict:
    row = {k: p.get(k) for k in ("id", "type", "name", "area", "lat", "lng", "address", "hours", "contact", "status",
                                 "capacity", "occupancy", "is_demo")}
    row["status"] = row["status"] or "open"
    if row["lat"] is None and row["area"]:
        row["lat"], row["lng"] = geocode(normalize_area(row["area"]) or row["area"])
    for k in JSON_COLS:
        row[k] = json.dumps(p.get(k) or [], ensure_ascii=False)
    cols = ",".join(row)
    conn.execute(f"INSERT OR REPLACE INTO places ({cols}, updated_at) VALUES ({','.join('?' * len(row))}, datetime('now'))", list(row.values()))
    conn.commit()
    return get(conn, row["id"])


def _row(r) -> dict:
    d = dict(r)
    for k in JSON_COLS:
        d[k] = json.loads(d[k] or "[]")
    d["type_th"] = TYPES.get(d["type"], d["type"])
    d["nav_url"] = f"https://www.google.com/maps/dir/?api=1&destination={d['lat']},{d['lng']}&travelmode=driving" if d["lat"] else None
    return d


def get(conn, pid: str) -> dict | None:
    r = conn.execute("SELECT * FROM places WHERE id=?", (pid,)).fetchone()
    return _row(r) if r else None


def list_places(conn, type_: str | None = None, status: str = "open") -> list[dict]:
    q, a = "SELECT * FROM places WHERE status=?", [status]
    if type_:
        q += " AND type=?"; a.append(type_)
    return [_row(r) for r in conn.execute(q, a)]


def km(a_lat, a_lng, b_lat, b_lng) -> float:
    r = math.pi / 180
    h = math.sin((b_lat - a_lat) * r / 2) ** 2 + math.cos(a_lat * r) * math.cos(b_lat * r) * math.sin((b_lng - a_lng) * r / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def demand_by_area(conn, need: str | None) -> dict:
    """How many OPEN cases in each area need this item (from the case table built by the intake AI)."""
    if not need:
        return {}
    out = {}
    for area, needs in conn.execute("SELECT area, needs FROM cases WHERE status IN ('new','verified','assigned','in_progress')"):
        if area and need in json.loads(needs or "[]"):
            out[area] = out.get(area, 0) + 1
    return out


def recommend_hubs(conn, item: str | None, lat: float | None = None, lng: float | None = None, top: int = 3) -> list[dict]:
    """Rank donation hubs/kitchens for an item: hub says it's short of it > area demand from open cases > distance."""
    demand = demand_by_area(conn, CASE_NEED.get(item))
    max_d = max(demand.values(), default=0) or 1
    out = []
    for p in list_places(conn, "donation_hub") + list_places(conn, "kitchen"):
        if item and item not in p["accepts"]:
            continue
        dist = km(lat, lng, p["lat"], p["lng"]) if lat is not None and p["lat"] is not None else None
        short = item in p["short_of"] if item else False
        d = demand.get(p["area"], 0)
        score = 2.0 * short + 1.5 * d / max_d + (1.0 / (1 + dist) if dist is not None else 0)
        why = []
        if short: why.append(f"จุดนี้แจ้งว่า{ITEM_TH.get(item, item)}เหลือน้อย")
        if d: why.append(f"พื้นที่{p['area']}มีเคสขาด{ITEM_TH.get(item, item)}อยู่ {d} เคส")
        if dist is not None: why.append(f"ห่างจากคุณ ~{dist:.1f} กม.")
        out.append({**p, "score": round(score, 3), "distance_km": round(dist, 1) if dist is not None else None, "why": why})
    return sorted(out, key=lambda x: -x["score"])[:top]


def nearest(conn, type_: str, lat: float | None, lng: float | None, top: int = 3) -> list[dict]:
    ps = list_places(conn, type_)
    for p in ps:
        p["distance_km"] = round(km(lat, lng, p["lat"], p["lng"]), 1) if lat is not None and p["lat"] is not None else None
        if p.get("capacity"):
            p["free"] = max(p["capacity"] - (p.get("occupancy") or 0), 0)
    key = (lambda p: p["distance_km"]) if lat is not None else (lambda p: -(p.get("free") or 0))
    return sorted(ps, key=key)[:top]


def needs_summary(conn, top: int = 5) -> list[dict]:
    """Which areas lack what, from open cases — for volunteers and donors."""
    agg = {}
    for area, needs, prio in conn.execute("SELECT area, needs, priority FROM cases WHERE status IN ('new','verified','assigned','in_progress')"):
        a = agg.setdefault(area or "ไม่ทราบพื้นที่", {"area": area or "ไม่ทราบพื้นที่", "open": 0, "red": 0, "needs": {}})
        a["open"] += 1; a["red"] += prio == "red"
        for n in json.loads(needs or "[]"):
            a["needs"][n] = a["needs"].get(n, 0) + 1
    return sorted(agg.values(), key=lambda a: (-a["red"], -a["open"]))[:top]


def maps_search_url(q: str) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={quote(q)}"

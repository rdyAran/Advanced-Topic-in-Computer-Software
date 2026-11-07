"""Location from the message + Google Maps navigation link.

Precision levels (best first):
  exact    - GPS coordinates or a Google Maps link with coordinates in the text  -> navigate to the exact point
  link     - a short Google Maps link (maps.app.goo.gl/...) we can't decode     -> open that link as-is
  address  - house no. / soi / landmark + area                                   -> Google searches the address
  area     - only the area name (gazetteer centroid)                              -> approximate, warn the team
"""
import os, re, urllib.request
from urllib.parse import quote, urlparse

# Thailand bounding box (rough) — rejects random number pairs that aren't coordinates
LAT_RANGE, LNG_RANGE = (5.0, 21.0), (97.0, 106.0)

_PAIR = r"(-?\d{1,2}\.\d{3,})\s*,\s*(-?\d{2,3}\.\d{3,})"
_URL_COORDS = [
    re.compile(r"@" + _PAIR),                                        # .../@7.0081,100.4752,17z
    re.compile(r"[?&](?:q|query|ll|destination|daddr)=" + _PAIR),     # ?q=7.0081,100.4752
    re.compile(r"!3d(-?\d{1,2}\.\d+)!4d(-?\d{2,3}\.\d+)"),           # place URLs
]
_TEXT_COORDS = re.compile(r"(?:พิกัด|gps|location|lat|ละติจูด)?\s*[:：]?\s*" + _PAIR, re.I)
_SHORT_LINK = re.compile(r"https?://(?:maps\.app\.goo\.gl|goo\.gl/maps|maps\.google\.[a-z.]+|www\.google\.[a-z.]+/maps)\S*", re.I)


def _ok(lat: float, lng: float) -> bool:
    return LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LNG_RANGE[0] <= lng <= LNG_RANGE[1]


def extract_location(text: str) -> dict:
    """{'lat','lng','map_url','precision'} found in the raw message (precision None if nothing usable)."""
    url = _SHORT_LINK.search(text or "")
    for rx in _URL_COORDS + [_TEXT_COORDS]:
        for m in rx.finditer(text or ""):
            lat, lng = float(m.group(1)), float(m.group(2))
            if _ok(lat, lng):
                return {"lat": round(lat, 6), "lng": round(lng, 6), "map_url": url.group(0) if url else None, "precision": "exact"}
    if url:
        return {"lat": None, "lng": None, "map_url": url.group(0).rstrip(").,"), "precision": "link"}
    return {"lat": None, "lng": None, "map_url": None, "precision": None}


def address_query(case: dict) -> str | None:
    parts = []
    if case.get("house_no"): parts.append(f"บ้านเลขที่ {case['house_no']}")
    for k in ("street", "landmark"):
        if case.get(k): parts.append(str(case[k]))
    if not parts:
        return None
    area = (case.get("area") or "").replace(" หาดใหญ่", "")
    return " ".join(parts + ([area] if area else []) + ["หาดใหญ่ สงขลา"])


def nav_url(case: dict) -> dict:
    """Best Google Maps directions link for a case + how precise it is (shown to the rescue team)."""
    prec = case.get("geo_precision")
    if prec == "exact" and case.get("lat") is not None:
        return {"url": f"https://www.google.com/maps/dir/?api=1&destination={case['lat']},{case['lng']}&travelmode=driving",
                "precision": "exact", "label": "นำทางไปพิกัดที่ผู้แจ้งส่งมา"}
    if case.get("map_url"):
        return {"url": case["map_url"], "precision": "link", "label": "เปิดลิงก์แผนที่ที่ผู้แจ้งส่งมา"}
    q = address_query(case)
    if q:
        return {"url": f"https://www.google.com/maps/dir/?api=1&destination={quote(q)}&travelmode=driving",
                "precision": "address", "label": "นำทางตามที่อยู่ (ให้ Google ค้นหา — ตรวจหมุดก่อนออกเดินทาง)"}
    if case.get("lat") is not None:
        return {"url": f"https://www.google.com/maps/dir/?api=1&destination={case['lat']},{case['lng']}&travelmode=driving",
                "precision": "area", "label": "⚠️ ตำแหน่งโดยประมาณระดับพื้นที่ — โทรยืนยันจุดก่อน"}
    return {"url": None, "precision": None, "label": "ยังไม่มีตำแหน่ง"}


# ---------------- short Google Maps links (maps.app.goo.gl/...) -> coordinates ----------------
_ALLOWED = re.compile(r"^(?:maps\.app\.goo\.gl|goo\.gl|(?:www\.|maps\.|consent\.)?google\.(?:com|co\.[a-z]{2}|com\.[a-z]{2}|[a-z]{2}))$", re.I)
_cache: dict[str, tuple | None] = {}


class _GoogleOnly(urllib.request.HTTPRedirectHandler):
    """Follow redirects only inside Google (never to an arbitrary host — no SSRF through a crafted link)."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _ALLOWED.match(urlparse(newurl).hostname or ""):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def coords_in_url(url: str):
    for rx in _URL_COORDS:
        m = rx.search(url or "")
        if m:
            lat, lng = float(m.group(1)), float(m.group(2))
            if _ok(lat, lng):
                return round(lat, 6), round(lng, 6)
    return None


def resolve_map_link(url: str, timeout: float = 4.0):
    """(lat, lng) behind a short Google Maps link, or None. Best effort: any error -> None. Off with RESOLVE_MAP_LINKS=0."""
    if not url or os.getenv("RESOLVE_MAP_LINKS", "1") == "0":
        return None
    if url in _cache:
        return _cache[url]
    out = coords_in_url(url)
    if out is None and _ALLOWED.match(urlparse(url).hostname or ""):
        try:
            opener = urllib.request.build_opener(_GoogleOnly)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 FloodLink"})
            with opener.open(req, timeout=timeout) as r:
                out = coords_in_url(r.geturl())
                if out is None:                                   # some pages carry the point only in the HTML
                    out = coords_in_url(r.read(200_000).decode("utf-8", "ignore"))
        except Exception:
            out = None
    _cache[url] = out
    return out

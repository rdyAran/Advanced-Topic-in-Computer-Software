"""Small in-memory limits for the PUBLIC endpoints (no login): report a case, chatbot, tracking-link follow-ups.

Why: anyone can submit without an account, so one person (or a script) could flood the queue with fake cases — real
cases sink down the list — and burn the LLM quota. Staff (logged in) are never limited.

  * per client: RATE_PER_MIN (default 6) and RATE_PER_HOUR (default 40) requests per kind
  * the SAME text again from the same client within DUP_WINDOW_MIN (default 10) minutes is not a new case:
    the earlier answer is returned (people press "send" twice when the network is slow)
Behind Cloudflare Tunnel / a proxy set TRUST_PROXY=1 so the real client IP (CF-Connecting-IP / X-Forwarded-For) is used.
"""
import hashlib, os, threading, time
from collections import defaultdict, deque

PER_MIN = int(os.getenv("RATE_PER_MIN", "6"))
PER_HOUR = int(os.getenv("RATE_PER_HOUR", "40"))
DUP_WINDOW = int(os.getenv("DUP_WINDOW_MIN", "10")) * 60
TRUST_PROXY = os.getenv("TRUST_PROXY", "0") == "1"


class Limited(Exception):
    def __init__(self, retry_after: int):
        super().__init__(f"ส่งถี่เกินไป กรุณารอ {retry_after} วินาที (ถ้าอันตรายถึงชีวิต โทร 1669 / 1784)")
        self.retry_after = retry_after


class Limiter:
    def __init__(self, per_min=PER_MIN, per_hour=PER_HOUR, dup_window=DUP_WINDOW, clock=time.time):
        self.per_min, self.per_hour, self.dup_window, self.clock = per_min, per_hour, dup_window, clock
        self.hits: dict[tuple, deque] = defaultdict(deque)
        self.recent: dict[tuple, tuple[float, dict]] = {}
        self.lock = threading.Lock()

    def check(self, client: str, kind: str):
        """Raise Limited if this client sent too many `kind` requests."""
        now = self.clock()
        with self.lock:
            q = self.hits[(client, kind)]
            while q and now - q[0] > 3600:
                q.popleft()
            last_min = sum(1 for t in q if now - t < 60)
            if last_min >= self.per_min:
                raise Limited(int(60 - (now - [t for t in q if now - t < 60][0])) + 1)
            if len(q) >= self.per_hour:
                raise Limited(int(3600 - (now - q[0])) + 1)
            q.append(now)

    @staticmethod
    def _key(client, text):
        return client, hashlib.sha256(" ".join((text or "").split()).encode()).hexdigest()

    def duplicate(self, client: str, text: str) -> dict | None:
        """The answer given to the same text from the same client a moment ago, if any."""
        now = self.clock()
        with self.lock:
            hit = self.recent.get(self._key(client, text))
            if hit and now - hit[0] < self.dup_window:
                return hit[1]
            return None

    def remember(self, client: str, text: str, answer: dict):
        now = self.clock()
        with self.lock:
            self.recent[self._key(client, text)] = (now, answer)
            if len(self.recent) > 5000:                      # keep memory bounded
                for k, (t, _) in list(self.recent.items()):
                    if now - t > self.dup_window:
                        del self.recent[k]


def client_id(request) -> str:
    h = request.headers
    if TRUST_PROXY:
        ip = h.get("cf-connecting-ip") or (h.get("x-forwarded-for") or "").split(",")[0].strip()
        if ip:
            return ip
    return getattr(request.client, "host", None) or "unknown"

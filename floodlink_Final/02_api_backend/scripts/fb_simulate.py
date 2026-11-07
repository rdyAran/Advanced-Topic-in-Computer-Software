"""ยิงข้อความจำลองแบบเดียวกับที่ Facebook ส่งมา -> ทดสอบ webhook ได้โดยไม่ต้องมีเพจจริง / ไม่ต้องออกเน็ต

  python 02_api_backend/scripts/fb_simulate.py                      # ส่งตัวอย่าง: คอมเมนต์ 2 อัน + แชท Messenger 1 อัน
  python 02_api_backend/scripts/fb_simulate.py --comment "ช่วยด้วย ..." --name "สมชาย"
  python 02_api_backend/scripts/fb_simulate.py --message "มีน้ำ 200 แพ็ค ส่งที่ไหนดี"
  python 02_api_backend/scripts/fb_simulate.py --verify             # ลองขั้น verify แบบที่ Meta ทำตอนกด "Verify and save"

อ่าน FB_APP_SECRET / FB_VERIFY_TOKEN จาก .env (ถ้ามี) เพื่อเซ็น X-Hub-Signature-256 ให้เหมือนของจริง
"""
import argparse, hashlib, hmac, json, os, random, time, urllib.parse, urllib.request
from pathlib import Path

for line in (Path(__file__).resolve().parents[2] / ".env").read_text(encoding="utf-8").splitlines() if (Path(__file__).resolve().parents[2] / ".env").exists() else []:
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())

PAGE = "1000000000000001"
SAMPLES = [
    ("comment", "คุณแม่", "ช่วยด้วยค่ะ ยายอายุ 85 ติดเตียง น้ำถึงชั้น 2 แล้ว คอหงส์ ซ.สังทิศ 2 โทร 081-234-1234"),
    ("comment", "น้องบอส", "ฝากด้วยครับ คลองแห\nเคส 1 บ้านเลขที่ 12 ซ.คลองแห 2 ผู้ใหญ่ 3 เด็ก 2 ขวบ อาหารหมด\nเคส 2 ซ.คลองแห 6 ลุงฟอกไต ขอเรือ"),
    ("messenger", None, "มีน้ำดื่ม 200 แพ็ค ควรเอาไปวางที่ไหนครับ"),
]


def payload(kind, text, name):
    now = int(time.time()); rid = str(random.randint(10**14, 10**15))
    if kind == "messenger":
        return {"object": "page", "entry": [{"id": PAGE, "time": now * 1000, "messaging": [{
            "sender": {"id": "7" + rid}, "recipient": {"id": PAGE}, "timestamp": now * 1000,
            "message": {"mid": "m_" + rid, "text": text}}]}]}
    return {"object": "page", "entry": [{"id": PAGE, "time": now, "changes": [{"field": "feed", "value": {
        "item": "comment", "verb": "add", "post_id": f"{PAGE}_111", "comment_id": f"111_{rid}", "parent_id": f"{PAGE}_111",
        "from": {"id": "9" + rid, "name": name or "ผู้ใช้ทดสอบ"}, "message": text, "created_time": now}}]}]}


def send(url, body):
    raw = json.dumps(body, ensure_ascii=False).encode()
    h = {"Content-Type": "application/json"}
    if os.getenv("FB_APP_SECRET"):
        h["X-Hub-Signature-256"] = "sha256=" + hmac.new(os.environ["FB_APP_SECRET"].encode(), raw, hashlib.sha256).hexdigest()
    with urllib.request.urlopen(urllib.request.Request(url, data=raw, headers=h), timeout=30) as r:
        return r.read().decode()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000/webhooks/facebook")
    ap.add_argument("--comment"); ap.add_argument("--message"); ap.add_argument("--name")
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    if a.verify:
        q = urllib.parse.urlencode({"hub.mode": "subscribe", "hub.verify_token": os.getenv("FB_VERIFY_TOKEN", "floodlink-dev"), "hub.challenge": "12345"})
        print("verify ->", urllib.request.urlopen(f"{a.url}?{q}").read().decode(), "(ต้องได้ 12345)"); raise SystemExit
    items = [("comment", a.name, a.comment)] if a.comment else [("messenger", None, a.message)] if a.message else SAMPLES
    for kind, name, text in items:
        print(f"{kind:9s} -> {send(a.url, payload(kind, text, name))}  {text[:50]!r}")
    print("\nเปิดหน้าเว็บ: เคสใหม่จะขึ้นในคิวภายในไม่กี่วินาที (ช่องทาง fb_comment / fb_messenger)")

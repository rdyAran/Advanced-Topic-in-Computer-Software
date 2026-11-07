"""Diagnose the Gemini connection.  Run:  docker compose exec agent python -m agent.check_gemini"""
import os, sys
from dotenv import load_dotenv
load_dotenv()

key = os.getenv("GEMINI_API_KEY", "")
model = os.getenv("GEMINI_MODEL") or "(auto)"
print(f"1) GEMINI_API_KEY: {'set (' + key[:4] + '…' + key[-3:] + ')' if key else 'MISSING'}  |  GEMINI_MODEL: {model}")
if not key:
    sys.exit("   -> ใส่ GEMINI_API_KEY ในไฟล์ .env แล้วรัน docker compose up ใหม่")

from google import genai
client = genai.Client(api_key=key)

print("2) โมเดลที่ key นี้ใช้ได้ (ตระกูล flash):")
try:
    names = [m.name.replace("models/", "") for m in client.models.list()]
    flash = [n for n in names if "flash" in n]
    print("   " + ", ".join(flash[:15]) or "   (ไม่พบ)")
    if os.getenv("GEMINI_MODEL") and model not in names:
        print(f"   !! '{model}' ไม่อยู่ในรายการ -> ตั้ง GEMINI_MODEL ใน .env เป็นตัวใดตัวหนึ่งข้างบน")
except Exception as e:
    print("   list models failed:", str(e)[:300])

from agent.providers import GeminiProvider
model = GeminiProvider().model
print(f"   -> จะใช้โมเดล: {model}")
print("3) เรียกแบบข้อความธรรมดา:")
try:
    r = client.models.generate_content(model=model, contents="ตอบคำว่า OK คำเดียว")
    print("   OK ->", (r.text or "").strip()[:50])
except Exception as e:
    sys.exit(f"   FAIL -> {str(e)[:400]}\n   (401/403 = key ผิด/ยังไม่เปิดใช้, 404 = ชื่อโมเดลผิด, 429 = เกินโควตา)")

print("4) เรียกแบบ Intake Agent (JSON schema) — วัดเวลาทุกรุ่น:")
import time
prov = GeminiProvider()
ok = []
for m in [prov.model] + prov.backups:
    t = time.time()
    try:
        e = prov._call(m, "ช่วยด้วย ยายอายุ 85 ติดเตียง น้ำถึงชั้น 2 คอหงส์ ซ.สังทิศ 2 โทร 081-xxx-1234")
        print(f"   OK   {m:<28} {time.time()-t:5.1f}s  flags={[f.value for f in e.flags]} water={e.water_level}")
        ok.append((time.time() - t, m))
    except Exception as ex:
        print(f"   FAIL {m:<28} {time.time()-t:5.1f}s  {str(ex)[:160]}")
if not ok:
    sys.exit("   ไม่มีรุ่นไหนใช้ได้ — ส่งผลนี้มาให้ดู")
best = min(ok)[1]
print(f"ทุกอย่างพร้อม ✅  รุ่นที่ตอบเร็วสุด: {best}  (ถ้ารุ่นหลักช้า/ล่มบ่อย ตั้ง GEMINI_MODEL={best} ใน .env)")

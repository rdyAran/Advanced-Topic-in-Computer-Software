"""Check every configured LLM provider with one real extraction.
Run:  docker compose exec agent python -m agent.check_llm
(For Gemini model listing / per-model timing use: python -m agent.check_gemini)
"""
import os, sys, time
from dotenv import load_dotenv
load_dotenv()
from agent.router import _make, KEYS

SAMPLE = "ช่วยด้วย ยายอายุ 85 ติดเตียง น้ำถึงชั้น 2 คอหงส์ ซ.สังทิศ 2 โทร 081-xxx-1234"
order = [n.strip() for n in os.getenv("LLM_PROVIDERS", "gemini,groq").split(",") if n.strip()]
print(f"LLM_PROVIDERS = {','.join(order)}  (order = which one is tried first)\n")
ok = 0
for name in order:
    if name not in KEYS:
        print(f"[{name}] unknown provider (use: {', '.join(KEYS)})"); continue
    key = os.getenv(KEYS[name], "")
    if not key:
        print(f"[{name}] skipped — {KEYS[name]} is empty in .env"); continue
    print(f"[{name}] key {key[:4]}…{key[-3:]}", end="  ")
    p = _make(name, interactive=True)
    if p is None:
        print("-> failed to start (see log above)"); continue
    t = time.time()
    try:
        e = p.extract(SAMPLE)
        print(f"model={p.model}  OK {time.time() - t:.1f}s  flags={[f.value for f in e.flags]} water={e.water_level.value if e.water_level else None}")
        ok += 1
    except Exception as ex:
        print(f"model={p.model}  FAIL {time.time() - t:.1f}s  {str(ex)[:220]}")
print("\nพร้อมใช้ ✅" if ok else "\nไม่มี LLM ไหนใช้ได้ — ระบบจะใช้โมเดลของเราอย่างเดียว (ยังทำงานได้)")
sys.exit(0)

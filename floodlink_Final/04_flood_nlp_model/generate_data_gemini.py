"""Teacher-LLM data: ask Gemini to WRITE natural messages for label specs we choose.

Labels are fixed by us (sampled like generate_data.py), Gemini only writes the text -> labels stay exact,
but wording becomes far more natural than templates. Then:  python train.py --extra data/gemini_train.jsonl

    python generate_data_gemini.py --n 300 --per 3 --out data/gemini_train.jsonl     (≈300 API calls)
NOTE: not runnable in the build sandbox (no API key) — test it on your machine.
"""
import argparse, json, os, random, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for p in ["common", "03_intake_ai_agent"]:
    sys.path.insert(0, str(ROOT / p))
try:
    from dotenv import load_dotenv; load_dotenv(ROOT / ".env")
except ImportError:
    pass
from generate_data import help_message, OTHER          # noqa: E402

TH = {"bedridden": "ผู้ป่วยติดเตียง", "dialysis": "ผู้ป่วยต้องฟอกไต", "heart": "ผู้ป่วยโรคหัวใจ", "pregnant": "หญิงตั้งครรภ์",
      "injured": "คนบาดเจ็บ", "disabled_blind": "ผู้พิการทางสายตา", "wheelchair": "คนเดินไม่ได้/ใช้วีลแชร์",
      "food": "อาหาร", "water": "น้ำดื่ม", "milk": "นมเด็ก", "medicine": "ยา", "evacuation": "เรือ/อพยพ", "power": "ไฟฟ้า/แบตโทรศัพท์",
      "knee": "เข่า", "waist": "เอว", "chest": "อก", "floor1": "ท่วมมิดชั้น 1", "floor2": "ถึงชั้น 2", "roof": "ต้องอยู่บนหลังคา"}
STYLES = ["พิมพ์รีบๆ ไม่เว้นวรรค", "ภาษาพูดคนใต้", "ญาติโพสต์แทนจากต่างจังหวัด", "สุภาพ เรียบร้อย", "ตื่นตระหนก ใช้อีโมจิ",
          "สั้นมาก", "ผสมภาษาอังกฤษ", "เล่ายาว อ้อมๆ ไม่ใช้คำตรงๆ"]

PROMPT = """เขียนข้อความขอความช่วยเหลือช่วงน้ำท่วมหาดใหญ่ แบบที่คนโพสต์จริงใน Facebook/LINE จำนวน {k} ข้อความ ที่ต่างกันมาก
ข้อเท็จจริงที่ทุกข้อความต้องมี (ห้ามเพิ่มกลุ่มเปราะบางหรือสิ่งที่ต้องการอื่นนอกจากนี้):
- กลุ่มเปราะบาง: {flags}
- ระดับน้ำ: {water}
- สิ่งที่ต้องการ: {needs}
สไตล์: {style}. ใช้คำอ้อม/คำพ้องได้ (เช่น 'นอนอยู่กับที่' แทน 'ติดเตียง'). ใส่ชื่อซอย/จุดสังเกตสมมติได้
ตอบเป็น JSON array ของ string เท่านั้น"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--per", type=int, default=3)
    ap.add_argument("--sleep", type=float, default=4)
    ap.add_argument("--out", default=str(HERE / "data/gemini_train.jsonl"))
    a = ap.parse_args()
    from agent.providers import GeminiProvider
    from google.genai import types
    g = GeminiProvider(interactive=False)
    random.seed(2026)
    done = 0
    with open(a.out, "a", encoding="utf-8") as f:
        for i in range(a.n):
            _, lab = help_message()
            prompt = PROMPT.format(k=a.per, flags=", ".join(TH[x] for x in lab["flags"]) or "ไม่มี",
                                   water=TH.get(lab["water_level"], "ไม่ระบุ"), needs=", ".join(TH[x] for x in lab["needs"]) or "ไม่ระบุ",
                                   style=random.choice(STYLES))
            try:
                r = g.client.models.generate_content(model=g.model, contents=prompt, config=types.GenerateContentConfig(
                    response_mime_type="application/json", response_schema={"type": "ARRAY", "items": {"type": "STRING"}}, temperature=1.0))
                for text in json.loads(r.text)[: a.per]:
                    f.write(json.dumps({"text": text, **lab, "source": "gemini_generated"}, ensure_ascii=False) + "\n")
                    done += 1
            except Exception as e:
                print("skip:", str(e)[:120])
            if i % 20 == 0:
                print(f"{i}/{a.n} specs, {done} messages"); f.flush()
            time.sleep(a.sleep)
    print(f"done: {done} messages -> {a.out}  (review a sample by hand before training!)")


if __name__ == "__main__":
    main()

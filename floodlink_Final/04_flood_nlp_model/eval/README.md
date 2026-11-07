# เครื่องมือวัดผลให้ตัวเลขน่าเชื่อถือ (กลุ่ม 2)

ลำดับที่แนะนำ: **A3 → A1 → A2 → A5 → A6** · ทุกคำสั่งรันจากโฟลเดอร์ `04_flood_nlp_model/eval/` (ยกเว้น A6 รันใน container api)
ไฟล์ข้อมูลอยู่ที่ `04_flood_nlp_model/realdata/data/` (train/dev/test.jsonl จาก `build_dataset.py`) หรือใน Google Drive `MyDrive/floodlink_wcb/data/`

| ขั้น | ปัญหาที่แก้ | ใครทำ | คำสั่ง |
|---|---|---|---|
| **A3** ข้อสอบรั่ว | test มีข้อความซ้ำ/เกือบซ้ำกับ train (โพสต์ที่แชร์ซ้ำ) | รันเอง 1 นาที | `python check_leakage.py ../realdata/data/train.jsonl ../realdata/data/test.jsonl --dev ../realdata/data/dev.jsonl --write` |
| **A1** ข้อสอบชุดใหม่ | ตัวเลขเดิมวัดจาก test ที่เราใช้ปรับกฎไปแล้ว | **คนนอกทีม 2–3 คน** เขียน 50–100 ข้อความลง `fresh_test_template.csv` (ให้มีเคสแดงอย่างน้อย 15–20) | `docker compose cp my_fresh_test.csv agent:/srv/04_flood_nlp_model/eval/` แล้ว `docker compose exec agent python /srv/04_flood_nlp_model/eval/eval_fresh.py /srv/04_flood_nlp_model/eval/my_fresh_test.csv` |
| **A2** ป้ายเชื่อถือได้ไหม | ป้ายส่วนใหญ่ติดโดย AI | **2 คน** ติดป้ายชุดเดียวกันแยกกัน | `python agreement.py sample ../realdata/data/test.jsonl --n 150` → ติดป้าย → `python agreement.py score annotator_A.csv annotator_B.csv --ai ../realdata/data/test.jsonl` |
| **A5** ความมั่นใจไม่ตรงจริง | "52%" ไม่ได้แปลว่าถูก 52% · เกณฑ์ส่งต่อ LLM 0.5 เป็นการกะเอา | รันใน Colab (GPU) หรือ container agent | `python calibrate.py --model ../artifacts/floodwcb_model --dev ../realdata/data/dev.jsonl --test ../realdata/data/test.jsonl --write` |
| **A6** รวมเคสผิด | ยังไม่เคยวัดว่ารวมเคสซ้ำถูกกี่ % | ติดป้าย ~60 คู่ว่าบ้านเดียวกันไหม | `docker compose exec api python -m api.tools.eval_merge sample` → กรอก `same` → `... eval_merge score` |

## อ่านผลอย่างไร (ใส่สไลด์ได้เลย)
- **A3:** ถ้า test ซ้ำกับ train เกิน ~5% ให้รายงานผลบน `test_clean.jsonl` คู่กับตัวเลขเดิม
- **A1:** ตัวเลขชุดนี้คือ "ผลจริง" — ถ้าต่ำกว่าเดิมเป็นเรื่องปกติ และน่าเชื่อถือกว่า · ดู `*_errors.csv` แถว `UNDER` (ให้สีต่ำกว่าจริง) ก่อน
- **A2:** kappa > 0.8 ดีมาก · 0.6–0.8 ดี · < 0.6 แปลว่าคู่มือติดป้าย (`LABEL_GUIDE.md`) ยังไม่ชัด → ดู `disagreements.csv` แล้วปรับคู่มือ
- **A5:** ECE ลดลง = ความมั่นใจเชื่อถือได้ขึ้น · เอา `ESCALATE_THRESHOLD` ที่แนะนำไปใส่ใน `.env` แล้ว `docker compose restart agent`
- **A6:** ตั้ง `DUP_THRESHOLD` ให้รวมผิด ≤ 2% · คู่ที่ต่ำกว่านั้นระบบจะขึ้น "อาจซ้ำกับ C-xxx" ให้เจ้าหน้าที่ตัดสิน (`DUP_SUGGEST_THRESHOLD`)

ห้ามใช้ข้อสอบชุดใหม่ (A1) ไปปรับกฎหรือเทรน — ถ้าจะปรับ ให้เขียนชุดใหม่อีกรอบแล้ววัดใหม่

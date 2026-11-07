# ข้อมูลจริงสำหรับเทรน (หาดใหญ่ พ.ย. 2568)

```
ข้อความดิบ (Ctrl+A จาก FB)  ->  prepare.py        แยกคอมเมนต์ ปิดข้อมูลส่วนตัว รวมข้อความซ้ำ   -> data/to_label.csv
                             ->  label_groq.py     Groq ติดป้ายร่างตาม LABEL_GUIDE.md          -> data/labels.jsonl
                             ->  build_dataset.py  แบ่ง train/dev/test + ทำชีตให้คนตรวจชุดทดสอบ  -> data/*.jsonl, review_test.csv
                             ->  (คนตรวจ review_test.csv)  -> build_dataset.py --reviewed ...  -> พร้อมเทรน WangchanBERTa
```

## ขั้นตอน
```powershell
cd 04_flood_nlp_model/realdata
python label_groq.py --limit 40          # ลองชุดเล็กก่อน แล้วเปิด data/labels.jsonl ดูว่าป้ายสมเหตุสมผลไหม
python label_groq.py                     # ติดป้ายทั้งหมด ถ้าโควตาหมดกลางทาง รันคำสั่งเดิมซ้ำ ระบบทำต่อจากที่ค้างไว้
python build_dataset.py                  # ล็อกชุดทดสอบ (เมื่อติดป้ายครบ >= 90%) + สร้าง data/review_test.csv
#   ทีมตรวจ review_test.csv ตาม LABEL_GUIDE.md ข้อ 5 (แก้ช่องที่ผิด ใส่ reviewed=1)
python build_dataset.py --reviewed data/review_test.csv
```

## มีข้อความใหม่จากโพสต์อื่น
รวมข้อความดิบเป็นไฟล์เดียว แล้วรัน `python prepare.py raw_all.txt data` ใหม่
**ไฟล์ดิบมีชื่อและเบอร์จริง ห้ามใส่ใน git หรือส่งให้คนอื่น** ใช้เฉพาะไฟล์ใน `data/` ที่ปิดข้อมูลแล้ว

## ปิดข้อมูลส่วนตัวอะไรบ้าง (prepare.py)
- เบอร์โทร: สุ่มเลขใหม่ คงรูปแบบเดิมไว้
- บ้านเลขที่: สุ่มเลขใหม่
- พิกัด: เลื่อนตำแหน่ง ±400 ม.
- ลิงก์แผนที่: แทนด้วยลิงก์ปลอม
- ชื่อผู้คอมเมนต์, ชื่อที่มีคำนำหน้า (นาย/นาง/นางสาว/ด.ช./ด.ญ.), "ชื่อ ...", ชื่อภาษาอังกฤษ: แทนด้วย `<NAME>`
- ชื่อเล่นที่เหลือ: LLM ส่งกลับมาใน `person_names` แล้ว build_dataset.py ปิดให้อีกรอบ

ชื่อพื้นที่ ซอย ถนน และอายุ ไม่ได้ปิด เพราะโมเดลต้องใช้

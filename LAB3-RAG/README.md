# LAB 3 — RAG System Development II (motorcycle_qa.txt)

LAB นี้จำลอง 10 ปัญหาที่พบบ่อยในระบบ LLM / RAG โดยแปลงจาก DL-05 ให้ใช้ Knowledge Base `motorcycle_qa.txt` ชุดเดียวกับ LAB 2
ทุกปัญหาแบ่งเป็น 2 ส่วน

1. **Simulation**: ตัวอย่าง "ผิด vs แก้แล้ว" บนข้อมูลจริง
2. **Found in LAB 2**: ปัญหาเดียวกันที่พบในระบบ RAG + LLM ที่สร้างเองใน LAB 2 (จากโค้ดจริงและผลรันจริง)

## Structure

```text
LAB3/
├── motorcycle_qa.txt              # Raw data / RAG Knowledge Base (35 Q&A)
├── data_loader.py                 # Shared parser: motorcycle_qa.txt -> list of dict (+ char-bigram similarity)
├── main.py                        # Main menu for running each problem
├── problem01_hallucination.py     # Hallucination / answer without supporting context
├── problem02_transformer.py       # Vocabulary Mismatch (slang, typo) + Token Position / Truncation
├── problem03_data_quality.py      # Duplicate / Noise / Normalization / inconsistent labels
├── problem04_chunking.py          # Chunk Size / Overlap / character split on Thai
├── problem05_metadata.py          # Metadata Filtering (lang)
├── problem06_reranking.py         # Top-k / Re-ranking
├── problem07_generation.py        # Correct Retrieval but incorrect Generation + citation check
├── problem08_config.py            # RAG Configuration + validate()
├── problem09_evaluation.py        # Chunk & Retrieval Evaluation by query type
└── problem10_debug_scripts.py     # Debug RAG Scripts + RAG doctor for the LAB 2 folder
```

## Run

ใช้ Python มาตรฐานอย่างเดียว ไม่ต้องติดตั้ง package เพิ่ม

```powershell
python main.py          # เมนู
python main.py 0        # รันทุกข้อ
python main.py 7        # รันเฉพาะข้อ 7
python problem10_debug_scripts.py C:\Users\Administrator\Desktop\work-ai--main\LAB2-RAG-LLM
```

`problem10` ตรวจโฟลเดอร์ `../LAB2-RAG-LLM` เป็นค่าเริ่มต้น ถ้าเครื่องติดตั้ง `sentence-transformers` ไว้ จะนับจำนวน token จริงของแต่ละ chunk ให้ด้วย (ใช้ยืนยัน Problem 2)

## Dataset

Knowledge Base ความรู้รถจักรยานยนต์ 35 ข้อ แบ่งเป็น 3 ระดับภาษา: ทางการ 16 / กันเอง 9 / แสลง 10

```text
[หมวด: <category>]                     หรือ   [หมวด: <category> | ภาษา: <variant>]
Q: <question>
A: <answer>
```

## Summary

| # | Problem | Simulation | Found in LAB 2 |
|---|---------|------------|----------------|
| 1 | Hallucination | คำถามนอกขอบเขต / คำถามที่ตรงแค่คำว่า "รถ" ยังได้คำตอบ | `MIN_SCORE` ประกาศไว้แต่ไม่ถูกใช้ ทำให้ส่ง top-3 ให้ LLM ทุกครั้ง |
| 2 | Vocabulary Mismatch / Position | BoW ของคำถามทางการ vs แสลง vs พิมพ์ผิด ไม่มีคำตรงกันเลย | "รถเสย สตารดไมดด" ได้คำตอบถูกที่อันดับ 2 / token ต่อ chunk 77–129 เกิน 128 แค่ 1 chunk |
| 3 | Data Quality | ล้าง noise ของข้อมูลจำลอง 9 แถว เหลือ 2 แถว | 35 ข้อแต่มีชื่อหมวด 10 ชื่อ ซ้อนกันหลายคู่ และข้อมูลไม่ครอบคลุม |
| 4 | Chunking | chunk ใหญ่ / เล็ก / overlap | ตัดตามจำนวนตัวอักษร ทำให้ตัดกลางคำไทย และ chunk ที่ 2 ไม่มีคำถามติดไป |
| 5 | Metadata Filtering | กรอง `lang` แล้วได้ภาษาทางการ แต่ถ้ากรองเข้มเกินจะได้ผิดหัวข้อ | LAB 2 เก็บ `\| ภาษา:` ไว้ในชื่อหมวด ทำให้มี 13 หมวดและกรองตามภาษาไม่ได้ |
| 6 | Re-ranking | เอกสารเรื่องเฟืองท้ายจากอันดับ 6 ขึ้นเป็นอันดับ 1 หลัง rerank | `USE_RERANK=False` และ RRF ใช้แค่อันดับ |
| 7 | Faithfulness | "ห้ามสตาร์ท" กลายเป็น "สตาร์ทได้ทันที", 95 dB กลายเป็น 110 dB | qwen2.5:7b ใส่ `[1][2][3]` ในประโยคถามกลับ (citation_check จับได้) |
| 8 | RAG Configuration | `validate(CONFIG)` เจอ 4 ปัญหา | error 404 / 429 / 503 / WinError 10061 / index เก่าค้าง ล้วนเป็นปัญหา config |
| 9 | Evaluation | Hit@1: verbatim 1.00 แต่ natural 0.50, typo 0.50 | golden set ของ LAB 2 ส่วนใหญ่เป็น verbatim/partial และไม่มี typo หรือ out-of-scope |
| 10 | Debug Scripts | 4 bug: encoding, off-by-one, ลำดับ index ไม่ตรง, index เก่า | RAG doctor ตรวจโฟลเดอร์ LAB 2 แล้วรายงาน ✓/✗ |

---

## Problem 1 — Hallucination

**Simulation:** `retrieve()` ให้คะแนนตามสัดส่วนคำที่ตรงกัน

| Query | Retrieved | Bad | Fixed (`min_score=0.6`) |
|-------|-----------|-----|-------------------------|
| ตั๋วเครื่องบินไปเชียงใหม่ราคาเท่าไหร่ | ไม่พบ | แต่งข้อมูลเรื่องน้ำมันดีเซลขึ้นมา | ไม่พบข้อมูล |
| รถ ยนต์ไฟฟ้า ชาร์จ กี่ชั่วโมง | ส่วนประกอบรถ (0.50) | ตอบเรื่องส่วนประกอบรถ | ไม่พบข้อมูล |
| รถ ใช้ E20 ได้ไหม | E20 (0.75) | ตอบถูก | ตอบถูก |

**Found in LAB 2:** `config.py` มี `MIN_SCORE = 0.0` แต่ไม่มีไฟล์ไหนเรียกใช้ ผลรันจริง: ถาม "รถเสียทำใง" ได้ context เป็นน้ำมันเฟืองท้าย โช้คหลัง และจอดตากแดด ระบบไม่ hallucinate เพราะกฎใน prompt อย่างเดียว
**Fix:** ตัด chunk ที่คะแนนต่ำกว่า threshold ออกก่อนเรียก LLM

## Problem 2 — Vocabulary Mismatch + Token Position

**Simulation:** ภาษาไทยไม่มีช่องว่างระหว่างคำ ทั้งประโยคจึงกลายเป็น token เดียวสำหรับ BoW

| KB question | User question | BoW overlap | Char-bigram sim |
|-------------|---------------|-------------|-----------------|
| ควรเปลี่ยนน้ำมันเครื่องรถจักรยานยนต์บ่อยแค่ไหน | น้ำมันเครื่อง ต้องถ่ายทุกกี่โลวะ | None | 0.22 |
| กดสตาร์ทแล้วรถไม่ติด ... | รถเสย สตารดไมดด | None | 0.12 |

ส่วนตัวอย่างการสลับลำดับคำ ("ห้ามสตาร์ทเด็ดขาด ...") ได้ BoW เหมือนเดิมทุกตัว ทั้งที่ความหมายเปลี่ยน

**Found in LAB 2:**
- ผลรันจริง คำถามพิมพ์ผิด "รถเสย สตารดไมดด" ได้ "ซื้อรถมือสอง" เป็นอันดับ 1
- Token limit: `paraphrase-multilingual-MiniLM-L12-v2` ตัดข้อความที่ยาวเกิน `max_seq_length` (128 tokens) ทิ้ง ผลวัดจริงด้วย `problem10`: **token ต่อ chunk 77–129 มีแค่ 1 จาก 35 chunks ที่เกิน (ตัดไป 1 token)** dataset ตอนนี้จึงแทบไม่ได้รับผลกระทบ แต่ถ้าเพิ่มคำตอบที่ยาวขึ้น ส่วนท้ายของคำตอบจะไม่ถูกนำไปคิด embedding และระบบจะไม่เตือนอะไรเลย (สิ่งเดียวที่บอกคือคำเตือนของ transformers `129 > 128`)

**Fix:** `USE_QUERY_TRANSFORM` (โหมด rewrite) ให้ LLM แก้คำผิดก่อนค้น, embed ส่วนคำถามแยกต่างหาก หรือใช้ `BAAI/bge-m3`

## Problem 3 — Data Quality

**Simulation:** ข้อมูลจำลองที่มี noise 9 แถว ผ่าน normalize + dedup แล้วเหลือ 2 แถว ส่วนไฟล์จริงไม่มีคำถามซ้ำเลย (0 duplicate)

**Found in LAB 2:**
- ข้อมูล 35 ข้อแต่มีชื่อหมวด **10 ชื่อ** และหลายชื่อซ้อนกัน เช่น `การบำรุงรักษา` ⊂ `การบำรุงรักษาและการแก้ปัญหา` และ `กฎหมาย` / `ความปลอดภัย` ⊂ `ความปลอดภัยและกฎหมาย`
- คู่เอกสารที่คล้ายกันที่สุด เช่น น้ำมันเครื่อง ↔ น้ำมันเฟืองท้าย (0.32) มีโอกาสสับสนเวลาค้น
- ข้อมูลน้อย คำถามที่พบบ่อยอย่าง "ไฟเลี้ยวไม่ติด" "เกียร์ค้าง" "ยางแบน" จึงไม่มีคำตอบ

**Fix:** ใช้ชื่อหมวดชุดเดียว (controlled vocabulary), เพิ่มข้อมูล และ validate ตอน build index

## Problem 4 — Chunking

**Simulation:** รวมคำตอบในหมวด `การบำรุงรักษาและการแก้ปัญหา` (88 คำ) แล้วตัดเป็น chunk ขนาด 60, 6 และ 25+overlap 8

**Found in LAB 2:** `split_text()` ตัดตาม**จำนวนตัวอักษร** เมื่อลองตั้ง `chunk_size=120` ทุก chunk จบกลางคำ และ chunk ที่ 1 เป็นต้นไปไม่มีข้อความคำถาม ตอนนี้ยังไม่มีข้อไหนถูกตัด เพราะ chunk ยาวที่สุดเท่ากับ 400 ตัวอักษรพอดี แต่ถ้าเพิ่มคำตอบที่ยาวขึ้นจะถูกตัดทันที
**Fix:** Q&A 1 คู่ = 1 chunk ถ้ายาวเกินให้ตัดที่ขอบประโยคและใส่คำถามซ้ำไว้ทุก chunk

## Problem 5 — Metadata Filtering

**Simulation:**
- `สตาร์ท ไม่ติด แบต` → ไม่กรอง: ได้คำตอบภาษากันเอง (สตาร์ทไม่ติด) / กรองเฉพาะ `ทางการ`: ได้แบตเตอรี่มีอายุเท่าไร (หัวข้อเกี่ยวข้อง ภาษาทางการ)
- `ยาง ดอกยาง สึก` → กรองเฉพาะ `ทางการ` ได้เรื่อง **ลมยาง** ซึ่งผิดหัวข้อ เพราะไม่มีข้อทางการที่พูดเรื่องยางหัวโล้น แปลว่า filter ต้องมีทางสำรอง (fallback)

**Found in LAB 2:** `document_loader.py` เก็บ `| ภาษา: แสลง` ไว้ในชื่อหมวด ทำให้มี 13 หมวด ไม่มี field `lang` และกรองตามระดับภาษาไม่ได้เลย
**Fix:** แยก field `category` กับ `lang` เก็บลง chunk_store แล้วกรองก่อนขั้น search

## Problem 6 — Re-ranking

**Simulation:** ผู้ใช้ถาม "รถออโต้วิ่งแล้วมีเสียงหอนจากล้อหลัง" ขั้นแรกนับคำทั่วไป (`รถ`, `ออโต้`, `หลัง`) แล้วเอกสารเฟืองท้ายได้**อันดับ 6** หลัง rerank ด้วยคำเฉพาะ (`เสียงหอน`, `เฟืองท้าย`) ขึ้นเป็น**อันดับ 1**

**Found in LAB 2:** คำตอบถูกของคำถามพิมพ์ผิดอยู่อันดับ 2 ถ้า `TOP_K=1` (แบบ LAB 1) ผู้ใช้จะได้คำตอบผิด, `USE_RERANK=False` เพราะโมเดลใหญ่ประมาณ 2 GB และ RRF รวมแค่อันดับ ไม่ได้ใช้คะแนน
**Fix:** เปิด cross-encoder (20 → 3) แล้วเทียบผลด้วย `eval_retrieval`

## Problem 7 — Faithfulness

**Simulation**

| Question | Context | Bad Generation | `faithfulness_check` |
|----------|---------|----------------|----------------------|
| รถจมน้ำมิด สตาร์ทได้ไหม | **ห้ามสตาร์ทเด็ดขาด** | **สตาร์ทได้ทันที** | ✗ ตัดคำ 'ห้าม' และ 'เด็ดขาด' ทิ้ง |
| ท่อแต่งโดนจับไหม | ไม่เกิน **95** เดซิเบล | ไม่เกิน **110** เดซิเบล | ✗ ตัวเลข '110' ไม่มีใน context |

**Found in LAB 2 (output จริงจาก qwen2.5:7b):**
> "คำถามนี้ไม่ชัดเจน ... ขอให้ระบุปัญหาเฉพาะเจาะจง [1][2][3]"

`citation_check` → `[1]/[2]/[3] cited but sentence does not use it (sim≈0.09)`
และเมื่อ LLM error ระบบ fallback ไปใช้ `chunks[0]` แม้จะเป็นคนละเรื่อง ส่วน `eval_generation` ที่วัดด้วย char-bigram จับกรณี "ห้าม" กลายเป็น "ได้" ไม่ได้

**Fix:** ตรวจคำตอบด้วย `faithfulness_check` + `citation_check` หลังสร้างคำตอบ และใช้ fallback เฉพาะเมื่อคะแนนผ่าน threshold

## Problem 8 — RAG Configuration

**Simulation:** `validate(CONFIG)` ด้วย config เดิมของ LAB 2 เจอ 4 ปัญหา: index เก่า, โมเดลถูกยกเลิก, ไม่มี API key และ `MIN_SCORE=0` หลังแก้ครบแล้วไม่เหลือปัญหา

**Found in LAB 2 (error ที่เกิดขึ้นจริง):**

| อาการ | สาเหตุ | แก้ |
|------|-------|-----|
| ยังตอบเรื่องคอมพิวเตอร์ | `SOURCE_FILE` เก่า + `vector_db/` ค้าง | ใช้ `index_meta.json` ให้ rebuild อัตโนมัติ |
| `ModuleNotFoundError` | pip ลงคนละ Python | `python -m pip install` |
| HTTP 404 | ชื่อโมเดลถูกยกเลิก | ย้ายชื่อโมเดลไปไว้ใน `.env` |
| HTTP 503 | server ไม่ว่าง | retry + backoff + fallback model |
| HTTP 429 | โควตาฟรีหมด | เปลี่ยนโมเดล / ใช้ Ollama |
| WinError 10061 | ไม่ได้เปิด Ollama | ติดตั้งแล้ว `ollama pull` |

## Problem 9 — Evaluation

**Simulation** (char-bigram retriever ที่ใช้หลักเดียวกับ BM25 ใน LAB 2)

| type | n | Hit@1 | Hit@3 | Hit@5 | MRR |
|------|---|-------|-------|-------|-----|
| verbatim | 6 | 1.00 | 1.00 | 1.00 | 1.00 |
| natural | 6 | 0.50 | 0.50 | 0.67 | 0.55 |
| slang | 4 | 0.75 | 0.75 | 0.75 | 0.79 |
| typo | 4 | 0.50 | 0.75 | 0.75 | 0.65 |

คำถามนอกขอบเขตทั้ง 4 ข้อถูกปฏิเสธที่ `MIN_SCORE=0.12` แต่คำถามในขอบเขต **12 จาก 14 ข้อ**ก็ถูกปฏิเสธไปด้วย แปลว่า threshold ที่คิดจากคะแนนแบบ lexical แยกสองกลุ่มนี้ออกจากกันไม่ได้

**Found in LAB 2:** golden set มี 113 queries แต่ **70 ข้อคัดลอกมาจาก KB** (verbatim + partial) ทำให้คะแนนรวมสูงเกินจริง, คำถาม paraphrase เขียนโดยคนเดียวกับที่สร้าง KB, ไม่มีคำถามพิมพ์ผิดหรือนอกขอบเขต และ generation metric เป็นแบบ lexical
**Fix:** รายงานผลแยกตามประเภทคำถาม, เพิ่มชุดคำถามพิมพ์ผิดและนอกขอบเขต, เพิ่ม `number_match` และ `refusal_accuracy`

## Problem 10 — Debug RAG Scripts

**Part A: 4 bug ที่เจอบ่อย (BUGGY vs FIXED)**

| Bug | BUGGY | FIXED |
|-----|-------|-------|
| 1. อ่านไฟล์โดยไม่ระบุ `encoding='utf-8'` | parse ได้ 0 ข้อ | parse ได้ 35 ข้อ |
| 2. off-by-one `ranked[1:4]` | คำตอบที่ดีที่สุดหายไป | `ranked[0:3]` |
| 3. ลำดับใน FAISS ≠ ลำดับใน chunk_store | ถามเรื่องขโมย ได้ ABS/CBS | assert ว่า id ตรงกัน |
| 4. ใช้ index เก่า | ถาม "รถเสีย" ได้ "RAM ทำหน้าที่อะไร" | `index_meta` + sha256 |

**Part B: RAG doctor** ตรวจโฟลเดอร์ LAB 2 จริง (ผลรันจริงบน Windows, Python 3.14.7)

```text
  ✓ SOURCE_FILE = motorcycle_qa.txt
  ✓ vector_db matches data file
  ✗ MIN_SCORE is defined in config.py but never used (Problem 1)
  ✗ document_loader keeps '| ภาษา: ...' inside category (Problem 5)
  ✓ .env is in .gitignore
  ✗ tokens per chunk 77-129, max_seq_length=128, 1/35 chunks truncated (Problem 2)
```

---

**สรุป:** ปัญหาที่พบใน LAB 2 ส่วนใหญ่**ไม่ได้มาจากโมเดล** แต่มาจากข้อมูล (Problem 3, 5), การตั้งค่า (Problem 1, 8) และการวัดผลที่ง่ายเกินจริง (Problem 9) ควรแก้ตามลำดับนี้

1. ใช้ `MIN_SCORE` จริง
2. แยก `category` / `lang`
3. ตรวจคำตอบด้วย faithfulness / citation check
4. เพิ่มคำถามพิมพ์ผิดและนอกขอบเขตใน golden set

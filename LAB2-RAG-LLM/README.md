# LAB 2 — RAG + LLM (รถจักรยานยนต์)

ต่อยอดจาก LAB 1 (retrieval อย่างเดียว) โดยเพิ่ม LLM มาสร้างคำตอบจากเอกสารที่ค้นเจอ พร้อมเลขอ้างอิง [1] [2]
โครงสร้างตาม Chapter 4: RAG System Development I

## ติดตั้ง
```powershell
python -m pip install -r requirements.txt
copy .env.example .env      # แล้วใส่ GEMINI_API_KEY ในไฟล์ .env
```
ขอ Gemini API key ฟรีได้ที่ https://aistudio.google.com/apikey
(หรือตั้ง `LLM_PROVIDER=ollama` เพื่อใช้โมเดลในเครื่อง / `openai`)

## รัน
```powershell
python build_index.py                      # 1) BUILD  (main.py ก็สร้างให้อัตโนมัติถ้าข้อมูลเปลี่ยน)
python main.py                             # 2) QUERY  แชตถาม-ตอบ
python -m evaluation.build_golden_set      # 3) EVALUATION
python -m evaluation.eval_retrieval        #    เทียบ dense / bm25 / hybrid / hybrid+rerank
python -m evaluation.eval_retrieval --no-rerank
python -m evaluation.eval_generation --limit 10
python -m evaluation.metrics               #    self-test ของ metrics
```

## Flags (config.py)
| Flag | Default | ความหมาย |
|---|---|---|
| USE_HYBRID | True | BM25 + dense รวมด้วย RRF |
| USE_RERANK | False | cross-encoder 20 → 3 (โมเดลใหญ่ ~2 GB) |
| USE_QUERY_TRANSFORM | False | rewrite / multi / hyde (ต้องใช้ LLM) |
| USE_MEMORY | True | จำ 6 รอบล่าสุด ใช้กับคำถามต่อเนื่อง |
| USE_LLM | True | False = ไม่เรียก LLM ตอบด้วยคำตอบที่ค้นเจอ |
| SHOW_DEBUG | False | แสดง chunk + คะแนน |

## โครงสร้าง
```
data/          motorcycle_qa.txt, golden_set.json
outputs/       extracted_text, chunks, embeddings, eval_*.json   (gitignored)
vector_db/     document.index, bm25_index.pkl, chunk_store.json, index_meta.json (gitignored)
labs/          lab01 – lab07 (จาก LAB 1)
src/           document_loader, text_splitter, embedding_model, vector_store, index_meta,
               retriever, hybrid_retriever, rerankers, query_transform, prompt_templates,
               generator, memory, rag_pipeline
evaluation/    metrics, build_golden_set, eval_retrieval, eval_generation
config.py  requirements.txt  build_index.py  main.py
```

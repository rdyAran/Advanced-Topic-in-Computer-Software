"""Build train_wangchanberta_colab.ipynb (embeds floodwcb.py so the notebook is self-contained)."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE = (HERE / "floodwcb.py").read_text(encoding="utf-8")

cells = []
md = lambda s: cells.append({"cell_type": "markdown", "metadata": {}, "source": s.strip("\n")})
code = lambda s: cells.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": s.strip("\n")})

md("""
# FloodLink — เทรน WangchanBERTa ด้วยข้อมูลจริง (Colab)

**ก่อนเริ่ม:** เมนู **Runtime → Change runtime type → T4 GPU** แล้วกด **Runtime → Run all**

ต้องมีไฟล์ 3 ไฟล์จาก `04_flood_nlp_model/realdata/data/` (สร้างด้วย `build_dataset.py`):
`train.jsonl`, `dev.jsonl`, `test.jsonl` — ถ้ายังไม่ได้วางใน Google Drive ช่องที่ 2 จะให้อัปโหลด

| ขั้น | เวลาโดยประมาณ (T4) |
|---|---|
| ติดตั้ง + โหลดโมเดล | 2–3 นาที |
| เทรน (สูงสุด 8 รอบ หยุดเองเมื่อไม่ดีขึ้น) | 10–25 นาที |
| วัดผล + ส่งออก | 2 นาที |

ผลลัพธ์: `floodwcb_model.zip` → แตกไฟล์ไว้ที่ `04_flood_nlp_model/artifacts/floodwcb_model/` ในโปรเจกต์
""")

md("## 1. เช็ก GPU และติดตั้ง")
code("""
!nvidia-smi --query-gpu=name,memory.total --format=csv || echo "⚠️ ไม่มี GPU — ไปที่ Runtime > Change runtime type > T4 GPU"
!pip -q install sentencepiece
import torch, transformers
print("torch", torch.__version__, "| transformers", transformers.__version__, "| cuda", torch.cuda.is_available())
""")

md("## 2. ตั้งค่า + ข้อมูล\nถ้าใช้ Google Drive: วางไฟล์ไว้ที่ `MyDrive/floodlink_wcb/data/` แล้วโมเดลจะถูกเซฟลง Drive ด้วย (กันหายถ้า Colab ตัด)")
code("""
from pathlib import Path
import shutil, json, os

USE_DRIVE = True          # False = ไม่ใช้ Drive (อัปโหลดเอง, เซฟใน Colab อย่างเดียว)
MAX_LEN = 256             # ข้อความยาวกว่านี้ (ราว 5% ของข้อมูล) จะถูกตัดท้าย
EPOCHS, BATCH, LR = 8, 16, 3e-5
PATIENCE = 2              # หยุดเมื่อคะแนน dev ไม่ดีขึ้น 2 รอบติด
RED_RECALL_TARGET = 0.98

WORK = Path("/content/work"); WORK.mkdir(exist_ok=True)
DATA = Path("/content/data"); DATA.mkdir(exist_ok=True)
DRIVE_DIR = None
if USE_DRIVE:
    try:
        from google.colab import drive
        drive.mount("/content/drive")
        DRIVE_DIR = Path("/content/drive/MyDrive/floodlink_wcb"); (DRIVE_DIR / "data").mkdir(parents=True, exist_ok=True)
        for n in ("train.jsonl", "dev.jsonl", "test.jsonl"):
            if (DRIVE_DIR / "data" / n).exists():
                shutil.copy(DRIVE_DIR / "data" / n, DATA / n)
    except Exception as e:
        print("ใช้ Drive ไม่ได้:", e); DRIVE_DIR = None

need = ["train.jsonl", "dev.jsonl", "test.jsonl"]
if not all((DATA / n).exists() for n in need):
    from google.colab import files
    print("อัปโหลด train.jsonl, dev.jsonl, test.jsonl (เลือกพร้อมกันได้)")
    for name, b in files.upload().items():
        for n in need:                                   # "train (1).jsonl" -> train.jsonl
            if name.replace(" ", "").startswith(n.split(".")[0]):
                (DATA / n).write_bytes(b)
missing = [n for n in need if not (DATA / n).exists()]
assert not missing, f"ยังขาดไฟล์: {missing}"
print("ข้อมูลพร้อม:", [f"{n} {sum(1 for _ in open(DATA / n, encoding='utf-8'))} แถว" for n in need])
""")

md("## 3. โค้ดโมเดล (`floodwcb.py` — ไฟล์เดียวกับในโปรเจกต์)")
cells.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
              "source": "%%writefile floodwcb.py\n" + MODULE})
code("""
import importlib, floodwcb as W
importlib.reload(W)
print("labels:", len(W.TYPES), "types |", len(W.FLAGS), "flags |", len(W.NEEDS), "needs |", len(W.WATER), "water levels")
""")

md("## 4. ตรวจข้อมูลก่อนเทรน")
code("""
from collections import Counter
load = lambda n: [json.loads(l) for l in open(DATA / n, encoding="utf-8") if l.strip()]
train_rows, dev_rows, test_rows = load("train.jsonl"), load("dev.jsonl"), load("test.jsonl")
print(f"train {len(train_rows)} | dev {len(dev_rows)} | test {len(test_rows)}")
print("ประเภท (train):", dict(Counter(r["message_type"] for r in train_rows)))
print("กลุ่มเปราะบาง (train):", dict(Counter(f for r in train_rows for f in r["flags"]).most_common()))
print("สี (train, help):", dict(Counter(r["priority"] for r in train_rows if r["message_type"] == "help_request")))
reviewed = sum(1 for r in test_rows if r.get("human_reviewed"))
print(f"\\nชุดทดสอบที่คนตรวจแล้ว: {reviewed}/{len(test_rows)}")
if reviewed < len(test_rows) * 0.9:
    print("⚠️ ชุดทดสอบยังไม่ได้ให้คนตรวจครบ — ผลที่ได้คือ 'เหมือน Groq แค่ไหน' ไม่ใช่ 'ถูกจริงแค่ไหน' ห้ามใช้ตัวเลขนี้ในรายงาน")
if len(train_rows) < 800:
    print("⚠️ ข้อมูลเทรนน้อย (<800) — เทรนได้ แต่ผลจะยังไม่นิ่ง")
ids = lambda rows: {r["row_id"] for r in rows}
assert not (ids(train_rows) & ids(test_rows)) and not (ids(dev_rows) & ids(test_rows)), "ข้อมูลรั่ว: มีแถวซ้ำระหว่าง train/dev กับ test"
""")

md("## 5. โหลด WangchanBERTa")
code("""
import random, numpy as np, torch, torch.nn as nn
from transformers import AutoTokenizer, AutoModel
SEED = 42; random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
device = "cuda" if torch.cuda.is_available() else "cpu"
try:
    tok = AutoTokenizer.from_pretrained(W.MODEL_NAME)
except Exception as e:
    print("fast tokenizer ใช้ไม่ได้ -> ใช้แบบ slow:", e)
    tok = AutoTokenizer.from_pretrained(W.MODEL_NAME, use_fast=False)
backbone = AutoModel.from_pretrained(W.MODEL_NAME)
model = W.FloodWCB(backbone, backbone.config.hidden_size).to(device)
sample = train_rows[0]["text"][:80]
print("ตัวอย่างการตัดคำ:", tok.tokenize(W.preprocess(sample))[:25])
lens = [len(tok(W.preprocess(r["text"]))["input_ids"]) for r in train_rows[:1000]]
print(f"ความยาว token: median {int(np.median(lens))}, p95 {int(np.percentile(lens, 95))}, ยาวเกิน {MAX_LEN}: {np.mean(np.array(lens) > MAX_LEN):.1%}")
""")

md("## 6. ชุดข้อมูล + loss (ถ่วงน้ำหนักกลุ่มที่หายาก)")
code("""
from torch.utils.data import Dataset, DataLoader

class DS(Dataset):
    def __init__(self, rows):
        self.txt = [W.preprocess(r["text"]) for r in rows]
        self.enc = [W.encode(r) for r in rows]
    def __len__(self): return len(self.txt)
    def __getitem__(self, i): return self.txt[i], self.enc[i]

def collate(batch):
    t = tok([b[0] for b in batch], truncation=True, max_length=MAX_LEN, padding=True, return_tensors="pt")
    e = [b[1] for b in batch]
    y = {"type": torch.tensor([x["type"] for x in e]), "water": torch.tensor([x["water"] for x in e]),
         "prio": torch.tensor([x["prio"] for x in e]), "bin_mask": torch.tensor([x["bin_mask"] for x in e], dtype=torch.float32)}
    for k in ("flags", "needs", "bin"):
        y[k] = torch.tensor(np.stack([x[k] for x in e]))
    return {"input_ids": t["input_ids"], "attention_mask": t["attention_mask"]}, y

train_ds, dev_ds, test_ds = DS(train_rows), DS(dev_rows), DS(test_rows)
train_dl = DataLoader(train_ds, batch_size=BATCH, shuffle=True, collate_fn=collate, num_workers=2)

def pos_weight(key):
    Y = np.stack([e[key] for e in train_ds.enc]); pos = Y.sum(0)
    return torch.tensor(np.clip((len(Y) - pos) / np.maximum(pos, 1), 1, 10), dtype=torch.float32, device=device)
tc = np.bincount([e["type"] for e in train_ds.enc], minlength=len(W.TYPES))
type_w = torch.tensor(np.clip(np.sqrt(tc.sum() / np.maximum(tc, 1) / len(tc)), 0.5, 5), dtype=torch.float32, device=device)
ce_type = nn.CrossEntropyLoss(weight=type_w)
ce = nn.CrossEntropyLoss(ignore_index=W.IGNORE)
bce_flags = nn.BCEWithLogitsLoss(pos_weight=pos_weight("flags"))
bce_needs = nn.BCEWithLogitsLoss(pos_weight=pos_weight("needs"))
bce_bin = nn.BCEWithLogitsLoss(reduction="none")

def loss_fn(o, y):
    L = ce_type(o["type"], y["type"]) + 1.5 * bce_flags(o["flags"], y["flags"]) + bce_needs(o["needs"], y["needs"])
    if (y["water"] != W.IGNORE).any(): L = L + 0.7 * ce(o["water"], y["water"])
    if (y["prio"] != W.IGNORE).any(): L = L + ce(o["prio"], y["prio"])
    m = y["bin_mask"]
    if m.sum() > 0: L = L + 0.5 * (bce_bin(o["bin"], y["bin"]).mean(1) * m).sum() / m.sum()
    return L

@torch.no_grad()
def predict_probs(ds):
    model.eval(); out = {k: [] for k in ("type", "flags", "needs", "water", "bin", "prio")}
    for x, _ in DataLoader(ds, batch_size=64, collate_fn=collate):
        with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=(device == "cuda")):
            o = model(x["input_ids"].to(device), x["attention_mask"].to(device))
        for k in out: out[k].append(o[k].float().cpu().numpy())
    return W.to_probs({k: np.concatenate(v) for k, v in out.items()})

def run_eval(ds, rows, th=None):
    probs = predict_probs(ds); texts = [r["text"] for r in rows]
    th = th or W.tune_thresholds(probs, rows, texts, RED_RECALL_TARGET)
    preds = [W.decode(probs, i, th, texts[i]) for i in range(len(rows))]
    return W.evaluate(preds, rows), th, preds, probs
print("type weights:", dict(zip(W.TYPES, type_w.cpu().numpy().round(2))))
""")

md("## 7. เทรน\nแต่ละรอบจะวัดกับชุด dev แล้วเก็บรอบที่ดีที่สุดไว้ (คะแนนเน้น: จับเคสแดงได้ > ประเภทถูก > กลุ่มเปราะบาง > สีถูก)")
code("""
import time
from transformers import get_linear_schedule_with_warmup
opt = torch.optim.AdamW([{"params": model.backbone.parameters(), "lr": LR},
                         {"params": model.heads.parameters(), "lr": 1e-3}], weight_decay=0.01)
total = EPOCHS * len(train_dl)
sched = get_linear_schedule_with_warmup(opt, int(0.1 * total), total)
use_amp = device == "cuda"
try:
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
except (AttributeError, TypeError):
    scaler = torch.cuda.amp.GradScaler(enabled=use_amp)

BEST = WORK / "best.pt"; best_score, bad, history = -1, 0, []
for ep in range(1, EPOCHS + 1):
    model.train(); t0, run = time.time(), 0.0
    for step, (x, y) in enumerate(train_dl, 1):
        x = {k: v.to(device) for k, v in x.items()}; y = {k: v.to(device) for k, v in y.items()}
        with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=use_amp):
            o = model(x["input_ids"], x["attention_mask"])
        loss = loss_fn({k: v.float() for k, v in o.items()}, y)
        opt.zero_grad(set_to_none=True)
        scaler.scale(loss).backward(); scaler.unscale_(opt)
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        scaler.step(opt); scaler.update(); sched.step()
        run += loss.item()
    m, th, _, _ = run_eval(dev_ds, dev_rows)
    s = W.score(m); history.append({"epoch": ep, "loss": round(run / step, 4), "score": s, "type_acc": m["type_acc"],
                                    "flags_f1": m.get("flags_macro_f1"), "red_recall": (m.get("red") or {}).get("recall"),
                                    "priority_acc": m.get("priority_acc")})
    print(f"epoch {ep}: loss {run / step:.4f} | dev score {s} | type {m['type_acc']} | flags F1 {m.get('flags_macro_f1')} "
          f"| red recall {(m.get('red') or {}).get('recall')} | colour {m.get('priority_acc')} | {time.time() - t0:.0f}s")
    if s > best_score:
        best_score, bad = s, 0
        torch.save(model.state_dict(), BEST)
        if DRIVE_DIR: shutil.copy(BEST, DRIVE_DIR / "best.pt")
        print("   ✓ เก็บเป็นรอบที่ดีที่สุด")
    else:
        bad += 1
        if bad >= PATIENCE:
            print("   หยุด: dev ไม่ดีขึ้น", PATIENCE, "รอบติด"); break
""")

md("## 8. วัดผลกับชุดทดสอบ (ไม่เคยเห็นตอนเทรน)\nเกณฑ์ (thresholds) ถูกตั้งจากชุด dev เท่านั้น แล้วนำมาใช้กับ test ตรง ๆ")
code("""
import pandas as pd
model.load_state_dict(torch.load(BEST, map_location=device))
m_dev, TH, _, _ = run_eval(dev_ds, dev_rows)
m_test, _, test_preds, _ = run_eval(test_ds, test_rows, TH)
print("เกณฑ์ที่ได้จาก dev:", json.dumps({"prio_red": TH["prio_red"], "help_min": TH["help_min"],
      "red_flags": {f: TH["flags"][f] for f in W.RED_FLAGS}}, ensure_ascii=False))
summary = {"ประเภทข้อความถูก": m_test["type_acc"], "กลุ่มเปราะบาง (macro F1)": m_test.get("flags_macro_f1"),
           "สิ่งที่ต้องการ (macro F1)": m_test.get("needs_macro_f1"), "ระดับน้ำถูก": m_test.get("water_acc"),
           "สีถูก (รวม 2 ทาง)": m_test.get("priority_acc"), "สีถูก (กฎอย่างเดียว)": m_test.get("priority_rules_acc"),
           "สีถูก (หัวทำนายอย่างเดียว)": m_test.get("priority_head_acc"),
           "จับเคสแดงได้ (recall)": (m_test.get("red") or {}).get("recall"), "เคสแดงที่ทาย ถูกจริง (precision)": (m_test.get("red") or {}).get("precision"),
           "ให้สีต่ำกว่าจริง (เคส)": m_test.get("under_triage")}
display(pd.DataFrame(summary.items(), columns=["ตัววัด (test)", "ค่า"]))
display(pd.DataFrame(m_test["type"]).T.rename_axis("ประเภท"))
display(pd.DataFrame(m_test["flags"]).T.rename_axis("กลุ่มเปราะบาง").sort_values("support", ascending=False))
display(pd.DataFrame(m_test["priority_confusion"]).T.rename_axis("จริง \\\\ ทาย"))
""")

md("## 9. ดูข้อผิดพลาด (ใช้ปรับคู่มือติดป้าย / หาข้อมูลเพิ่ม)")
code("""
pd.set_option("display.max_colwidth", 160)
err = []
for p, r in zip(test_preds, test_rows):
    if r["message_type"] == "help_request" and W.RANK[p["priority"]] < W.RANK.get(r["priority"], -1):
        err.append({"ชนิด": "ให้สีต่ำกว่าจริง", "จริง": r["priority"], "ทาย": p["priority"], "text": r["text"][:160],
                    "flags จริง": r["flags"], "flags ทาย": p["flags"]})
    elif p["message_type"] != r["message_type"]:
        err.append({"ชนิด": "ประเภทผิด", "จริง": r["message_type"], "ทาย": p["message_type"], "text": r["text"][:160],
                    "flags จริง": r["flags"], "flags ทาย": p["flags"]})
print(f"ผิดทั้งหมด {len(err)} จาก {len(test_rows)}  (ให้สีต่ำกว่าจริง {sum(e['ชนิด'] == 'ให้สีต่ำกว่าจริง' for e in err)})")
display(pd.DataFrame(err).sort_values("ชนิด").head(40))
""")

md("## 10. ลองพิมพ์ข้อความเอง")
code("""
def try_text(*texts):
    ds = DS([{"text": t, "message_type": "irrelevant", "flags": [], "needs": [], "priority": "none"} for t in texts])
    probs = predict_probs(ds)
    for i, t in enumerate(texts):
        p = W.decode(probs, i, TH, t)
        print(f"\\n{t}\\n -> {p['message_type']} | สี {p['priority']} (กฎ {p['priority_rules']}, หัว {p['priority_head']}) "
              f"| flags {p['flags']} | needs {p['needs']} | น้ำ {p['water_level']} | ติดต่อไม่ได้ {p['lost_contact']} | มั่นใจ {p['confidence']}")

try_text("แม่ต้องไปโรงพยาบาลทุกวันอังคาร ตอนนี้ออกจากบ้านไม่ได้ น้ำถึงชั้น 2 ซ.8 รัตนอุทิศ",
         "ได้รับการช่วยเหลือแล้วค่ะ ขอบคุณทีมกู้ภัยมาก ๆ",
         "สู้ ๆ นะคะพี่กัน",
         "มีเรือว่าง 2 ลำ อยู่หน้า มอ. ใครต้องการติดต่อได้",
         "ลูกสาว 8 เดือน ไข้สูง ติดอยู่ชั้น 2 คลองแห")
""")

md("## 11. ส่งออกโมเดล\nได้ `floodwcb_model.zip` → แตกไว้ที่ `04_flood_nlp_model/artifacts/floodwcb_model/` ในโปรเจกต์")
code("""
import datetime
EXPORT = Path("/content/floodwcb_model"); shutil.rmtree(EXPORT, ignore_errors=True); EXPORT.mkdir()
sd = {k: (v.half() if v.dtype == torch.float32 else v) for k, v in model.state_dict().items()}   # fp16: ไฟล์เล็กลงครึ่งหนึ่ง
torch.save(sd, EXPORT / "model.pt")
tok.save_pretrained(EXPORT); backbone.config.save_pretrained(EXPORT)
shutil.copy("floodwcb.py", EXPORT / "floodwcb.py")
cfg = {"model_name": W.MODEL_NAME, "max_len": MAX_LEN, "thresholds": TH, "version": "wcb-" + datetime.date.today().isoformat(),
       "labels": {"types": W.TYPES, "flags": W.FLAGS, "needs": W.NEEDS, "water": W.WATER, "prio": W.PRIO},
       "data": {"train": len(train_rows), "dev": len(dev_rows), "test": len(test_rows),
                "test_human_reviewed": sum(1 for r in test_rows if r.get("human_reviewed"))},
       "metrics_test": m_test, "metrics_dev": m_dev, "history": history}
(EXPORT / "floodwcb_config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2, default=float), encoding="utf-8")

# ตรวจว่าโหลดกลับได้ และทายเหมือนเดิม (แบบเดียวกับที่ backend จะโหลด)
P = W.Predictor(EXPORT, device="cpu")
check = [r["text"] for r in dev_rows[:20]]
same = sum(a["message_type"] == b["message_type"] and a["priority"] == b["priority"]
           for a, b in zip(P.predict(check), [W.decode(predict_probs(DS(dev_rows[:20])), i, TH, t) for i, t in enumerate(check)]))
print(f"โหลดกลับแล้วทายตรงกัน {same}/20 (ต่างกันเล็กน้อยได้จาก fp16)")

shutil.make_archive("/content/floodwcb_model", "zip", EXPORT)
size = Path("/content/floodwcb_model.zip").stat().st_size / 1e6
print(f"floodwcb_model.zip {size:.0f} MB")
if DRIVE_DIR:
    shutil.copy("/content/floodwcb_model.zip", DRIVE_DIR / "floodwcb_model.zip"); print("เซฟลง Drive แล้ว:", DRIVE_DIR)
try:
    from google.colab import files; files.download("/content/floodwcb_model.zip")
except Exception as e:
    print("ดาวน์โหลดเองจากแถบไฟล์ด้านซ้าย:", e)
""")

nb = {"cells": cells, "metadata": {"accelerator": "GPU", "colab": {"provenance": [], "gpuType": "T4"},
                                   "kernelspec": {"display_name": "Python 3", "name": "python3"},
                                   "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 0}
out = HERE / "train_wangchanberta_colab.ipynb"
out.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
print("wrote", out, len(cells), "cells")

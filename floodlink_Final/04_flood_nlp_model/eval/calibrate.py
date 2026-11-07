"""A5 — make the model's "confidence" mean what it says, then choose the escalate-to-LLM threshold from data.

Run where torch + the model are (Colab with GPU, or the agent container on CPU — a few minutes):
  python calibrate.py --model ../artifacts/floodwcb_model --dev ../realdata/data/dev.jsonl --test ../realdata/data/test.jsonl [--write]

1. temperature scaling: one number T per head (type, prio) chosen on DEV so that "80% sure" is right ~80% of the time
2. ECE (calibration error) before / after on TEST — lower is better
3. table: for each threshold, how many messages would go to the LLM and how accurate the rest (kept by our model) are
   -> suggested ESCALATE_THRESHOLD = the lowest one that keeps our model's own answers >= --target accurate
--write stores T in floodwcb_config.json (a backup is kept); Predictor applies it automatically.
"""
import argparse, json, shutil, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE)]
import floodwcb as W  # noqa: E402
from evalutil import load_rows, md_table  # noqa: E402


def softmax(x):
    e = np.exp(x - x.max(-1, keepdims=True)); return e / e.sum(-1, keepdims=True)


def nll(logits, y, T):
    p = softmax(logits / T)
    return -np.mean(np.log(p[np.arange(len(y)), y] + 1e-12))


def fit_T(logits, y):
    grid = np.concatenate([np.linspace(0.5, 1.5, 41), np.linspace(1.6, 5, 35)])
    return float(min(grid, key=lambda T: nll(logits, y, T)))


def ece(logits, y, T=1.0, bins=10):
    p = softmax(logits / T); conf = p.max(1); ok = p.argmax(1) == y
    e = 0.0
    for lo in np.linspace(0, 1, bins, endpoint=False):
        m = (conf > lo) & (conf <= lo + 1 / bins)
        if m.any():
            e += m.mean() * abs(ok[m].mean() - conf[m].mean())
    return float(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True); ap.add_argument("--dev", required=True); ap.add_argument("--test", required=True)
    ap.add_argument("--target", type=float, default=0.97, help="accuracy wanted for answers our model keeps")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    P = W.Predictor(a.model)
    dev, test = load_rows(a.dev), load_rows(a.test)
    out, Ts = {}, {}
    for name, rows in (("dev", dev), ("test", test)):
        out[name] = (P.logits([r["text"] for r in rows], 32), rows)
    lg, rows = out["dev"]
    y_type = np.array([W.TYPES.index(r["message_type"]) for r in rows])
    Ts["type"] = fit_T(lg["type"], y_type)
    hp = [i for i, r in enumerate(rows) if r["message_type"] == "help_request" and r.get("priority") in W.PRIO]
    if hp:
        Ts["prio"] = fit_T(lg["prio"][hp], np.array([W.PRIO.index(rows[i]["priority"]) for i in hp]))
    lt, rt = out["test"]
    yt = np.array([W.TYPES.index(r["message_type"]) for r in rt])
    print("\nTemperature (fit on dev):", {k: round(v, 2) for k, v in Ts.items()})
    print(f"ECE ประเภทข้อความบน test: ก่อน {ece(lt['type'], yt):.3f} -> หลัง {ece(lt['type'], yt, Ts['type']):.3f}  (ต่ำ = เชื่อถือได้)\n")
    # threshold table on DEV with the calibrated model + the same decode the agent uses
    P.cfg["temperature"] = Ts
    preds = P.predict([r["text"] for r in rows])
    conf = np.array([p["confidence"] for p in preds])
    ok = np.array([p["message_type"] == r["message_type"] and (r["message_type"] != "help_request" or p["priority"] == r.get("priority", p["priority"]))
                   for p, r in zip(preds, rows)])
    table, pick = [], None
    for th in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
        keep = conf >= th
        acc = ok[keep].mean() if keep.any() else float("nan")
        table.append([th, f"{1 - keep.mean():.0%}", f"{acc:.1%}"])
        if pick is None and acc >= a.target:
            pick = th
    print(md_table(table, ["เกณฑ์", "ส่งต่อ LLM", "ความแม่นของที่โมเดลเราตอบเอง"]))
    print(f"\nแนะนำ ESCALATE_THRESHOLD={pick if pick is not None else 'สูงกว่า 0.9 (โมเดลยังไม่แม่นพอ)'} "
          f"(ต่ำที่สุดที่ทำให้คำตอบของโมเดลเราแม่น ≥ {a.target:.0%}) — ใส่ใน .env")
    if a.write:
        cfgp = Path(a.model) / "floodwcb_config.json"
        shutil.copy(cfgp, cfgp.with_suffix(".json.bak"))
        cfg = json.loads(cfgp.read_text(encoding="utf-8")); cfg["temperature"] = Ts
        cfgp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"บันทึก temperature ลง {cfgp} แล้ว (สำรองไว้ที่ .bak) — docker compose restart agent")


if __name__ == "__main__":
    main()

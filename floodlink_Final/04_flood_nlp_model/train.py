"""Train FloodLink NLP model v1 and report validation scores.

    python generate_data.py --n 3000 --seed 7  --out data/train.jsonl
    python generate_data.py --n 500  --seed 99 --out data/val.jsonl
    python train.py                       # -> artifacts/floodnlp_v1.joblib + artifacts/metrics_v1.json
    python train.py --extra data/gemini_train.jsonl   # add teacher-LLM data (see generate_data_gemini.py)
"""
import argparse, json, sys, time
from pathlib import Path
import numpy as np
from sklearn.metrics import accuracy_score, f1_score

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from floodnlp.model import FloodNLPModel, FLAGS, NEEDS, DEFAULT_PATH  # noqa: E402


def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def evaluate(model, rows):
    preds = [model.predict(r["text"]) for r in rows]
    help_i = [i for i, r in enumerate(rows) if r["message_type"] == "help_request"]
    mlb = lambda lists, cls: np.array([[int(c in l) for c in cls] for l in lists])
    return {
        "message_type_acc": round(accuracy_score([r["message_type"] for r in rows], [p["message_type"] for p in preds]), 3),
        "water_level_acc": round(accuracy_score([rows[i]["water_level"] or "none" for i in help_i],
                                                [preds[i]["water_level"] or "none" for i in help_i]), 3),
        "flags_micro_f1": round(f1_score(mlb([rows[i]["flags"] for i in help_i], FLAGS), mlb([preds[i]["flags"] for i in help_i], FLAGS), average="micro", zero_division=0), 3),
        "needs_micro_f1": round(f1_score(mlb([rows[i]["needs"] for i in help_i], NEEDS), mlb([preds[i]["needs"] for i in help_i], NEEDS), average="micro", zero_division=0), 3),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default=str(HERE / "data/train.jsonl"))
    ap.add_argument("--val", default=str(HERE / "data/val.jsonl"))
    ap.add_argument("--extra", nargs="*", default=[])
    ap.add_argument("--out", default=str(DEFAULT_PATH))
    a = ap.parse_args()
    rows = load(a.train)
    for e in a.extra:
        if Path(e).exists():
            rows += load(e)
    # never train on the held-out test sets (teacher log may contain demo runs of them)
    held = HERE.parent / "05_evaluation" / "data"
    banned = {json.loads(l)["text"].strip() for f in held.glob("*.jsonl") for l in open(f, encoding="utf-8")}
    before = len(rows)
    rows = [r for r in rows if r["text"].strip() not in banned]
    if before != len(rows):
        print(f"removed {before - len(rows)} rows that appear in 05_evaluation test sets")
    t0 = time.time()
    model = FloodNLPModel().fit(rows)
    secs = round(time.time() - t0, 1)
    val = evaluate(model, load(a.val))
    t1 = time.time(); [model.predict("ช่วยด้วย ยายอายุ 85 ติดเตียง น้ำถึงชั้น 2") for _ in range(100)]
    latency_ms = round((time.time() - t1) * 10, 2)
    model.meta.update({"train_seconds": secs, "val": val, "latency_ms_per_message": latency_ms})
    model.save(a.out)
    (Path(a.out).parent / "metrics_v1.json").write_text(json.dumps(model.meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(model.meta, ensure_ascii=False, indent=2))

"""Evaluate the whole intake pipeline (agent 03 + case logic 02) on a labelled dataset.

Usage (from repo root):
    python 05_evaluation/evaluate.py --strategy rules                  # keyword baseline (before AI)
    python 05_evaluation/evaluate.py --strategy own                    # our trained model only (04)
    python 05_evaluation/evaluate.py --strategy gemini --sleep 4       # Gemini only
    python 05_evaluation/evaluate.py --strategy groq --sleep 15        # Groq only (free tier ≈ 8K tokens/min)
    python 05_evaluation/evaluate.py --strategy llm --sleep 4          # LLM chain (LLM_PROVIDERS order)
    python 05_evaluation/evaluate.py --strategy hybrid --sleep 4       # own model + escalate to LLM
    add  --data 05_evaluation/data/hard_messages.jsonl   for the hand-written hard set
    python 05_evaluation/evaluate.py --compare                         # rules vs own on both sets (no API)

Writes 05_evaluation/reports/report_<strategy>_<dataset>.md
"""
import argparse, json, os, sys, time, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in ["common", "02_api_backend", "03_intake_ai_agent", "04_flood_nlp_model"]:
    sys.path.insert(0, str(ROOT / _p))
try:
    from dotenv import load_dotenv; load_dotenv(ROOT / ".env")
except ImportError:
    pass
from agent.router import IntakeAgent                               # noqa: E402
from floodcommon.triage import priority, missing_fields            # noqa: E402
from floodcommon.schemas import Extraction                         # noqa: E402
from api import service                                            # noqa: E402

COLORS = ["red", "orange", "yellow", "green"]


def prf(pred: set, gold: set):
    tp = len(pred & gold)
    return tp, len(pred) - tp, len(gold) - tp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", default="own", choices=["rules", "own", "llm", "gemini", "groq", "hybrid"])
    ap.add_argument("--data", default=str(ROOT / "05_evaluation/data/flood_messages.jsonl"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=0.0)
    ap.add_argument("--threshold", type=float, default=None)
    ap.add_argument("--compare", action="store_true")
    a = ap.parse_args()
    if a.compare:
        return compare()
    print(json.dumps(run(a.strategy, a.data, a.limit, a.sleep, a.threshold), ensure_ascii=False, indent=2))


def run(strategy, data, limit=0, sleep=0.0, threshold=None, write=True):
    a = argparse.Namespace(provider=strategy, data=data, limit=limit, sleep=sleep)

    rows = [json.loads(l) for l in open(a.data, encoding="utf-8")]
    if a.limit:
        rows = rows[:a.limit]
    agent = IntakeAgent(strategy=a.provider, threshold=threshold, interactive=False, fallback=False, log_teacher=False)
    escalated = 0
    conn = service.connect(":memory:")

    type_ok = 0
    conf = collections.Counter()                  # (gold, pred) colour pairs
    field_ok = collections.Counter(); field_n = collections.Counter()
    setc = {k: [0, 0, 0] for k in ("flags", "needs")}
    miss_ok = miss_n = 0
    gold_case_of, pred_case_of = {}, {}
    resolved_ok = resolved_n = 0
    preds = []
    t0 = time.time()

    errors = 0
    for i, r in enumerate(rows, 1):
        try:
            res = service.process_message(conn, agent, r["text"], r["channel"], r["timestamp"])
        except Exception as err:   # one failed API call must not kill the whole run -> counted as wrong
            errors += 1
            print(f"  ! {r['msg_id']} failed: {str(err)[:150]}", flush=True)
            preds.append({"msg_id": r["msg_id"], "error": str(err)[:300]})
            if r["gt_message_type"] == "help_request":
                conf[(r["gt_priority"], "error")] += 1
                miss_n += 1
            if a.sleep:
                time.sleep(a.sleep)
            continue
        e = res["extraction"]
        escalated += bool(res.get("escalated"))
        preds.append({"msg_id": r["msg_id"], **res})
        gtype = "help_request" if r["gt_message_type"].startswith("help_request") else r["gt_message_type"]
        type_ok += e["message_type"] == gtype

        if gtype == "help_request":
            ex = Extraction.model_validate(e)
            pc, _ = priority(ex)
            if r["gt_message_type"] == "help_request":        # score extraction on originals only
                conf[(r["gt_priority"], pc)] += 1
                for f, g, p in [("area", r["gt_area"], ex.area), ("adults", r["gt_adults"], ex.adults),
                                ("water_level", r["gt_water_level"], ex.water_level.value if ex.water_level else None),
                                ("children_ages", sorted(r["gt_children_ages"]), sorted(ex.children_ages)),
                                ("elderly_ages", sorted(r["gt_elderly_ages"]), sorted(ex.elderly_ages))]:
                    if f in ("area", "adults", "water_level") and g is None:
                        continue
                    same = (len(g) == len(p) and all(abs(x - y) <= 0.1 for x, y in zip(g, p))) if isinstance(g, list) else g == p
                    field_n[f] += 1; field_ok[f] += same
                for k in setc:
                    tp, fp, fn = prf({x if isinstance(x, str) else x.value for x in getattr(ex, k)}, set(r[f"gt_{k}"]))
                    setc[k][0] += tp; setc[k][1] += fp; setc[k][2] += fn
                miss_n += 1; miss_ok += set(missing_fields(ex)) == set(r["gt_missing_fields"])
            if res["case_id"]:
                gold_case_of[r["msg_id"]] = r["gt_case_id"]; pred_case_of[r["msg_id"]] = res["case_id"]
        if gtype == "status_update_resolved":
            resolved_n += 1; resolved_ok += res["action"] == "resolved"
        if a.sleep:
            time.sleep(a.sleep)
        if i % 20 == 0:
            print(f"  {i}/{len(rows)} processed", flush=True)

    # duplicate detection: pairwise precision/recall over messages
    ids = list(gold_case_of)
    tp = fp = fn = 0
    for x in range(len(ids)):
        for y in range(x + 1, len(ids)):
            g = gold_case_of[ids[x]] == gold_case_of[ids[y]]
            p = pred_case_of[ids[x]] == pred_case_of[ids[y]]
            tp += g and p; fp += p and not g; fn += g and not p
    n_col = sum(conf.values())
    col_acc = sum(v for (g, p), v in conf.items() if g == p) / max(n_col, 1)
    red_total = sum(v for (g, _), v in conf.items() if g == "red")
    red_hit = conf[("red", "red")]
    f1 = lambda t, f, n: (2 * t / (2 * t + f + n)) if t else 0.0

    report = {
        "strategy": a.provider, "messages": len(rows), "seconds": round(time.time() - t0, 1),
        "escalated_to_llm": escalated,
        "failed_messages": errors,
        "message_type_accuracy": round(type_ok / len(rows), 3),
        "priority_accuracy": round(col_acc, 3),
        "red_recall": round(red_hit / max(red_total, 1), 3),
        "field_accuracy": {k: round(field_ok[k] / field_n[k], 3) for k in field_n},
        "flags_f1": round(f1(*setc["flags"]), 3), "needs_f1": round(f1(*setc["needs"]), 3),
        "missing_fields_exact": round(miss_ok / max(miss_n, 1), 3),
        "duplicate_precision": round(tp / max(tp + fp, 1), 3), "duplicate_recall": round(tp / max(tp + fn, 1), 3),
        "resolved_closed": f"{resolved_ok}/{resolved_n}",
        "final_stats": service.stats(conn),
    }
    out = ROOT / "05_evaluation" / "reports"
    tag = f"{a.provider}_{Path(a.data).stem}"
    if not write:
        return report
    out.mkdir(exist_ok=True)
    (out / f"predictions_{tag}.jsonl").write_text("\n".join(json.dumps(p, ensure_ascii=False) for p in preds), encoding="utf-8")
    md = [f"# Evaluation report — strategy: {a.provider} — data: {Path(a.data).name}", "", "| metric | value |", "|---|---|"]
    for k, v in report.items():
        if k not in ("field_accuracy", "final_stats"):
            md.append(f"| {k} | {v} |")
    md += ["", "## Field accuracy", "", "| field | accuracy |", "|---|---|"] + [f"| {k} | {v} |" for k, v in report["field_accuracy"].items()]
    md += ["", "## Priority confusion (rows = gold, cols = predicted)", "", "| gold \\ pred | " + " | ".join(COLORS) + " |", "|---" * 5 + "|"]
    md += [f"| {g} | " + " | ".join(str(conf[(g, p)]) for p in COLORS) + " |" for g in COLORS]
    (out / f"report_{tag}.md").write_text("\n".join(md), encoding="utf-8")
    return report


def compare():
    keys = ["message_type_accuracy", "priority_accuracy", "red_recall", "flags_f1", "needs_f1", "missing_fields_exact",
            "duplicate_precision", "duplicate_recall", "escalated_to_llm"]
    sets = {"template (200)": ROOT / "05_evaluation/data/flood_messages.jsonl", "hard (30)": ROOT / "05_evaluation/data/hard_messages.jsonl"}
    res = {(st, n): run(st, str(p)) for st in ("rules", "own") for n, p in sets.items()}
    cols = list(res)
    lines = ["| metric | " + " | ".join(f"{s} · {n}" for s, n in cols) + " |", "|---" * (len(cols) + 1) + "|"]
    lines += [f"| {k} | " + " | ".join(str(res[c][k]) for c in cols) + " |" for k in keys]
    table = "\n".join(lines)
    (ROOT / "05_evaluation" / "reports" / "comparison.md").write_text("# rules vs own model\n\n" + table + "\n", encoding="utf-8")
    print(table)


if __name__ == "__main__":
    main()

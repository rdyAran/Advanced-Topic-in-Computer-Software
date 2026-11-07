"""A1 — measure the AI on a NEW test set written by people outside the team (never used to tune anything).

  1. copy fresh_test_template.csv, let 2-3 people who did NOT build the system write 50-100 messages and their answers
  2. run (inside the agent container, so the real WangchanBERTa model is used):
       docker compose cp my_fresh_test.csv agent:/srv/04_flood_nlp_model/eval/my_fresh_test.csv
       docker compose exec agent python /srv/04_flood_nlp_model/eval/eval_fresh.py /srv/04_flood_nlp_model/eval/my_fresh_test.csv
     add --strategy hybrid to include the LLM step (uses quota)
Prints a table for the slides and writes <file>_errors.csv (every miss, worst first).
"""
import argparse, os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in ("common", "03_intake_ai_agent", "04_flood_nlp_model"):
    sys.path.insert(0, str(ROOT / p))
sys.path.insert(0, str(HERE))
from evalutil import load_rows, write_csv, md_table, PRIO_RANK  # noqa: E402


def score(rows, preds) -> dict:
    n = len(rows)
    help_rows = [(r, p) for r, p in zip(rows, preds) if r["message_type"] == "help_request"]
    type_ok = sum(r["message_type"] == p["message_type"] for r, p in zip(rows, preds))
    with_prio = [(r, p) for r, p in help_rows if r.get("priority")]
    red_true = [p for r, p in with_prio if r["priority"] == "red"]
    red_pred = [r for r, p in with_prio if p["priority"] == "red"]
    under = [1 for r, p in with_prio if PRIO_RANK.get(p["priority"], 9) > PRIO_RANK[r["priority"]]]
    tp = fp = fn = 0
    for r, p in help_rows:
        a, b = set(r.get("flags") or []), set(p["flags"])
        tp += len(a & b); fp += len(b - a); fn += len(a - b)
    help_found = sum(p["message_type"] == "help_request" for r, p in help_rows)
    return {"n": n, "type_acc": type_ok / n if n else None, "help_recall": help_found / len(help_rows) if help_rows else None,
            "priority_acc": sum(r["priority"] == p["priority"] for r, p in with_prio) / len(with_prio) if with_prio else None,
            "red_recall": sum(p["priority"] == "red" for p in red_true) / len(red_true) if red_true else None,
            "red_precision": sum(r["priority"] == "red" for r in red_pred) / len(red_pred) if red_pred else None,
            "under_triage": sum(under), "flags_f1": 2 * tp / (2 * tp + fp + fn) if (tp + fp + fn) else None,
            "n_red": len(red_true)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--strategy", default="own", help="own (our model only, default) | hybrid (+LLM when unsure)")
    a = ap.parse_args()
    from agent.router import IntakeAgent
    from floodcommon.triage import priority
    agent = IntakeAgent(strategy=a.strategy, log_teacher=False)
    rows = [r for r in load_rows(a.csv) if (r.get("text") or "").strip() and not (r.get("writer") or "").startswith("ตัวอย่าง")]
    preds, errs = [], []
    for r in rows:
        e = agent.run(r["text"])
        pr = priority(e)[0] if e.message_type.value == "help_request" else None
        p = {"message_type": e.message_type.value, "priority": pr, "flags": [f.value for f in e.flags], "provider": agent.last.get("provider_used")}
        preds.append(p)
        bad = []
        if p["message_type"] != r["message_type"]:
            bad.append("type")
        if r.get("priority") and r["message_type"] == "help_request" and p["priority"] != r["priority"]:
            bad.append("UNDER" if PRIO_RANK.get(p["priority"], 9) > PRIO_RANK[r["priority"]] else "over")
        if bad:
            errs.append({**r, "pred_type": p["message_type"], "pred_priority": p["priority"], "pred_flags": p["flags"],
                         "error": "+".join(bad), "provider": p["provider"]})
    m = score(rows, preds)
    f = lambda x: "—" if x is None else (f"{x:.1%}" if isinstance(x, float) else x)
    print(f"\nFresh test set: {m['n']} messages (red {m['n_red']}) · model: {agent.describe().get('own_model')} · strategy {a.strategy}\n")
    print(md_table([["ประเภทข้อความถูก", f(m["type_acc"])], ["เจอคำขอความช่วยเหลือ (recall)", f(m["help_recall"])],
                    ["สีถูก", f(m["priority_acc"])], ["จับเคสแดงได้ (recall)", f(m["red_recall"])],
                    ["แดงที่ทายถูก (precision)", f(m["red_precision"])], ["ให้สีต่ำกว่าจริง (เคส)", m["under_triage"]],
                    ["กลุ่มเปราะบาง F1", f(m["flags_f1"])]], ["ตัวชี้วัด", "ผล"]))
    if m["n_red"] < 15:
        print(f"\n⚠️ มีเคสแดงแค่ {m['n_red']} เคส — ตัวเลข red recall ยังแกว่งมาก ควรมีอย่างน้อย 15-20 เคส")
    errs.sort(key=lambda r: ("UNDER" not in r["error"], r["error"]))
    out = Path(a.csv).with_name(Path(a.csv).stem + "_errors.csv")
    write_csv(out, errs, ["error", "text", "message_type", "pred_type", "priority", "pred_priority", "flags", "pred_flags", "writer", "provider"])
    print(f"\nข้อผิดพลาด {len(errs)} ข้อ -> {out}  (UNDER = ให้สีต่ำกว่าจริง อันตรายที่สุด ดูก่อน)")


if __name__ == "__main__":
    main()

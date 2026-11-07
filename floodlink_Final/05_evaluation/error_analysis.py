"""Show every message the model gets wrong (default: DEV set, own model) — use this while tuning.
    python 05_evaluation/error_analysis.py [--data 05_evaluation/data/dev_messages.jsonl] [--strategy own]
"""
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
for _p in ["common", "03_intake_ai_agent", "04_flood_nlp_model"]:
    sys.path.insert(0, str(ROOT / _p))
from agent.router import IntakeAgent                  # noqa: E402
from floodcommon.triage import priority               # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--data", default=str(ROOT / "05_evaluation/data/dev_messages.jsonl"))
ap.add_argument("--strategy", default="own")
a = ap.parse_args()
agent = IntakeAgent(strategy=a.strategy, log_teacher=False)
n = ok_type = ok_col = n_help = red = red_hit = 0
for l in open(a.data, encoding="utf-8"):
    r = json.loads(l); n += 1
    e = agent.run(r["text"]); conf = agent.last.get("confidence")
    g = r["gt_message_type"].replace("_duplicate", "")
    problems = []
    if e.message_type.value != g:
        problems.append(f"type {e.message_type.value} (gold {g})")
    else:
        ok_type += 1
    if r["gt_message_type"] == "help_request":
        n_help += 1
        c = priority(e)[0]; ok_col += c == r["gt_priority"]
        red += r["gt_priority"] == "red"; red_hit += r["gt_priority"] == "red" and c == "red"
        if c != r["gt_priority"]: problems.append(f"colour {c} (gold {r['gt_priority']})")
        for k in ("flags", "needs"):
            p, gl = sorted(x.value for x in getattr(e, k)), sorted(r[f"gt_{k}"])
            if p != gl: problems.append(f"{k} {p} (gold {gl})")
        w = e.water_level.value if e.water_level else None
        if w != r["gt_water_level"]: problems.append(f"water {w} (gold {r['gt_water_level']})")
        for k in ("adults", "elderly_ages", "children_ages"):
            p, gl = getattr(e, k), r[f"gt_{k}"]
            if isinstance(gl, list): same = len(p) == len(gl) and all(abs(x - y) <= .1 for x, y in zip(sorted(p), sorted(gl)))
            else: same = gl is None or p == gl
            if not same: problems.append(f"{k} {p} (gold {gl})")
    if problems:
        print(f"{r['msg_id']} conf={conf}  {r['text'][:70]}\n      -> " + " | ".join(problems))
print(f"\ntype {ok_type}/{n} · colour {ok_col}/{n_help} · red {red_hit}/{red}")

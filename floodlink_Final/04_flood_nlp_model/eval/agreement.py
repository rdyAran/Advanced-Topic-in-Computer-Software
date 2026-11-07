"""A2 — are the labels trustworthy? Two people label the same sample separately; we measure how often they agree.

  python agreement.py sample ../realdata/data/test.jsonl --n 150      -> annotator_A.csv, annotator_B.csv (labels blank)
     (or any labels*.jsonl / floodlink_training.jsonl export). Give A to one person, B to another; they must not talk.
  python agreement.py score annotator_A.csv annotator_B.csv [--ai ../realdata/data/test.jsonl]
     -> Cohen's kappa per field (+ how often each person agrees with the AI-made labels)

Kappa: 1 = always agree, 0 = no better than chance.  >0.8 very good · 0.6-0.8 good · <0.6 the label guide is unclear.
"""
import argparse, random, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evalutil import load_rows, write_csv, md_table  # noqa: E402

FIELDS = ["message_type", "priority", "water_level", "flags", "needs"]
FLAGS = ["bedridden", "dialysis", "heart", "pregnant", "injured", "disabled_blind", "wheelchair", "in_labor", "sick_now",
         "chronic_illness", "cannot_swim"]


def kappa(a: list, b: list) -> float | None:
    pairs = [(x or "-", y or "-") for x, y in zip(a, b)]
    if not pairs:
        return None
    po = sum(x == y for x, y in pairs) / len(pairs)
    ca, cb, n = Counter(x for x, _ in pairs), Counter(y for _, y in pairs), len(pairs)
    pe = sum(ca[k] / n * cb[k] / n for k in set(ca) | set(cb))
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def compare(A, B):
    out = []
    for f in ("message_type", "priority", "water_level"):
        a, b = [r.get(f) for r in A], [r.get(f) for r in B]
        out.append([f, f"{sum((x or '-') == (y or '-') for x, y in zip(a, b)) / len(a):.0%}", f"{kappa(a, b):.2f}"])
    for fl in FLAGS:
        a, b = [fl in (r.get("flags") or []) for r in A], [fl in (r.get("flags") or []) for r in B]
        if any(a) or any(b):
            out.append([f"flag:{fl}", f"{sum(x == y for x, y in zip(a, b)) / len(a):.0%}", f"{kappa(a, b):.2f}"])
    return out


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample"); s.add_argument("src"); s.add_argument("--n", type=int, default=150); s.add_argument("--seed", type=int, default=7)
    c = sub.add_parser("score"); c.add_argument("a"); c.add_argument("b"); c.add_argument("--ai")
    a = ap.parse_args()
    if a.cmd == "sample":
        rows = [r for r in load_rows(a.src) if (r.get("text") or "").strip()]
        random.Random(a.seed).shuffle(rows)
        pick = [{"id": r.get("id") or r.get("row_id") or i, "text": r["text"]} for i, r in enumerate(rows[:a.n])]
        for who in ("A", "B"):
            write_csv(f"annotator_{who}.csv", [{**r, **{f: "" for f in FIELDS}} for r in pick], ["id", "text"] + FIELDS)
        print(f"wrote annotator_A.csv / annotator_B.csv ({len(pick)} rows) — ใช้ LABEL_GUIDE.md เป็นคู่มือ, ห้ามดูของอีกคน")
        return
    A = {str(r["id"]): r for r in load_rows(a.a)}
    B = {str(r["id"]): r for r in load_rows(a.b)}
    ids = [i for i in A if i in B and (A[i].get("message_type") and B[i].get("message_type"))]
    print(f"\nแถวที่ทั้งสองคนติดป้ายแล้ว: {len(ids)}\n")
    print(md_table(compare([A[i] for i in ids], [B[i] for i in ids]), ["ช่อง", "ตรงกัน", "kappa"]))
    if a.ai:
        AI = {str(r.get("id") or r.get("row_id")): r for r in load_rows(a.ai)}
        both = [i for i in ids if i in AI]
        for who, X in (("A", A), ("B", B)):
            print(f"\nคน {who} เทียบกับป้ายเดิม (AI) — {len(both)} แถว\n")
            print(md_table(compare([X[i] for i in both], [AI[i] for i in both])[:3], ["ช่อง", "ตรงกัน", "kappa"]))
    dis = [i for i in ids if A[i].get("priority") != B[i].get("priority")]
    if dis:
        write_csv("disagreements.csv", [{"id": i, "text": A[i]["text"], "A": A[i].get("priority"), "B": B[i].get("priority")} for i in dis],
                  ["id", "text", "A", "B"])
        print(f"\nสีไม่ตรงกัน {len(dis)} แถว -> disagreements.csv (คุยกันแล้วปรับ LABEL_GUIDE ให้ชัดขึ้น)")


if __name__ == "__main__":
    main()

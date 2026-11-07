"""A6 — how often is "merge as duplicate" right? A wrong merge hides a real household inside another case.

Inside the api container (it has the database):
  docker compose exec api python -m api.tools.eval_merge sample --n 60
      -> /data/merge_pairs.csv : pairs of reports from the database with their similarity score (blank 'same' column)
  copy it out, fill 'same' with 1 (same household) or 0, copy it back:
      docker compose cp api:/data/merge_pairs.csv .      ...edit...      docker compose cp merge_pairs.csv api:/data/merge_pairs.csv
  docker compose exec api python -m api.tools.eval_merge score
      -> precision / recall / wrong merges for each threshold + the suggested DUP_THRESHOLD / DUP_SUGGEST_THRESHOLD
Your own pairs (columns text_a,text_b,same) work too: rows without a score are read by the AI agent first.
"""
import argparse, csv, json, os, random
from floodcommon.schemas import Extraction
from .. import service
from ..verify import CaseView, match_score, DUP_THRESHOLD, SUGGEST_THRESHOLD

PATH = os.getenv("MERGE_PAIRS", "/data/merge_pairs.csv")


def _view(cid, text, e: Extraction) -> CaseView:
    return CaseView(case_id=cid, area=e.area, text=text, adults=e.adults, elderly_ages=e.elderly_ages, children_ages=e.children_ages,
                    flags=[f.value for f in e.flags], house_no=e.house_no, street=e.street)


def sample(conn, n: int, path: str):
    msgs = []
    for r in conn.execute("SELECT id, text, extraction FROM messages WHERE message_type='help_request' AND action IN ('created','merged')"):
        try:
            msgs.append((r["id"], r["text"], Extraction.model_validate(json.loads(r["extraction"]))))
        except Exception:
            pass
    pairs = []
    for i, (ia, ta, ea) in enumerate(msgs):
        for ib, tb, eb in msgs[i + 1:]:
            s = match_score(ea, ta, _view(ib, tb, eb))
            if s >= 0.2:
                pairs.append((s, ia, ta, ib, tb))
    random.Random(1).shuffle(pairs)
    bands = [(0.2, 0.4), (0.4, 0.55), (0.55, 0.7), (0.7, 0.85), (0.85, 9)]       # spread over the score range
    pick = []
    for lo, hi in bands:
        pick += [p for p in pairs if lo <= p[0] < hi][: max(n // len(bands), 1)]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(["pair_id", "score", "text_a", "text_b", "same"])
        for k, (s, ia, ta, ib, tb) in enumerate(sorted(pick, key=lambda p: -p[0])):
            w.writerow([f"{ia}|{ib}", round(s, 3), ta, tb, ""])
    print(f"wrote {len(pick)} pairs -> {path}  (fill 'same' with 1 or 0)")


def score(path: str):
    rows = [r for r in csv.DictReader(open(path, encoding="utf-8-sig")) if (r.get("same") or "").strip() in ("0", "1")]
    need = [r for r in rows if not (r.get("score") or "").strip()]
    if need:
        from ..agent_client import AgentClient
        ag = AgentClient()
        for r in need:
            ea, eb = ag.run(r["text_a"]), ag.run(r["text_b"])
            r["score"] = match_score(ea, r["text_a"], _view("B", r["text_b"], eb))
    data = [(float(r["score"]), r["same"].strip() == "1") for r in rows]
    if not data:
        print("ยังไม่มีแถวที่กรอก same = 0/1"); return
    print(f"\n{len(data)} คู่ · บ้านเดียวกันจริง {sum(s for _, s in data)} คู่\n")
    print("| เกณฑ์ | รวมอัตโนมัติ | รวมถูก (precision) | เจอคู่ซ้ำ (recall) | รวมผิด (บ้านคนละหลัง) |\n|---|---|---|---|---|")
    best = None
    for th in [0.4, 0.5, 0.55, 0.6, 0.7, 0.8, 0.9]:
        m = [(sc, same) for sc, same in data if sc >= th]
        tp = sum(s for _, s in m); wrong = len(m) - tp; pos = sum(s for _, s in data)
        prec = tp / len(m) if m else 1.0; rec = tp / pos if pos else 0.0
        print(f"| {th} | {len(m)} | {prec:.0%} | {rec:.0%} | {wrong} |")
        if best is None and prec >= 0.98:
            best = th
    print(f"\nตอนนี้: DUP_THRESHOLD={DUP_THRESHOLD} (รวมเอง) · DUP_SUGGEST_THRESHOLD={SUGGEST_THRESHOLD} (ให้เจ้าหน้าที่ตัดสิน)")
    print(f"แนะนำ DUP_THRESHOLD={best if best else 'สูงกว่า 0.9'} = ต่ำที่สุดที่รวมผิด ≤2% — คู่ที่ต่ำกว่านั้นให้เจ้าหน้าที่ตัดสิน")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["sample", "score"]); ap.add_argument("--n", type=int, default=60); ap.add_argument("--file", default=PATH)
    a = ap.parse_args()
    if a.cmd == "sample":
        sample(service.connect(os.getenv("DB_PATH", "floodlink.db")), a.n, a.file)
    else:
        score(a.file)


if __name__ == "__main__":
    main()

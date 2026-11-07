"""labels.jsonl + to_label.csv -> train / dev / test splits + a review sheet for the test set.

  python build_dataset.py                                   # after label_groq.py
  python build_dataset.py --reviewed data/review_test.csv   # after the team has checked the test set

Rules:
  * the TEST set is frozen by row id in data/test_ids.txt the first time — never re-drawn, never trained on
  * near-duplicate shares were already merged by prepare.py (one row per dup group) so copies cannot leak across splits
  * person names the labeller found are masked once more before anything is written
"""
import argparse, csv, json, random, re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = HERE / "data"
MIN = {"bedridden": 150, "dialysis": 100, "pregnant": 80, "in_labor": 30, "injured": 80, "sick_now": 80,
       "status_update_resolved": 150, "hazard_report": 80, "donation_offer": 80, "irrelevant": 300}
REVIEW_COLS = ["row_id", "text", "message_type", "flags", "needs", "water_level", "lost_contact", "insufficient_info",
               "priority", "priority_rules", "label_confidence", "reviewed", "review_note"]
SEV = {"knee": 1, "waist": 2, "chest": 3, "floor1": 3, "floor2": 4, "roof": 5}


def rule_priority(l: dict) -> str:
    """Same logic as floodcommon.triage.priority, extended with the flags found in real data (see LABEL_GUIDE)."""
    if l["message_type"] != "help_request":
        return "none"
    f, sev = set(l["flags"]), SEV.get(l.get("water_level"), -1)
    kids = l.get("children_ages") or []
    if f & {"dialysis", "heart", "injured", "in_labor", "sick_now"} or any(a < 1 for a in kids) or sev >= 5:
        return "red"
    if ("bedridden" in f and sev >= 4) or ("pregnant" in f and sev >= 3):
        return "red"
    if f & {"bedridden", "wheelchair", "disabled_blind", "pregnant"} or any(a >= 70 for a in l.get("elderly_ages") or []) \
            or any(a < 6 for a in kids) or sev >= 4:
        return "orange"
    if sev >= 2 or (l.get("days_trapped") or 0) >= 2 or {"food", "water", "medicine"} & set(l["needs"]):
        return "yellow"
    return "green"


ADDRESS = re.compile(r"บ้านเลขที่|เลขที่\s*\d|ซอย|ซ\.|ถนน|ถ\.|หมู่\s*\d|ม\.\s*\d|\d+/\d+|maps|พิกัด|\d\.\d{4,}|แมนชั่น|อพาร์ท|หอพัก|หมู่บ้าน|ชุมชน|มัสยิด|วัด")


def autofix(l: dict, text: str) -> dict:
    """Fix the LLM label errors that the test-set review showed are systematic (rows Claude did not relabel)."""
    l = dict(l)
    if l.get("message_type") == "help_request":
        if l.get("insufficient_info") and ADDRESS.search(text):
            l["insufficient_info"] = False                             # has an address -> the team can go
        if l.get("water_level") == "floor2" and re.search(r"(?:ติด|อยู่|ยุ)\S{0,6}ชั้น\s*(?:2|สอง)", text) \
                and not re.search(r"น้ำ\S{0,10}ชั้น\s*(?:2|สอง)", text):
            l["water_level"] = None                                    # "ติดอยู่ชั้น 2" = where people are, not the water
        if l.get("priority") not in ("red", "orange", "yellow", "green"):
            l["priority"] = rule_priority(l)                           # help requests must have a colour
    return l


def mask(text: str, names: list[str]) -> str:
    for n in sorted(set(names), key=len, reverse=True):
        if len(n) >= 2 and n not in ("<NAME>",):
            text = text.replace(n, "<NAME>")
    return text


def strat_key(l):
    if l["message_type"] != "help_request":
        return l["message_type"]
    rare = [f for f in ("dialysis", "in_labor", "injured", "pregnant", "bedridden", "sick_now") if f in l["flags"]]
    return "help:" + (rare[0] if rare else rule_priority(l))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reviewed", help="review_test.csv edited by the team")
    ap.add_argument("--freeze-now", action="store_true",
                    help="lock the test set from the rows labelled so far (labelling may continue; new rows go to train/dev)")
    ap.add_argument("--test", type=int, default=600)
    ap.add_argument("--dev", type=float, default=0.15)   # bigger dev = steadier thresholds
    a = ap.parse_args()

    texts = {r["row_id"]: r for r in csv.DictReader(open(D / "to_label.csv", encoding="utf-8-sig"))}
    labels = {}
    for fp in sorted(D.glob("labels*.jsonl")):                        # labels.jsonl + parallel shards
        for line in open(fp, encoding="utf-8"):
            if line.strip():
                try:
                    l = json.loads(line)
                except json.JSONDecodeError:
                    continue                                          # half-written line after Ctrl+C
                labels[l["id"]] = l
    rows = []
    for rid, l in labels.items():
        if rid not in texts:
            continue
        if not str(l.get("label_model", "")).startswith("claude"):
            l = autofix(l, texts[rid]["text"])                         # systematic LLM mistakes found in the test review
        names = l.get("person_names", [])
        l = {k: v for k, v in l.items() if k != "person_names"}       # names are only used for masking, never stored
        rows.append({**l, "row_id": rid, "text": mask(texts[rid]["text"], names),
                     "dup_count": int(texts[rid]["dup_count"]), "priority_rules": rule_priority(l)})
    print(f"labelled rows: {len(rows)} / {len(texts)}")

    # ---- frozen test set ----
    tid_file = D / "test_ids.txt"
    coverage = len(rows) / max(len(texts), 1)
    if tid_file.exists():
        test_ids = set(tid_file.read_text().split())
    else:
        n_test = min(a.test, int(len(rows) * 0.15))
        rnd = random.Random(7)
        by = {}
        for r in rows:
            by.setdefault(strat_key(r), []).append(r["row_id"])
        test_ids = set()
        for k, ids in sorted(by.items()):
            rnd.shuffle(ids)
            take = round(len(ids) * n_test / len(rows)) if len(ids) >= 5 else 0
            if k.startswith("help:") and k.split(":")[1] in MIN:      # over-sample rare classes into the test set (min 20 each)
                take = max(take, min(20, len(ids) // 3))
            test_ids.update(ids[:take])
        if coverage >= 0.9 or a.freeze_now:
            tid_file.write_text("\n".join(sorted(test_ids)))
            print(f"froze {len(test_ids)} test ids -> {tid_file.name}")
        else:                                                         # don't freeze a test set drawn from a partial sample
            print(f"⚠️ ติดป้ายแล้วแค่ {coverage:.0%} — ชุดทดสอบนี้ชั่วคราว จะถูกล็อกเมื่อติดป้ายครบ ≥90%")

    if a.reviewed:
        rev = {r["row_id"]: r for r in csv.DictReader(open(a.reviewed, encoding="utf-8-sig")) if r.get("reviewed", "").strip() == "1"}
        for r in rows:
            if r["row_id"] in rev:
                v = rev[r["row_id"]]
                r.update({"message_type": v["message_type"], "flags": [x for x in v["flags"].split("|") if x],
                          "needs": [x for x in v["needs"].split("|") if x], "water_level": v["water_level"] or None,
                          "lost_contact": v["lost_contact"] in ("1", "True", "true"),
                          "insufficient_info": v["insufficient_info"] in ("1", "True", "true"), "priority": v["priority"],
                          "human_reviewed": True})
                r["priority_rules"] = rule_priority(r)
        print(f"applied {len(rev)} human-reviewed test labels")

    test = [r for r in rows if r["row_id"] in test_ids]
    rest = [r for r in rows if r["row_id"] not in test_ids]
    random.Random(11).shuffle(rest)
    n_dev = int(len(rest) * a.dev)
    dev, train = rest[:n_dev], rest[n_dev:]
    # synthetic examples for rare classes (make_synthetic.py) -> TRAIN ONLY, never dev/test
    syn = []
    for fp in sorted(D.glob("synthetic*.jsonl")):
        for line in open(fp, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                r.setdefault("dup_count", 1); r["priority_rules"] = rule_priority(r)
                syn.append(r)
    train = train + syn
    if syn:
        print(f"+ synthetic {len(syn)} rows (train only)")
    for name, part in (("train", train), ("dev", dev), ("test", test)):
        with open(D / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for r in part:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    review = D / "review_test.csv"
    stale = False
    if review.exists():
        old_rows = list(csv.DictReader(open(review, encoding="utf-8-sig")))
        started = any(r.get("reviewed", "").strip() for r in old_rows)
        same = {r["row_id"] for r in old_rows} == {r["row_id"] for r in test}
        if started and not same:
            print(f"⚠️ {review.name} มีการตรวจแล้วแต่แถวไม่ตรงกับชุดทดสอบปัจจุบัน — ไม่เขียนทับ เช็กก่อนใช้")
        elif started:
            print(f"มี {review.name} ที่เริ่มตรวจแล้ว — ไม่เขียนทับ")
        stale = not started                    # nobody has reviewed yet -> safe to rebuild from the current test set
    if not review.exists() or stale:
        with open(review, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, REVIEW_COLS); w.writeheader()
            for r in sorted(test, key=lambda r: (r.get("confidence") or 1)):   # least confident first
                w.writerow({"row_id": r["row_id"], "text": r["text"], "message_type": r["message_type"],
                            "flags": "|".join(r["flags"]), "needs": "|".join(r["needs"]), "water_level": r.get("water_level") or "",
                            "lost_contact": int(bool(r.get("lost_contact"))), "insufficient_info": int(bool(r.get("insufficient_info"))),
                            "priority": r["priority"], "priority_rules": r["priority_rules"],
                            "label_confidence": r.get("confidence"), "reviewed": "", "review_note": ""})

    # ---- report ----
    c_type = Counter(r["message_type"] for r in rows)
    c_flag = Counter(f for r in rows for f in r["flags"])
    c_prio = Counter(r["priority"] for r in rows if r["message_type"] == "help_request")
    agree = [r["priority"] == r["priority_rules"] for r in rows if r["message_type"] == "help_request"]
    rep = {"rows": len(rows), "synthetic_in_train": len(syn), "train": len(train), "dev": len(dev), "test": len(test),
           "test_human_reviewed": sum(1 for r in test if r.get("human_reviewed")),
           "message_type": dict(c_type), "flags": dict(c_flag), "needs": dict(Counter(n for r in rows for n in r["needs"])),
           "priority_llm": dict(c_prio), "llm_vs_rules_priority_agreement": round(sum(agree) / len(agree), 3) if agree else None,
           "below_minimum": {k: f"{(c_flag.get(k) or c_type.get(k) or 0)}/{v}" for k, v in MIN.items() if (c_flag.get(k) or c_type.get(k) or 0) < v}}
    (D / "dataset_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

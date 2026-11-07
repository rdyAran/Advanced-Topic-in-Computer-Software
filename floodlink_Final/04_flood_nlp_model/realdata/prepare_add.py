"""Add a NEW raw comment dump to an existing data/to_label.csv without changing existing row ids or labels.

  python prepare_add.py raw_v2.txt            -> appends new unique rows to data/to_label.csv (backup kept)

* same parsing + anonymisation as prepare.py
* near-duplicates of EXISTING rows (any split, incl. the test set) are dropped -> no test leakage via re-shares
* new rows get ids after the current maximum, so labels*.jsonl / test_ids.txt / review_test.csv stay valid
"""
import csv, json, re, shutil, sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import prepare as P

D = HERE / "data"


def main(src, thr=0.85, tag="v2"):
    old = list(csv.DictReader(open(D / "to_label.csv", encoding="utf-8-sig")))
    cols = list(old[0].keys())
    new = P.parse(Path(src).read_text(encoding="utf-8"))
    authors = {r["author"] for r in new if r["author"]}
    pii = 0
    for r in new:
        r["text"], k = P.anonymise(r["text"], authors); pii += k
        r["chatter"] = P.is_chatter(r["text"])

    # cluster old + new together; a new row in a cluster that already has an old row is a duplicate
    texts = [r["text"] for r in old] + [r["text"] for r in new]
    groups = P.dup_groups(texts, thr)
    old_groups = set(groups[:len(old)])
    n0 = len(old)
    test_ids = set((D / "test_ids.txt").read_text().split()) if (D / "test_ids.txt").exists() else set()
    test_groups = {groups[i] for i, r in enumerate(old) if r["row_id"] in test_ids}

    next_id = max(int(r["row_id"][1:]) for r in old) + 1
    next_g = max(int(r["dup_group"][1:]) for r in old) + 1
    gmap, added, dup_old, dup_test, size = {}, [], 0, 0, Counter(groups[n0:])
    best = {}
    for j, r in enumerate(new):                     # keep the longest version of each new cluster
        g = groups[n0 + j]
        if g in old_groups:
            dup_old += 1; dup_test += g in test_groups; continue
        if g not in best or len(r["text"]) > len(new[best[g]]["text"]):
            best[g] = j
    for g, j in sorted(best.items(), key=lambda kv: kv[1]):
        r = new[j]
        if g not in gmap:
            gmap[g] = f"G{next_g:05d}"; next_g += 1
        added.append({"row_id": f"R{next_id:05d}", "dup_group": gmap[g], "dup_count": size[g], "has_image": r["has_image"],
                      "chatter": r["chatter"], "text": r["text"], **({"batch": tag} if "batch" in cols else {})})
        next_id += 1

    shutil.copy(D / "to_label.csv", D / f"to_label.before_{tag}.csv")
    with open(D / "to_label.csv", "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore")
        for r in added:
            w.writerow(r)
    rep = {"parsed": len(new), "duplicate_of_existing": dup_old, "of_which_test_set": dup_test,
           "duplicate_within_new": len(new) - dup_old - len(added), "added": len(added),
           "added_chatter": sum(1 for r in added if r["chatter"]), "pii_replacements": pii,
           "new_id_range": f"{added[0]['row_id']}..{added[-1]['row_id']}" if added else None, "total_rows_now": n0 + len(added)}
    (D / f"report_{tag}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return added


if __name__ == "__main__":
    main(sys.argv[1], tag=sys.argv[2] if len(sys.argv) > 2 else "v2")

"""A3 — does the test set contain the same (or almost the same) message as train? Re-posts are common in floods,
so an exam question may already be in the textbook. Also checks that no synthetic row is in dev/test.

  python check_leakage.py ../realdata/data/train.jsonl ../realdata/data/test.jsonl [--dev ../realdata/data/dev.jsonl] [--write]
--write saves test_clean.jsonl without the leaked rows (measure on both and report both).
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evalutil import load_rows, norm_text  # noqa: E402

NEAR = 0.8


def grams(t: str, n: int = 5) -> set:
    return {t[i:i + n] for i in range(max(len(t) - n + 1, 1))}


def leaks(train, test):
    exact = {norm_text(r["text"]): r for r in train}
    tg = [(grams(norm_text(r["text"])), len(norm_text(r["text"])), r) for r in train]
    out = []
    for r in test:
        t = norm_text(r["text"])
        if t in exact:
            out.append((r, exact[t], 1.0)); continue
        g, L = grams(t), len(t)
        best, bs = None, 0.0
        for g2, L2, r2 in tg:
            if not L or min(L, L2) / max(L, L2) < NEAR:          # very different length cannot be 80% the same
                continue
            j = len(g & g2) / len(g | g2)
            if j > bs:
                best, bs = r2, j
        if bs >= NEAR:
            out.append((r, best, bs))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("train"); ap.add_argument("test"); ap.add_argument("--dev"); ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    train, test = load_rows(a.train), load_rows(a.test)
    sets = [("test", test)] + ([("dev", load_rows(a.dev))] if a.dev else [])
    for name, rows in sets:
        syn = [r for r in rows if "synthetic" in str(r.get("source", "")) or str(r.get("id", "")).lower().startswith("syn")]
        L = leaks(train, rows)
        print(f"\n{name}: {len(rows)} แถว · ซ้ำ/เกือบซ้ำกับ train {len(L)} แถว ({len(L) / max(len(rows), 1):.1%}) · ข้อมูลสังเคราะห์ {len(syn)} แถว")
        for r, r2, s in L[:10]:
            print(f"  {s:.2f}  test: {r['text'][:60]!r}\n        train: {r2['text'][:60]!r}")
        if a.write and name == "test":
            bad = {id(r) for r, _, _ in L} | {id(r) for r in syn}
            out = Path(a.test).with_name("test_clean.jsonl")
            out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows if id(r) not in bad), encoding="utf-8")
            print(f"  -> {out} ({len(rows) - len(bad)} แถว) วัดผลซ้ำบนไฟล์นี้แล้วรายงานทั้งสองตัวเลข")


if __name__ == "__main__":
    main()

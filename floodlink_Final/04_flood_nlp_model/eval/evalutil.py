"""Shared helpers for the evaluation tools (pure Python, no torch)."""
import csv, json, re
from pathlib import Path

PRIO_RANK = {"red": 0, "orange": 1, "yellow": 2, "green": 3}
LIST_FIELDS = ("flags", "needs")


def norm_text(t: str) -> str:
    """For duplicate checks: no spaces/punctuation, masked placeholders and digits unified."""
    t = re.sub(r"\[[^\]]{1,12}\d*\]", "#", t or "")
    t = re.sub(r"\d+", "0", t)
    return re.sub(r"[\s\W_]+", "", t.lower())


def load_rows(path) -> list[dict]:
    """.jsonl or .csv -> list of dicts; 'flags' / 'needs' in a CSV may be 'a,b' or 'a|b'."""
    path = Path(path)
    if path.suffix == ".jsonl":
        return [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    for r in rows:
        for k in LIST_FIELDS:
            if k in r:
                r[k] = [x.strip() for x in re.split(r"[,|;]", r[k] or "") if x.strip()]
        for k in ("water_level", "priority", "message_type"):
            if k in r:
                r[k] = (r[k] or "").strip() or None
    return rows


def write_csv(path, rows: list[dict], fields: list[str]):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (",".join(v) if isinstance(v, list) else v) for k, v in r.items()})


def md_table(rows: list[list], head: list[str]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    return "\n".join(out)

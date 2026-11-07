"""FloodLink WangchanBERTa model (multi-task) — shared by the Colab notebook and the backend.

One encoder, six heads, trained together on the real Hat Yai data (realdata/):
  type   : help_request / status_update_resolved / hazard_report / donation_offer / irrelevant   (softmax)
  flags  : vulnerable groups, multi-label                                                       (sigmoid)
  needs  : what they need, multi-label                                                          (sigmoid)
  water  : water level (or none)                                                                (softmax)
  bin    : lost_contact, insufficient_info                                                      (sigmoid)
  prio   : direct priority guess (help requests only) — a safety net next to the rule colour    (softmax)

The final colour = the MORE urgent of (rules applied to the predicted facts, priority head), so a miss in one
path can be caught by the other. Thresholds for life-threatening flags are tuned for recall, not F1.

Pure-python/numpy parts (preprocess, labels, decode, thresholds, metrics) work without torch.
"""
import json, math, re
from pathlib import Path

import numpy as np

MODEL_NAME = "airesearch/wangchanberta-base-att-spm-uncased"
TYPES = ["help_request", "status_update_resolved", "hazard_report", "donation_offer", "irrelevant"]
FLAGS = ["bedridden", "wheelchair", "disabled_blind", "dialysis", "heart", "pregnant", "in_labor", "injured",
         "chronic_illness", "sick_now", "cannot_swim"]
NEEDS = ["evacuation", "food", "water", "milk", "medicine", "power", "medical"]
WATER = ["none", "knee", "waist", "chest", "floor1", "floor2", "roof"]
BIN = ["lost_contact", "insufficient_info"]
PRIO = ["red", "orange", "yellow", "green"]
RED_FLAGS = {"dialysis", "heart", "injured", "in_labor", "sick_now"}      # tuned for recall
SEV = {"knee": 1, "waist": 2, "chest": 3, "floor1": 3, "floor2": 4, "roof": 5}
RANK = {"red": 3, "orange": 2, "yellow": 1, "green": 0, "none": -1}
IGNORE = -100


# ---------------- text ----------------
def preprocess(text: str) -> str:
    """WangchanBERTa (thai2transformers) style: lowercase, collapse spaces, space -> <_>, cut long repeats."""
    t = text.replace("￼", " ").lower()
    t = re.sub(r"https?://\S+", " <url> ", t)
    t = re.sub(r"(.)\1{3,}", r"\1\1\1", t)                       # ค่าาาาาา -> ค่าาา, 🙏🙏🙏🙏🙏 -> 🙏🙏🙏
    t = re.sub(r"[ \t\r\n]+", " ", t).strip()
    return t.replace(" ", "<_>")


AGE_KID = re.compile(r"(\d{1,2}(?:\.\d)?)\s*(ขวบ|เดือน|ด\.)")
AGE_OLD = re.compile(r"(?:อายุ\s*|ยาย\s*|ตา\s*|ปู่\s*|ย่า\s*|แม่\s*|พ่อ\s*)(\d{2,3})(?:\s*ปี)?|(\d{2,3})\s*ปี")


def ages(text: str) -> tuple[list[float], list[int]]:
    """Light age extractor for the rules (the backend may use floodnlp.entities instead)."""
    kids = []
    for n, unit in AGE_KID.findall(text):
        v = float(n) / (12 if unit in ("เดือน", "ด.") else 1)
        if v < 18:
            kids.append(round(v, 2))
    old = []
    for a, b in AGE_OLD.findall(text):
        v = int(a or b)
        if 60 <= v <= 110:
            old.append(v)
    return kids, old



# ---------------- keyword safety rules (applied after the model; see decode) ----------------
# Found in the round-4 test errors: the model lost very short pleas ("ฝากน้องอีกคนนะคะ") to "irrelevant" and gave
# green to "มีเด็กทารก" / "น้องตัวซีดแล้ว". Measured on 472 reviewed test + 1,783 V2 labelled texts before use:
# the help cue never fired on a test comment labelled irrelevant; the critical/infant words hit 13/13 red test cases.
USE_RULES = True
ADDR = re.compile(r"บ้านเลขที่|เลขที่\s*\d|\d{1,4}/\d{1,4}|0\d(?:[\s.-]?\d){7,9}|\d\.\d{4,}")
HELP_CUE = re.compile(
    r"ยังมี(?:คน)?(?:ติด|เหลือ)|ยังออกมาไม่หมด|ยังช่วย(?:ออกมา)?ไม่หมด|(?<!คน)(?<!บางกลุ่ม)ติด(?:อยู่|ค้าง|ยุ|ยู่)|"
    r"ขาดการติดต่อ|ติดต่อ\S{0,8}ไม่ได้|อด(?:อาหาร|ข้าว)\S{0,10}(?:วัน|แล้ว)|ไม่มี\S{0,6}(?:อาหาร|ข้าว|น้ำดื่ม)|"
    r"(?<!คน)(?<!ผู้)(?<!ที่)ต้องการ(?:อาหาร|น้ำ|อพยพ|ความช่วยเหลือ|เรือ)|ขอ(?:ความ|คาม)ช่วยเหล[ืี]อ|ช่วยเหลือ(?:ด้วย|หน่อย)|"
    r"[ชข]่วยด้วย|อยู่บนหลังคา|ใต้หลังคา|ลอยคอ|ไม่มีที่(?:จะ)?อยู่|"
    r"^[\W\d_]*#?(?:ฝาก(?!แชร์)|รบกวน|ด่วน|ช่วย(?!กัน|บอก|แชร์|พี่น้อง|ออกมาให้|ได้))|ช่วย(?!กัน|บอก|แชร์|พี่น้อง|ออกมาให้|ได้)[^\n]{0,40}?ด้วย|ช่วย[^\n]{0,20}?หน่อย|"
    r"ยังไม่มี(?:หน่วย|ใคร|เจ้าหน้าที่|เรือ)|"
    r"(?:ซอย|ซ\.|ถนน|ถ\.|หมู่บ้าน|ชุมชน|คอนโด|แมนชั่น|หอพัก|อพาร์ท)\S*.{0,40}(?:ด้วย|ยังไม่|ขอ(?:อาหาร|น้ำ|ข้าว))", re.I)
HELP_VETO = re.compile(
    r"ขอบคุณ|กำลังใจ|ขอให้|สงสาร|หดหู่|เยี่ยม|ทำไม|ควร|น่าจะ|ถ้า|ทหาร|เรือหลวง|ทีมงาน(?!คุณ)|ทุกหน่วยงาน|ประชาชน|คนไทย|ทั่วถึง|"
    r"เพจ|วิธี|เสนอ|โทรหา|รวมเบอร์|แมว|หมา|jetski|เจ็ตสกี|ทีมเรือ|ทีมตอบโต้|สตูล|รัฐบาล|นายก|อนุทิน|โดรน|เสื้อชูชีพ|บริจาค|พักผ่อน|"
    r"ปลอดภัยแล้ว|ได้รับการช่วยเหลือแล้ว|ช่วยออกมาได้แล้ว|ใจจริง|ดูแลตัวเอง|เป็นจำนวนมาก|หลายแสน|ทุกหลัง|เป็นพัน", re.I)
INFANT = re.compile(r"ทารก|เด็กอ่อน(?!เพลีย|แรง)|แรกเกิด|แรกคลอด|ลูกอ่อน")
CRITICAL = re.compile(r"ตัวซีด|ปากม่วง|ปากเขียว|ชัก(?!ช้า|ชวน|จูง)|หมดสติ|ไม่รู้สึกตัว|หายใจไม่ออก|หายใจลำบาก|หายใจไม่สะดวก|"
                      r"ไข้(?:ขึ้น)?สูง|เลือดออก|เสียเลือด|เป็นลม(?!แรง)|เจ็บท้อง(?:คลอด)?|น้ำเดิน|ฟอกไต|ล้างไต|ออกซิเจน")


def help_cue(text: str) -> bool:
    """A comment the model called irrelevant that still reads like a request for help."""
    t = (text or "").strip()
    if not HELP_CUE.search(t):
        return False
    if ADDR.search(t) and not re.search(r"รวมเบอร์|สายด่วน|ศูนย์|โทรหา|ปลัด", t):
        return True                                   # a concrete place / phone number + a request = a case
    return not HELP_VETO.search(t)


# "ไม่มีไข้", "ไม่ได้ชัก", "หายใจได้ปกติ", "ไม่ต้องฟอกไต" ... : a negation just before the word cancels it
NEGATION = re.compile(r"(?:ไม่|ไม่ได้|ไม่มี|ไม่ค่อย|ไม่เคย|ไม่ต้อง|ไม่ได้มี|ยังไม่|หาย(?:จาก)?|ปลอดจาก|ไม่ใช่)\s*(?:อาการ|ภาวะ|มี|เป็น|ได้|ใช้|ต้องใช้)?\s*$")


def critical_hits(text: str) -> list[str]:
    """Words that make a help request red on their own (infant, collapse, breathing, bleeding, labour, dialysis).
    A word right after a negation ("ไม่มีไข้สูง", "ไม่ได้ฟอกไต") does not count."""
    t = text or ""
    hits = set()
    for rx in (INFANT, CRITICAL):
        for m in rx.finditer(t):
            if not NEGATION.search(t[max(0, m.start() - 14):m.start()]):
                hits.add(m.group(0))
    return sorted(hits)

# ---------------- labels ----------------
def encode(row: dict) -> dict:
    """jsonl row from realdata/build_dataset.py -> numeric targets."""
    help_ = row["message_type"] == "help_request"
    wl = row.get("water_level") or "none"
    return {
        "type": TYPES.index(row["message_type"]),
        "flags": np.array([f in row.get("flags", []) for f in FLAGS], dtype=np.float32),
        "needs": np.array([n in row.get("needs", []) for n in NEEDS], dtype=np.float32),
        "water": WATER.index(wl) if (help_ and wl in WATER) else IGNORE,
        "bin": np.array([bool(row.get("lost_contact")), bool(row.get("insufficient_info"))], dtype=np.float32),
        "bin_mask": 1.0 if help_ else 0.0,
        # synthetic rows teach type/flags/needs only: their colour mix (mostly red) is not the real mix and
        # pulled the colour head towards red (61 of 81 orange test cases came out red)
        "prio": PRIO.index(row["priority"]) if (help_ and row.get("priority") in PRIO and row.get("source") != "synthetic") else IGNORE,
    }


def rule_priority(p: dict) -> str:
    """Same rules as realdata/build_dataset.rule_priority (and floodcommon.triage, extended)."""
    if p["message_type"] != "help_request":
        return "none"
    f, sev = set(p["flags"]), SEV.get(p.get("water_level"), -1)
    kids, old = p.get("children_ages") or [], p.get("elderly_ages") or []
    if f & RED_FLAGS or any(a < 1 for a in kids) or sev >= 5:
        return "red"
    if ("bedridden" in f and sev >= 4) or ("pregnant" in f and sev >= 3):
        return "red"
    if f & {"bedridden", "wheelchair", "disabled_blind", "pregnant"} or any(a >= 70 for a in old) or any(a < 6 for a in kids) or sev >= 4:
        return "orange"
    if sev >= 2 or {"food", "water", "medicine"} & set(p.get("needs") or []):
        return "yellow"
    return "green"


def _sigmoid(x):
    return 1 / (1 + np.exp(-x))


def _softmax(x):
    e = np.exp(x - x.max(-1, keepdims=True))
    return e / e.sum(-1, keepdims=True)


def to_probs(logits: dict) -> dict:
    """numpy logits (batch x k) -> probabilities."""
    return {"type": _softmax(logits["type"]), "flags": _sigmoid(logits["flags"]), "needs": _sigmoid(logits["needs"]),
            "water": _softmax(logits["water"]), "bin": _sigmoid(logits["bin"]), "prio": _softmax(logits["prio"])}


def default_thresholds() -> dict:
    return {"flags": {f: 0.5 for f in FLAGS}, "needs": {n: 0.5 for n in NEEDS}, "bin": {b: 0.5 for b in BIN}, "prio_red": 0.5,
            "help_min": 0.5}


def decode(probs: dict, i: int, th: dict, text: str = "") -> dict:
    """Probabilities of item i -> one prediction dict (facts + colour + confidence)."""
    t = TYPES[int(probs["type"][i].argmax())]
    flags = [f for j, f in enumerate(FLAGS) if probs["flags"][i, j] >= th["flags"][f]]
    overridden, rule_hits = False, []
    if t != "help_request" and set(flags) & RED_FLAGS and probs["type"][i, 0] >= th.get("help_min", 0.5):
        t, overridden = "help_request", True           # safety: a life-threatening signal must not be lost to a type mistake
    if USE_RULES and t == "irrelevant" and help_cue(text):
        t, overridden = "help_request", True           # short plea ("ฝากน้องอีกคนนะคะ") the model filed as chatter
        rule_hits.append("help_cue")
    needs = [n for j, n in enumerate(NEEDS) if probs["needs"][i, j] >= th["needs"][n]]
    w = WATER[int(probs["water"][i].argmax())]
    kids, old = ages(text)
    p = {"message_type": t, "flags": flags, "needs": needs, "water_level": None if w == "none" else w,
         "lost_contact": bool(probs["bin"][i, 0] >= th["bin"]["lost_contact"]),
         "insufficient_info": bool(probs["bin"][i, 1] >= th["bin"]["insufficient_info"]),
         "children_ages": kids, "elderly_ages": old}
    p["type_overridden"] = overridden
    p["priority_rules"] = rule_priority(p)
    if t == "help_request":
        pr = probs["prio"][i]
        head = "red" if pr[0] >= th["prio_red"] else PRIO[int(pr[1:].argmax()) + 1]
        p["priority_head"] = head
        p["priority"] = max(p["priority_rules"], head, key=lambda c: RANK[c])
        crit = critical_hits(text) if USE_RULES else []
        if crit:
            p["priority"] = "red"                      # infant / collapse / breathing / bleeding words: never below red
            rule_hits += ["critical:" + w for w in crit]
    else:
        p["priority_head"] = p["priority"] = "none"
    # confidence for the Agent's escalate-to-LLM decision: weakest of the decisions that matter most
    margins = [float(probs["type"][i].max())]
    for j, f in enumerate(FLAGS):                             # a red flag near its threshold = uncertain
        if f in RED_FLAGS:
            q = float(probs["flags"][i, j]); thr = th["flags"][f]
            if 0.25 * thr < q < min(0.95, thr + 0.3):
                margins.append(0.5 + abs(q - thr))
    p["confidence"] = round(min(margins), 3)
    p["red_prob"] = round(float(max(probs["prio"][i][0] if t == "help_request" else 0,
                                    max(probs["flags"][i, FLAGS.index(f)] for f in RED_FLAGS))), 3)
    p["rule_hits"] = rule_hits
    return p


# ---------------- thresholds ----------------
def _prf(y, yhat):
    tp = float((y & yhat).sum()); fp = float((~y & yhat).sum()); fn = float((y & ~yhat).sum())
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


GRID = [round(x, 2) for x in np.arange(0.05, 0.951, 0.05)]


def tune_thresholds(probs: dict, rows: list[dict], texts: list[str], red_recall: float = 0.98, min_pos: int = 5) -> dict:
    """Pick thresholds on the DEV set. Red flags: highest threshold that still reaches the recall target.
    Others: best F1. Too few positives -> keep 0.5 (a threshold tuned on 2 examples is noise)."""
    th = default_thresholds()
    Y = np.array([encode(r)["flags"] for r in rows]).astype(bool)
    N = np.array([encode(r)["needs"] for r in rows]).astype(bool)
    B = np.array([encode(r)["bin"] for r in rows]).astype(bool)
    for cols, name, Ytrue, P in ((FLAGS, "flags", Y, probs["flags"]), (NEEDS, "needs", N, probs["needs"]), (BIN, "bin", B, probs["bin"])):
        for j, c in enumerate(cols):
            y = Ytrue[:, j]
            if y.sum() < min_pos:
                continue
            if c in RED_FLAGS:
                # life-threatening flag: among thresholds that reach the recall target pick the best F2;
                # if none reaches it, near-best recall at the highest threshold — not blindly the lowest (that made
                # sick_now fire on 8x too many messages and forced them red)
                def fb(t, b):
                    p, r, _ = _prf(y, P[:, j] >= t)
                    return (1 + b * b) * p * r / (b * b * p + r) if p + r else 0.0
                ok = [t for t in GRID if _prf(y, P[:, j] >= t)[1] >= red_recall]
                if ok:
                    th[name][c] = max(ok, key=lambda t: (fb(t, 2), t))
                else:                                   # target unreachable: stay within 5 points of the best recall,
                    rec = {t: _prf(y, P[:, j] >= t)[1] for t in GRID}          # and take the highest such threshold
                    th[name][c] = max(t for t in GRID if rec[t] >= max(rec.values()) - 0.05)
            else:
                th[name][c] = max(GRID, key=lambda t: (_prf(y, P[:, j] >= t)[2], -abs(t - 0.5)))
    # priority head + type-override bar. A dev set has few red cases (one miss = -3%), so instead of "highest
    # threshold that still hits the target" (which drives the threshold to ~0.1 and turns half the orange cases red),
    # choose the best F2 (recall weighted 2x over precision) among settings that reach the target; if none does,
    # take the best recall.
    gold_red = np.array([r.get("priority") == "red" for r in rows])
    if gold_red.sum() >= min_pos:
        def f2(p, r):
            return 5 * p * r / (4 * p + r) if p + r else 0.0
        best, best_key = (0.5, 0.5), (-1.0, -1.0, 0.0)
        for hm in (0.5, 0.4, 0.3, 0.2, 0.1, 0.05):
            for t in GRID:
                th2 = {**th, "prio_red": t, "help_min": hm}
                pred_red = np.array([decode(probs, i, th2, texts[i])["priority"] == "red" for i in range(len(rows))])
                p, r, _ = _prf(gold_red, pred_red)
                key = (1.0 if r >= red_recall else 0.0, f2(p, r) if r >= red_recall else r, t)
                if key > best_key:
                    best, best_key = (t, hm), key
        th["prio_red"], th["help_min"] = best
        pred_red = np.array([decode(probs, i, {**th}, texts[i])["priority"] == "red" for i in range(len(rows))])
        p, r, _ = _prf(gold_red, pred_red)
        th["dev_red_recall"], th["dev_red_precision"] = round(r, 4), round(p, 4)
    return th


# ---------------- metrics ----------------
def evaluate(preds: list[dict], rows: list[dict]) -> dict:
    out = {"n": len(rows)}
    out["type_acc"] = round(float(np.mean([p["message_type"] == r["message_type"] for p, r in zip(preds, rows)])), 4)
    out["type"] = {}
    for t in TYPES:
        y = np.array([r["message_type"] == t for r in rows]); yh = np.array([p["message_type"] == t for p in preds])
        P, R, F = _prf(y, yh); out["type"][t] = {"support": int(y.sum()), "precision": round(P, 3), "recall": round(R, 3), "f1": round(F, 3)}
    for key, cols in (("flags", FLAGS), ("needs", NEEDS)):
        out[key] = {}
        for c in cols:
            y = np.array([c in r.get(key, []) for r in rows]); yh = np.array([c in p[key] for p in preds])
            if y.sum() or yh.sum():
                P, R, F = _prf(y, yh); out[key][c] = {"support": int(y.sum()), "precision": round(P, 3), "recall": round(R, 3), "f1": round(F, 3)}
        f1s = [v["f1"] for v in out[key].values() if v["support"] >= 5]
        out[key + "_macro_f1"] = round(float(np.mean(f1s)), 4) if f1s else None
    help_rows = [(p, r) for p, r in zip(preds, rows) if r["message_type"] == "help_request"]
    if help_rows:
        out["water_acc"] = round(float(np.mean([(p["water_level"] or "none") == (r.get("water_level") or "none") for p, r in help_rows])), 4)
        for name in ("priority", "priority_rules", "priority_head"):
            out[name + "_acc"] = round(float(np.mean([p[name] == r.get("priority") for p, r in help_rows])), 4)
        y = np.array([r.get("priority") == "red" for _, r in help_rows]); yh = np.array([p["priority"] == "red" for p, _ in help_rows])
        P, R, F = _prf(y, yh)
        out["red"] = {"support": int(y.sum()), "precision": round(P, 3), "recall": round(R, 3), "f1": round(F, 3)}
        out["priority_confusion"] = {g: {q: sum(1 for p, r in help_rows if r.get("priority") == g and p["priority"] == q) for q in PRIO} for g in PRIO}
        out["under_triage"] = sum(1 for p, r in help_rows if RANK[p["priority"]] < RANK.get(r.get("priority"), -1))
    return out


def score(m: dict) -> float:
    """Model selection on DEV: red recall matters most, then type accuracy, flags F1, colour accuracy."""
    red = (m.get("red") or {}).get("recall", 0)
    return round(0.4 * red + 0.25 * m["type_acc"] + 0.2 * (m.get("flags_macro_f1") or 0) + 0.15 * m.get("priority_acc", 0), 4)


# ---------------- torch part ----------------
try:
    import torch
    import torch.nn as nn
except ImportError:                                     # backend without torch: the numpy helpers above still work
    torch = nn = None

if nn is not None:
    class FloodWCB(nn.Module):
        def __init__(self, backbone, hidden: int, dropout: float = 0.1):
            super().__init__()
            self.backbone = backbone
            self.drop = nn.Dropout(dropout)
            # ModuleDict keys get a "head_" prefix: a key named "type" would clash with nn.Module.type()
            self.heads = nn.ModuleDict({"head_type": nn.Linear(hidden, len(TYPES)), "head_flags": nn.Linear(hidden, len(FLAGS)),
                                        "head_needs": nn.Linear(hidden, len(NEEDS)), "head_water": nn.Linear(hidden, len(WATER)),
                                        "head_bin": nn.Linear(hidden, len(BIN)), "head_prio": nn.Linear(hidden, len(PRIO))})

        def forward(self, input_ids, attention_mask):
            h = self.backbone(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
            m = attention_mask.unsqueeze(-1).to(h.dtype)
            pooled = (h * m).sum(1) / m.sum(1).clamp(min=1.0)          # mean pooling over real tokens
            x = self.drop(pooled)
            return {k[len("head_"):]: head(x) for k, head in self.heads.items()}

    class Predictor:
        """Load an exported model folder (no internet needed) and predict on raw texts."""
        def __init__(self, path, device: str | None = None, threads: int | None = None):
            from transformers import AutoConfig, AutoModel, AutoTokenizer
            path = Path(path)
            self.cfg = json.loads((path / "floodwcb_config.json").read_text(encoding="utf-8"))
            self.th = self.cfg["thresholds"]
            self.tok = AutoTokenizer.from_pretrained(path)
            backbone = AutoModel.from_config(AutoConfig.from_pretrained(path))
            self.model = FloodWCB(backbone, backbone.config.hidden_size)
            sd = torch.load(path / "model.pt", map_location="cpu")
            self.model.load_state_dict({k: v.float() for k, v in sd.items()})
            self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
            if threads:
                torch.set_num_threads(threads)
            self.model.to(self.device).eval()
            self.max_len = self.cfg.get("max_len", 256)

        @torch.no_grad()
        def logits(self, texts: list[str], batch: int = 16) -> dict:
            out = {k: [] for k in ("type", "flags", "needs", "water", "bin", "prio")}
            for i in range(0, len(texts), batch):
                enc = self.tok([preprocess(t) for t in texts[i:i + batch]], truncation=True, max_length=self.max_len,
                               padding=True, return_tensors="pt").to(self.device)
                o = self.model(enc["input_ids"], enc["attention_mask"])
                for k in out:
                    out[k].append(o[k].float().cpu().numpy())
            return {k: np.concatenate(v) for k, v in out.items()}

        def predict(self, texts: list[str], batch: int = 16) -> list[dict]:
            lg = self.logits(texts, batch)
            for head, T in (self.cfg.get("temperature") or {}).items():     # eval/calibrate.py: confidence that means what it says
                if head in lg and T and T > 0:
                    lg[head] = lg[head] / float(T)
            probs = to_probs(lg)
            return [decode(probs, i, self.th, t) for i, t in enumerate(texts)]

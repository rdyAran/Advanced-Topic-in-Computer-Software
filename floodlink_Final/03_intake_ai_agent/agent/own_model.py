"""Adapter: our own trained model (04_flood_nlp_model) -> Extraction.

Two models, chosen with OWN_MODEL (default "auto"):
  * "wcb" - WangchanBERTa fine-tuned on ~4,800 real Hat Yai messages + keyword safety rules (floodwcb.py).
            Needs torch + transformers and the exported folder artifacts/floodwcb_model/ (from the Colab notebook).
  * "v1"  - the small scikit-learn model (floodnlp/), trains itself in ~3 s, no extra packages.
  * "auto"- wcb when its folder and torch are both present, otherwise v1 (the agent never fails to start).
"""
import logging, os, sys
from pathlib import Path

MODEL_DIR = Path(os.getenv("FLOODNLP_DIR", Path(__file__).resolve().parents[2] / "04_flood_nlp_model"))
sys.path.insert(0, str(MODEL_DIR))

from floodnlp.entities import extract_entities                     # noqa: E402
from floodcommon.schemas import Extraction, Flag, Need             # noqa: E402
from floodcommon.triage import normalize_area, people_total        # noqa: E402

log = logging.getLogger(__name__)
WCB_DIR = Path(os.getenv("WCB_DIR", MODEL_DIR / "artifacts" / "floodwcb_model"))
FIELDS = ["message_type", "flags", "needs", "water_level", "adults", "children_ages",
          "elderly_ages", "children_count", "elderly_count", "building_floors", "days_trapped", "contact", "house_no", "street"]
FLAG_OK, NEED_OK = {f.value for f in Flag}, {n.value for n in Need}


class OwnModelProvider:
    """v1: TF-IDF + logistic regression (floodnlp)."""
    kind = "v1"

    def __init__(self, path: str | None = None):
        from floodnlp.model import load_or_train, DEFAULT_PATH
        self.model = load_or_train(Path(path) if path else DEFAULT_PATH)
        self.version = self.model.meta.get("version", "?")
        self.last_confidence = None

    def predict(self, text: str, force_help: bool = False) -> tuple[Extraction, dict]:
        p = self.model.predict(text)
        e = Extraction(**{k: p.get(k) for k in FIELDS}, area=normalize_area(text), summary=_summary(p))
        self.last_confidence = p["confidence"]
        return e, p["confidence"]

    def extract(self, text: str) -> Extraction:
        return self.predict(text)[0]


class WCBProvider:
    """v2: WangchanBERTa multi-task model + keyword safety rules. Same predict() contract as OwnModelProvider."""
    kind = "wcb"

    def __init__(self, path: Path = WCB_DIR):
        import floodwcb as W
        self.W = W
        self.P = W.Predictor(path, device=os.getenv("WCB_DEVICE") or None, threads=int(os.getenv("WCB_THREADS", "2")))
        self.version = self.P.cfg.get("version", "wcb")
        self.last_confidence = None

    def predict(self, text: str, force_help: bool = False) -> tuple[Extraction, dict]:
        p = self.P.predict([text])[0]
        if force_help and p["message_type"] != "help_request":
            p = {**p, "message_type": "help_request"}       # follow-up for a known case: keep flags / needs / water
        help_ = p["message_type"] == "help_request"
        ents = extract_entities(text) if help_ else {}
        hint, why = None, None
        if help_:
            crit = [h.split(":", 1)[1] for h in p.get("rule_hits", []) if h.startswith("critical:")]
            hint = p["priority"]
            why = ("พบคำวิกฤต: " + ", ".join(crit)) if crit else "โมเดลประเมินจากบริบทของข้อความ"
        out = {"message_type": p["message_type"], "flags": [f for f in p["flags"] if f in FLAG_OK] if help_ else [],
               "needs": [n for n in p["needs"] if n in NEED_OK] if help_ else [],
               "water_level": p["water_level"] if help_ else None, **ents}
        e = Extraction(**{k: out.get(k) for k in FIELDS if out.get(k) is not None or k == "message_type"},
                       lost_contact=bool(help_ and p.get("lost_contact")), area=normalize_area(text),
                       summary=_summary({**out, **ents, "children_ages": ents.get("children_ages") or [],
                                         "elderly_ages": ents.get("elderly_ages") or []}),
                       priority_hint=hint, priority_hint_reason=why)
        conf = {"overall": float(p["confidence"]), "red_flags_max_prob": float(p.get("red_prob", 0)),
                "rule_hits": p.get("rule_hits", [])}
        self.last_confidence = conf
        return e, conf

    def extract(self, text: str) -> Extraction:
        return self.predict(text)[0]


def load_own_model():
    """Pick the model from OWN_MODEL (auto | wcb | v1). 'auto' falls back to v1 with a log line, never crashes."""
    choice = os.getenv("OWN_MODEL", "auto").lower()
    if choice in ("auto", "wcb"):
        try:
            if not (WCB_DIR / "model.pt").exists():
                raise FileNotFoundError(f"{WCB_DIR / 'model.pt'} not found (unzip floodwcb_model*.zip there)")
            m = WCBProvider()
            log.info("own model: WangchanBERTa %s", m.version)
            return m
        except Exception as err:
            if choice == "wcb":
                raise
            log.warning("WangchanBERTa model not used (%s) -> falling back to v1", err)
    return OwnModelProvider()


TH = {"bedridden": "ติดเตียง", "dialysis": "ฟอกไต", "heart": "โรคหัวใจ", "pregnant": "ตั้งครรภ์", "injured": "บาดเจ็บ",
      "disabled_blind": "ผู้พิการ", "wheelchair": "เดินลำบาก/รถเข็น", "in_labor": "กำลังคลอด", "sick_now": "ป่วยหนักตอนนี้",
      "chronic_illness": "โรคประจำตัว", "cannot_swim": "ว่ายน้ำไม่เป็น",
      "knee": "น้ำถึงเข่า", "waist": "น้ำถึงเอว", "chest": "น้ำถึงอก",
      "floor1": "น้ำมิดชั้น 1", "floor2": "น้ำถึงชั้น 2", "roof": "อยู่บนหลังคา", "food": "อาหาร", "water": "น้ำดื่ม",
      "milk": "นมเด็ก", "medicine": "ยา", "evacuation": "เรือ/อพยพ", "power": "ไฟ/แบต", "medical": "แพทย์"}


def _summary(p: dict) -> str:
    if p["message_type"] != "help_request":
        return ""
    bits = []
    n = people_total(p)
    if n: bits.append(f"{n} คน")
    if p.get("elderly_ages"): bits.append("ผู้สูงอายุ " + ",".join(map(str, p["elderly_ages"])))
    elif p.get("elderly_count"): bits.append(f"ผู้สูงอายุ {p['elderly_count']}")
    kids = max(len(p.get("children_ages") or []), p.get("children_count") or 0)
    if kids: bits.append(f"เด็ก {kids}")
    bits += [TH.get(f, f) for f in p.get("flags") or []]
    if p.get("water_level"): bits.append(TH[p["water_level"]])
    if p.get("needs"): bits.append("ต้องการ" + "/".join(TH.get(x, x) for x in p["needs"]))
    return " · ".join(bits)

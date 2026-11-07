"""FloodLink NLP model v1 — our own trained multi-head text classifier.

Features : character n-grams (1-4) TF-IDF  -> works on Thai without a word tokenizer, robust to typos
Heads    : message_type (5 classes) · water_level (7 incl. none) · flags (7, multi-label) · needs (6, multi-label)
Values   : entities.py (ages, people, contact, place)

Every prediction returns a confidence so the agent (03) can escalate uncertain messages to the LLM.
"""
import json, re, time
from pathlib import Path
import numpy as np
import joblib
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.preprocessing import MultiLabelBinarizer
from .entities import normalize, extract_entities
from .lexicon import mark

FLAGS = ["bedridden", "dialysis", "heart", "pregnant", "injured", "disabled_blind", "wheelchair"]
NEEDS = ["food", "water", "milk", "medicine", "evacuation", "power"]
NONE = "none"
DEFAULT_PATH = Path(__file__).resolve().parent.parent / "artifacts" / "floodnlp_v1.joblib"
VERSION = "v1.1-charngram+lexicon"
MILK_RX = r"นม(?:เด็ก|ผง|กล่อง|สูตร|หมด|ให้|สำหรับ|แม่|ขวด)|(?:ขาด|ขอ|ไม่มี|ชง)นม|milk|formula"   # not bare "นม": it hides inside "กินมา", "ขึ้นมา"
TAG_PATTERN = r"\[\[[A-Z_]+\]\]|NEG_[A-Z]+"


class FloodNLPModel:
    def __init__(self, ngram=(1, 4), C=6.0, C_multi=8.0, tag_weight=0.6, thr_flags=0.5, thr_needs=0.5, use_lexicon=True, help_bias=0.3):
        # help_bias: if P(help_request) >= this, call it a help request even when another class scores higher.
        # Missing a real request (a red case lost) costs far more than a false alarm an officer can dismiss.
        self.cfg = dict(ngram=ngram, C=C, C_multi=C_multi, tag_weight=tag_weight, thr_flags=thr_flags, thr_needs=thr_needs,
                        use_lexicon=use_lexicon, help_bias=help_bias)
        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=ngram, min_df=2, sublinear_tf=True, max_features=120000)
        # concept tags from lexicon.py as their own features (binary)
        self.tagvec = TfidfVectorizer(token_pattern=TAG_PATTERN, lowercase=False, binary=True, use_idf=False, norm=None)
        self.type_clf = LogisticRegression(max_iter=3000, C=C, class_weight="balanced")
        self.water_clf = LogisticRegression(max_iter=3000, C=C, class_weight="balanced")
        self.flag_mlb = MultiLabelBinarizer(classes=FLAGS)
        self.need_mlb = MultiLabelBinarizer(classes=NEEDS)
        self.flag_clf = OneVsRestClassifier(LogisticRegression(max_iter=3000, C=C_multi, class_weight="balanced"))
        self.need_clf = OneVsRestClassifier(LogisticRegression(max_iter=3000, C=C_multi, class_weight="balanced"))
        self.meta = {}

    # ---------- features ----------
    def _prep(self, text: str) -> str:
        t = normalize(text)
        return mark(t) if self.cfg["use_lexicon"] else t

    def _X(self, texts, fit=False):
        prepped = [self._prep(t) for t in texts]
        if fit:
            Xc = self.vec.fit_transform(prepped)
            Xt = self.tagvec.fit_transform([p + " NEG_NONE" for p in prepped])   # NEG_NONE keeps vocab non-empty
        else:
            Xc = self.vec.transform(prepped)
            Xt = self.tagvec.transform([p + " NEG_NONE" for p in prepped])
        return hstack([Xc, Xt * self.cfg["tag_weight"]]).tocsr()

    # ---------- training ----------
    def fit(self, rows: list[dict]):
        X = self._X([r["text"] for r in rows], fit=True)
        self.type_clf.fit(X, [r["message_type"] for r in rows])
        help_idx = [i for i, r in enumerate(rows) if r["message_type"] == "help_request"]
        Xh = X[help_idx]
        self.water_clf.fit(Xh, [rows[i]["water_level"] or NONE for i in help_idx])
        self.flag_clf.fit(Xh, self.flag_mlb.fit_transform([rows[i]["flags"] for i in help_idx]))
        self.need_clf.fit(Xh, self.need_mlb.fit_transform([rows[i]["needs"] for i in help_idx]))
        self.meta = {"version": VERSION, "trained_at": time.strftime("%Y-%m-%d %H:%M"), "n_train": len(rows),
                     "n_features": len(self.vec.vocabulary_) + len(self.tagvec.vocabulary_), "config": {k: (list(v) if isinstance(v, tuple) else v) for k, v in self.cfg.items()}}
        return self

    # ---------- inference ----------
    def predict(self, text: str) -> dict:
        X = self._X([text])
        tp = self.type_clf.predict_proba(X)[0]
        mtype = self.type_clf.classes_[int(np.argmax(tp))]
        p_help = float(tp[list(self.type_clf.classes_).index("help_request")])
        if mtype != "help_request" and p_help >= self.cfg.get("help_bias", 1.0):
            mtype = "help_request"
        out = {"message_type": mtype, "flags": [], "needs": [], "water_level": None,
               "adults": None, "children_ages": [], "elderly_ages": [], "days_trapped": None,
               "contact": None, "house_no": None, "street": None,
               "confidence": {"message_type": float(tp.max()) if mtype == self.type_clf.classes_[int(np.argmax(tp))] else p_help}}
        if mtype == "help_request":
            wp = self.water_clf.predict_proba(X)[0]
            w = self.water_clf.classes_[int(np.argmax(wp))]
            out["water_level"] = None if w == NONE else w
            fp = self.flag_clf.predict_proba(X)[0]
            npb = self.need_clf.predict_proba(X)[0]
            out["flags"] = [FLAGS[i] for i, p in enumerate(fp) if p >= self.cfg["thr_flags"]]
            out["needs"] = [NEEDS[i] for i, p in enumerate(npb) if p >= self.cfg["thr_needs"]]
            if "milk" in out["needs"] and not re.search(MILK_RX, text, re.I):   # milk must be mentioned
                out["needs"].remove("milk")
            # how sure is the model about each yes/no decision? (0.5 = coin flip, 1.0 = certain)
            out["confidence"].update({
                "water_level": float(wp.max()),
                "flags": float(np.min(np.abs(fp - self.cfg["thr_flags"])) / max(self.cfg["thr_flags"], 1 - self.cfg["thr_flags"])),
                "needs": float(np.min(np.abs(npb - self.cfg["thr_needs"])) / max(self.cfg["thr_needs"], 1 - self.cfg["thr_needs"])),
                "red_flags_max_prob": float(max(fp[FLAGS.index(f)] for f in ("dialysis", "heart", "injured"))),
            })
            out.update(extract_entities(text))
        out["confidence"]["overall"] = float(min(v for k, v in out["confidence"].items() if k != "red_flags_max_prob"))
        return out

    # ---------- persistence ----------
    def save(self, path: Path = DEFAULT_PATH):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path, compress=3)

    @staticmethod
    def load(path: Path = DEFAULT_PATH) -> "FloodNLPModel":
        return joblib.load(path)


def load_or_train(path: Path = DEFAULT_PATH, train_file: Path | None = None) -> FloodNLPModel:
    """Load the saved model; if it's missing or was saved by another scikit-learn version, retrain (takes seconds)."""
    try:
        return FloodNLPModel.load(path)
    except Exception:
        train_file = train_file or Path(path).parent.parent / "data" / "train.jsonl"
        rows = [json.loads(l) for l in open(train_file, encoding="utf-8")]
        m = FloodNLPModel().fit(rows)
        try:
            m.save(path)
        except Exception:
            pass
        return m

"""Model v2 (optional, needs GPU): fine-tune WangchanBERTa (Thai RoBERTa) with the same 4 heads as v1.

    pip install -r requirements-gpu.txt
    python train_wangchanberta.py --epochs 4 --extra data/gemini_train.jsonl data/teacher_labels.jsonl
    -> artifacts/floodnlp_v2/  (weights + heads + label maps)

RTX 3060 12GB: batch 16, max_len 128 -> roughly 5–10 min for ~4k messages.
NOTE: written for the team's GPU machine; NOT executed in the build sandbox (no torch there).
Integrate by adding a provider like agent/own_model.py that calls V2Model.predict().
"""
import argparse, json, sys
from pathlib import Path
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModel, AutoTokenizer

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from floodnlp.model import FLAGS, NEEDS                      # noqa: E402
from floodnlp.entities import normalize                       # noqa: E402

BASE = "airesearch/wangchanberta-base-att-spm-uncased"
TYPES = ["help_request", "hazard_report", "status_update_resolved", "donation_offer", "irrelevant"]
WATERS = ["none", "knee", "waist", "chest", "floor1", "floor2", "roof"]


class Heads(nn.Module):
    def __init__(self, base=BASE):
        super().__init__()
        self.enc = AutoModel.from_pretrained(base)
        h = self.enc.config.hidden_size
        self.drop = nn.Dropout(0.1)
        self.type, self.water = nn.Linear(h, len(TYPES)), nn.Linear(h, len(WATERS))
        self.flags, self.needs = nn.Linear(h, len(FLAGS)), nn.Linear(h, len(NEEDS))

    def forward(self, **x):
        cls = self.drop(self.enc(**x).last_hidden_state[:, 0])
        return self.type(cls), self.water(cls), self.flags(cls), self.needs(cls)


class DS(Dataset):
    def __init__(self, rows, tok, max_len):
        self.rows, self.tok, self.max_len = rows, tok, max_len

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        r = self.rows[i]
        return (normalize(r["text"]), TYPES.index(r["message_type"]), WATERS.index(r.get("water_level") or "none"),
                [float(f in r["flags"]) for f in FLAGS], [float(n in r["needs"]) for n in NEEDS],
                float(r["message_type"] == "help_request"))


def collate(tok, max_len):
    def f(batch):
        texts, t, w, fl, nd, is_help = zip(*batch)
        enc = tok(list(texts), padding=True, truncation=True, max_length=max_len, return_tensors="pt")
        return enc, torch.tensor(t), torch.tensor(w), torch.tensor(fl), torch.tensor(nd), torch.tensor(is_help)
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default=str(HERE / "data/train.jsonl"))
    ap.add_argument("--val", default=str(HERE / "data/val.jsonl"))
    ap.add_argument("--extra", nargs="*", default=[])
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--bs", type=int, default=16)
    ap.add_argument("--lr", type=float, default=3e-5)
    ap.add_argument("--max_len", type=int, default=128)
    ap.add_argument("--out", default=str(HERE / "artifacts/floodnlp_v2"))
    a = ap.parse_args()
    load = lambda p: [json.loads(l) for l in open(p, encoding="utf-8")]
    rows = load(a.train) + [r for e in a.extra for r in load(e)]
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(BASE)
    model = Heads().to(dev)
    dl = DataLoader(DS(rows, tok, a.max_len), batch_size=a.bs, shuffle=True, collate_fn=collate(tok, a.max_len))
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.01)
    ce, bce = nn.CrossEntropyLoss(), nn.BCEWithLogitsLoss(reduction="none")
    for ep in range(a.epochs):
        model.train(); total = 0.0
        for enc, t, w, fl, nd, is_help in dl:
            enc = {k: v.to(dev) for k, v in enc.items()}
            t, w, fl, nd, is_help = t.to(dev), w.to(dev), fl.to(dev), nd.to(dev), is_help.to(dev)
            lt, lw, lf, ln = model(**enc)
            m = is_help.unsqueeze(1)   # water/flags/needs only learned from help requests
            loss = ce(lt, t) + (ce(lw, w) if is_help.sum() else 0) \
                + (bce(lf, fl) * m).sum() / m.sum().clamp(min=1) / len(FLAGS) \
                + (bce(ln, nd) * m).sum() / m.sum().clamp(min=1) / len(NEEDS)
            opt.zero_grad(); loss.backward(); opt.step(); total += loss.item()
        print(f"epoch {ep + 1}: loss {total / len(dl):.4f}")
    Path(a.out).mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), Path(a.out) / "heads.pt")
    tok.save_pretrained(a.out)
    (Path(a.out) / "labels.json").write_text(json.dumps({"types": TYPES, "waters": WATERS, "flags": FLAGS, "needs": NEEDS, "base": BASE}))
    print("saved ->", a.out, "| evaluate by wiring a V2 provider into 03 and running 05_evaluation/evaluate.py")


if __name__ == "__main__":
    main()

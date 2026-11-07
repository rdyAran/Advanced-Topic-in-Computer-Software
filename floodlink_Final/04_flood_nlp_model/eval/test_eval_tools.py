"""The evaluation tools themselves (no torch needed)."""
import csv, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import agreement, check_leakage  # noqa: E402
from evalutil import norm_text  # noqa: E402


def test_kappa_and_near_duplicates():
    assert agreement.kappa(list("aabb"), list("aabb")) == 1.0
    assert abs(agreement.kappa(list("abab"), list("aabb"))) < 1e-9          # chance level
    tr = [{"text": "ช่วยด้วย ยายติดเตียง ซ.สังทิศ 2 คอหงส์ โทร 081-111-2222"}, {"text": "อีกเรื่องหนึ่งที่ไม่เกี่ยว"}]
    te = [{"text": "ช่วยด้วย ยายติดเตียง ซ.สังทิศ 2 คอหงส์ โทร 089-999-0000!!"}, {"text": "ข้อความใหม่จริง ๆ ไม่ซ้ำใคร เลย"}]
    L = check_leakage.leaks(tr, te)
    assert len(L) == 1 and L[0][0] is te[0] and norm_text("โทร 08 1") == norm_text("โทร  09 9")


def test_agreement_score_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    for who, pr in (("A", ["red", "yellow"]), ("B", ["red", "green"])):
        with open(f"annotator_{who}.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f); w.writerow(["id", "text", "message_type", "priority", "water_level", "flags", "needs"])
            w.writerow(["1", "ก", "help_request", pr[0], "chest", "bedridden", ""]); w.writerow(["2", "ข", "help_request", pr[1], "", "", ""])
    monkeypatch.setattr(sys, "argv", ["agreement.py", "score", "annotator_A.csv", "annotator_B.csv"])
    agreement.main()
    out = capsys.readouterr().out
    assert "priority" in out and (tmp_path / "disagreements.csv").exists()

import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import prepare, label_groq, build_dataset

RAW = "โพสต์ต้นทาง\nตอบกลับ\nสมชาย ใจดี\n ·\nแฟนตัวยง\nช่วยด้วยค่ะ นางสาวกมล ชูใจ ติดเตียง โทร.06-55160328 บ้านเลขที่ 47 ซ.8\n7.0176062\n100.4563052\nไม่มีคำอธิบายรูปภาพ\nตอบกลับ\nแก้ไขแล้ว\nมานี มีนา\n ·\nสู้ๆค่ะ คุณสมชาย ใจดี\nตอบกลับ\n"


def test_parse_and_anonymise():
    rows = prepare.parse(RAW)
    assert [r["author"] for r in rows] == [None, "สมชาย ใจดี", "มานี มีนา"]
    assert rows[1]["has_image"] and "แฟนตัวยง" not in rows[1]["text"]
    t, _ = prepare.anonymise(rows[1]["text"], {"สมชาย ใจดี", "มานี มีนา"})
    assert "55160328" not in t and "กมล" not in t and "บ้านเลขที่ 47" not in t and "0176062" not in t
    assert "ติดเตียง" in t and "ซ.8" in t                     # content the model needs is kept
    t2, _ = prepare.anonymise(rows[2]["text"], {"สมชาย ใจดี"})
    assert "สมชาย" not in t2 and prepare.is_chatter(t2)


def test_clean_rejects_bad_llm_values():
    assert label_groq.clean({"id": 1, "message_type": "x"}) is None          # invalid type -> retried, never guessed
    c = label_groq.clean({"id": "id=R00012", "message_type": "help_request", "flags": ["dialysis", "bogus"],
                          "elderly_ages": [85, 20, "x"], "adults": "3", "priority": "purple"})
    assert c["id"] == "R00012" and c["flags"] == ["dialysis"] and c["elderly_ages"] == [85]
    assert c["adults"] == 3 and c["priority"] == "none"                        # "3" -> 3, bad enum -> none


def test_rule_priority_extended():
    base = {"message_type": "help_request", "flags": [], "needs": [], "water_level": None}
    assert build_dataset.rule_priority({**base, "flags": ["in_labor"]}) == "red"
    assert build_dataset.rule_priority({**base, "water_level": "roof"}) == "red"
    assert build_dataset.rule_priority({**base, "flags": ["bedridden"]}) == "orange"
    assert build_dataset.rule_priority({**base, "needs": ["food"]}) == "yellow"
    assert build_dataset.rule_priority({**base, "message_type": "irrelevant"}) == "none"

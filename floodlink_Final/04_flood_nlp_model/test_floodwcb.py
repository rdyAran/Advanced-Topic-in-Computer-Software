import numpy as np, floodwcb as W

def test_preprocess_and_ages():
    assert W.preprocess("ช่วยด้วย  ค่าาาาาา\nยาย 85") == "ช่วยด้วย<_>ค่าาา<_>ยาย<_>85"
    kids, old = W.ages("เด็ก 3 ขวบ ทารก 6 เดือน ยาย 85 ปี ลุงอายุ 72")
    assert kids == [3.0, 0.5] and sorted(old) == [72, 85]

def test_encode_masks_non_help():
    e = W.encode({"message_type": "irrelevant", "flags": [], "needs": [], "priority": "none"})
    assert e["water"] == W.IGNORE and e["prio"] == W.IGNORE and e["bin_mask"] == 0
    e = W.encode({"message_type": "help_request", "flags": ["dialysis"], "needs": ["food"], "water_level": "floor2", "priority": "red"})
    assert e["flags"][W.FLAGS.index("dialysis")] == 1 and e["water"] == W.WATER.index("floor2") and e["prio"] == 0

def _probs(n, rng):
    lg = {"type": rng.normal(size=(n, 5)), "flags": rng.normal(-2, 1, size=(n, 11)), "needs": rng.normal(-1, 1, size=(n, 7)),
          "water": rng.normal(size=(n, 7)), "bin": rng.normal(size=(n, 2)), "prio": rng.normal(size=(n, 4))}
    return lg

def test_decode_priority_is_the_more_urgent_path():
    pr = W.to_probs({"type": np.array([[5., 0, 0, 0, 0]]), "flags": np.full((1, 11), -5.), "needs": np.full((1, 7), -5.),
                     "water": np.array([[0, 0, 0, 0, 0, 5., 0]]), "bin": np.zeros((1, 2)), "prio": np.array([[3., 0, 0, 0]])})
    p = W.decode(pr, 0, W.default_thresholds(), "ช่วยด้วย")
    assert p["priority_rules"] == "orange" and p["priority_head"] == "red" and p["priority"] == "red"

def test_tune_reaches_red_recall_on_dev_and_eval_runs():
    rng = np.random.default_rng(0); n = 300
    rows = []
    for i in range(n):
        red = i % 6 == 0
        rows.append({"message_type": "help_request" if i % 4 else "irrelevant", "flags": ["dialysis"] if red else [],
                     "needs": ["food"] if i % 3 == 0 else [], "water_level": "floor2" if i % 5 == 0 else None,
                     "lost_contact": i % 7 == 0, "insufficient_info": False, "priority": "red" if red else "yellow"})
        if rows[-1]["message_type"] != "help_request":
            rows[-1].update(flags=[], priority="none")
    lg = _probs(n, rng)
    for i, r in enumerate(rows):                 # make the logits informative but noisy
        lg["type"][i, W.TYPES.index(r["message_type"])] += 2.5
        if "dialysis" in r["flags"]: lg["flags"][i, W.FLAGS.index("dialysis")] += rng.uniform(0.5, 4)
        if r["priority"] == "red": lg["prio"][i, 0] += 1.5
    probs = W.to_probs(lg); texts = ["x"] * n
    th = W.tune_thresholds(probs, rows, texts, red_recall=0.98)
    preds = [W.decode(probs, i, th, texts[i]) for i in range(n)]
    m = W.evaluate(preds, rows)
    assert m["red"]["recall"] >= 0.98 and 0 <= W.score(m) <= 1
    assert set(m["priority_confusion"]) == set(W.PRIO)


def _irrelevant_probs():
    return W.to_probs({"type": np.array([[0., 0, 0, 0, 5.]]), "flags": np.full((1, 11), -5.), "needs": np.full((1, 7), -5.),
                       "water": np.array([[5., 0, 0, 0, 0, 0, 0]]), "bin": np.zeros((1, 2)), "prio": np.array([[0, 0, 0, 5.]])})


def test_help_cue_catches_short_pleas_but_not_cheering():
    for t in ["ฝากน้องอีกคนนะคะ", "#ฝากเคสนี้ด้วยนะค่ะ เห็นเม้นนี้ด้วย", "ซอย 4 โชคสมาน 5 ด้วยค่ะ", "ช่วยด่วนได้ไหมคะ น้องตัวซีดแล้ว",
              "อดอาหารหลายวันแล้วค่ะช่วยหน่อยนะค่ะ", "ที้นี้ด้วยน่ะ ขาดการติดต่อ 5วันแล้วค่ะ"]:
        assert W.help_cue(t), t
    for t in ["ขอให้ทุกคนปลอดภัยนะคะ", "ขอบคุณช่วยด้วยใจจริงๆ..ดูแลตัวเองนะคะ", "ฝากช่วยสตูลหน่อยนะค่ะ หนักไม่แพ้หาดใหญ่เลยค่ะ",
              "ช่วยกันแชร์นะคะ", "รัฐบาลช่วยอะไรบ้าง", "สงสารเด็กทารกมาก", "ช่วยออกมาให้ได้ค่ะ"]:
        assert not W.help_cue(t), t


def test_rules_turn_short_plea_into_red_help_request():
    p = W.decode(_irrelevant_probs(), 0, W.default_thresholds(), "ฝากตรงนี้ด้วยค่ะมีเด็กทารกค่ะ")
    assert p["message_type"] == "help_request" and p["priority"] == "red" and "help_cue" in p["rule_hits"]
    p = W.decode(_irrelevant_probs(), 0, W.default_thresholds(), "สงสารเด็กทารกมาก")       # cheering stays irrelevant
    assert p["message_type"] == "irrelevant" and p["priority"] == "none"
    W.USE_RULES = False
    try:
        p = W.decode(_irrelevant_probs(), 0, W.default_thresholds(), "ฝากตรงนี้ด้วยค่ะมีเด็กทารกค่ะ")
        assert p["message_type"] == "irrelevant" and p["rule_hits"] == []
    finally:
        W.USE_RULES = True


def test_critical_words_respect_negation():
    assert W.critical_hits("ลูกไข้สูง ตัวซีดแล้ว") == ["ตัวซีด", "ไข้สูง"]
    for t in ["ไม่มีไข้สูง แค่หิว", "ไม่ได้ฟอกไต", "ตอนนี้ไม่ชักแล้ว", "ยังไม่หมดสติ", "ไม่ต้องใช้ออกซิเจน"]:
        assert W.critical_hits(t) == [], t
    assert W.critical_hits("ยายไม่สบาย หายใจลำบาก") == ["หายใจลำบาก"]       # negation must sit right before the word


def test_help_cue_allows_spaces_between_help_and_please():
    assert W.help_cue("ช่วยผ่านไปให้อาหาร น้ำ ด้วยนะคะ")

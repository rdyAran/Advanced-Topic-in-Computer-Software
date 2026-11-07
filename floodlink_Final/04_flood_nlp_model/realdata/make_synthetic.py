"""Synthetic examples for classes that are rare in the real Hat Yai data (TRAIN ONLY — never dev/test).

Written in the style of the real comments (locations, emojis, typos, <NAME> masks), with labels that follow
LABEL_GUIDE.md exactly. Every row has "source": "synthetic" so it can be counted / removed / ablated.

  python make_synthetic.py            -> data/synthetic_rare.jsonl  (build_dataset.py adds it to train.jsonl)
"""
import json, random, re
from pathlib import Path

R = random.Random(2568)
OUT = Path(__file__).resolve().parent / "data" / "synthetic_rare.jsonl"
SEV = {"knee": 1, "waist": 2, "chest": 3, "floor1": 3, "floor2": 4, "roof": 5}
RED_FLAGS = {"dialysis", "heart", "injured", "in_labor", "sick_now"}

ROADS = ["โชคสมาน5", "โชคสมาน6", "โชคสมาน4", "รัตนอุทิศ", "ราษฎร์อุทิศ", "นิพัทธ์สงเคราะห์1", "นิพัทธ์สงเคราะห์3", "สาครมงคล2",
         "เพชรเกษม", "พลพิชัย", "รัถการ", "จันทร์วิโรจน์", "คึกฤทธิ์", "สุทธิสมิทธิ์"]
AREAS = ["เขต8", "คลองแห", "ควนลัง", "หาดใหญ่ใน", "สะพานดำ", "คอหงส์", "ท่าเคียน", "ทุ่งเสา", "สายกลาง"]
MARKS = ["ตรงข้ามเซเว่น", "หลังวัดโคกสมานคุณ", "ใกล้มัสยิด", "ซอยตัน บ้านสุดท้ายขวามือ", "บ้านสองชั้นสีฟ้า", "หน้าบ้านมีป้ายร้านซ่อมรถ",
         "ติดทางรถไฟ", "ตรงข้ามคลินิก", "หลังคาสีส้ม", "ข้างร้านข้าวมันไก่", "ใกล้โรงเรียน", "หลังตลาด"]
REL = ["แม่", "พ่อ", "ยาย", "ตา", "ลุง", "ป้า", "น้า", "พี่สาว", "พี่ชาย", "น้องสาว", "น้องชาย", "เพื่อน", "หลาน", "ย่า", "ปู่", "อา", "พี่เขย"]
OPEN = ["🆘ขอความช่วยเหลือด่วนค่ะ🆘", "ช่วยด้วยค่ะ", "ช่วยด้วยครับ", "📌รบกวนหน่วยงานที่เห็นโพสต์นี้ด้วยค่ะ", "#ขอความช่วยเหลือ", "พี่กันคะ ช่วยหน่อยค่ะ",
        "ฝากเคสนี้ด้วยนะคะ", "‼️ด่วนมากค่ะ‼️", "รบกวนช่วยหน่อยครับ", "🚨ขอความช่วยเหลือเร่งด่วน🚨", "กันจอมพลัง ช่วยสู้ ขอความช่วยเหลือค่ะ", ""]
END = ["🙏🙏🙏", "ขอบคุณมากค่ะ", "ขอบคุณครับ🙏", "ฝากแชร์ด้วยนะคะ", "😭🙏", "รบกวนด้วยนะครับ", "", "", "ช่วยด้วยนะคะ🥺"]
WATER = [("น้ำถึงเข่า", "knee"), ("น้ำถึงเอวแล้ว", "waist"), ("น้ำถึงอก", "chest"), ("น้ำท่วมมิดชั้น1แล้ว", "floor1"),
         ("น้ำขึ้นชั้น2แล้ว", "floor2"), ("น้ำจะถึงชั้น 2 แล้ว", "floor2"), ("ตอนนี้ขึ้นไปอยู่บนหลังคาแล้ว", "roof"), ("", None), ("", None), ("", None)]


def phone():
    return R.choice(["08", "09", "06"]) + str(R.randint(1, 9)) + "-" + str(R.randint(100, 999)) + "-" + str(R.randint(1000, 9999))


def place(detail=None):
    detail = R.random() < 0.8 if detail is None else detail
    if not detail:
        return R.choice(AREAS)
    p = R.choice([f"บ้านเลขที่ {R.randint(1, 999)} {R.choice(ROADS)} ซอย {R.randint(1, 24)}",
                  f"{R.choice(ROADS)} ซ.{R.randint(1, 24)} {R.choice(MARKS)}",
                  f"{R.choice(AREAS)} {R.choice(ROADS)} ซอย{R.randint(1, 24)}",
                  f"หมู่{R.randint(1, 9)} {R.choice(['คลองแห', 'ควนลัง', 'คอหงส์'])} {R.choice(MARKS)}"])
    return "📍" + p if R.random() < 0.4 else p


def noise(t):
    """Real comments: random emoji, missing spaces, common typos."""
    if R.random() < 0.3:
        t = t.replace(" ", "", R.randint(1, 3))
    if R.random() < 0.15:
        t = t.replace("ค่ะ", "คะ").replace("ช่วย", "ข่วย", 1)
    if R.random() < 0.15:
        t = t.replace("อยู่", "ยุ")
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def rule_priority(p):
    f, sev = set(p["flags"]), SEV.get(p.get("water_level"), -1)
    kids, old = p.get("_kids", []), p.get("_old", [])
    if f & RED_FLAGS or any(a < 1 for a in kids) or sev >= 5:
        return "red"
    if ("bedridden" in f and sev >= 4) or ("pregnant" in f and sev >= 3):
        return "red"
    if f & {"bedridden", "wheelchair", "disabled_blind", "pregnant"} or any(a >= 70 for a in old) or any(a < 6 for a in kids) or sev >= 4:
        return "orange"
    if sev >= 2 or {"food", "water", "medicine"} & set(p["needs"]) or p.get("lost_contact"):
        return "yellow"
    return "green"


def help_msg(core, flags, needs, kids=(), old=(), extra_lines=()):
    w_txt, wl = R.choice(WATER)
    lc = R.random() < 0.3
    detail = R.random() < 0.85
    lines = [R.choice(OPEN), core]
    lines += list(extra_lines)
    if w_txt:
        lines.append(w_txt)
    if lc:
        lines.append(R.choice(["ตอนนี้ติดต่อไม่ได้แล้วค่ะ", "ขาดการติดต่อมา2วันแล้ว", "แบตน่าจะหมด ติดต่อไม่ได้", "#ติดต่อไม่ได้"]))
    lines.append(place(detail))
    if R.random() < 0.6:
        lines.append(f"ติดต่อ {phone()} {R.choice(['(ผู้แจ้ง)', '', 'ลูกสาว', '<NAME>'])}".strip())
    lines.append(R.choice(END))
    if R.random() < 0.35:
        R.shuffle(lines[1:-1])
    p = {"message_type": "help_request", "flags": sorted(set(flags)), "needs": sorted(set(needs)), "water_level": wl,
         "lost_contact": lc, "insufficient_info": False, "_kids": list(kids), "_old": list(old)}
    p["priority"] = rule_priority(p)
    p["text"] = noise("\n".join(x for x in lines if x))
    return p


def other_msg(mtype, text):
    return {"message_type": mtype, "flags": [], "needs": [], "water_level": None, "lost_contact": False,
            "insufficient_info": False, "priority": "none", "text": noise(text)}


# ---------------- class generators ----------------
def dialysis():
    rel, n = R.choice(REL), R.randint(2, 6)
    core = R.choice([f"{rel}ต้องฟอกไตอาทิตย์ละ 3 ครั้ง ไม่ได้ฟอกมา{n}วันแล้ว",
                     f"มีผู้ป่วยไตวายต้องล้างไต ({rel} อายุ{R.randint(45, 85)}) ตอนนี้เลยรอบฟอกไตมา{n}วัน",
                     f"{rel}ล้างไตทางหน้าท้อง น้ำยาล้างไตหมดแล้วค่ะ",
                     f"ผู้ป่วยฟอกไต ตัวเริ่มบวม หายใจเหนื่อย ไม่ได้ไปฟอกตามนัด",
                     f"{rel}เป็นโรคไตต้องฟอกเลือด พลาดรอบวันจันทร์ไปแล้ว ตอนนี้อ่อนเพลียมาก",
                     f"มีคนฟอกไต 1 คน ต้องไปโรงพยาบาลด่วน ไม่ได้ฟอกมา {n} วัน"])
    age = re.search(r"อายุ(\d+)", core)
    return help_msg(core, ["dialysis"], ["medical", "evacuation"], old=[int(age.group(1))] if age and int(age.group(1)) >= 60 else [])


def missing_meds():
    rel = R.choice(REL)
    symptomatic = R.random() < 0.6
    drug, ill = R.choice([("อินซูลิน", "เบาหวาน"), ("ยาความดัน", "ความดันสูง"), ("ยากันชัก", "ลมชัก"), ("ยาพ่นหอบ", "หอบหืด"),
                          ("ยาหัวใจ", "โรคหัวใจ"), ("ยาละลายลิ่มเลือด", "เส้นเลือดสมองตีบ"), ("ยาจิตเวช", "โรคประจำตัว")])
    sym = R.choice(["ตอนนี้มึนหัว อาเจียน", "เริ่มชักแล้ว", "หายใจไม่ค่อยออก", "เจ็บหน้าอก", "ซึมลง เรียกไม่ค่อยตอบ", "น้ำตาลต่ำ เหงื่อออก ใจสั่น"])
    core = f"{rel}เป็น{ill} {drug}หมดมา{R.randint(1, 5)}วันแล้ว" + (f" {sym}" if symptomatic else " ยาเหลือแค่วันเดียว")
    flags = ["chronic_illness"] + (["sick_now"] if symptomatic else []) + (["heart"] if ill == "โรคหัวใจ" else [])
    return help_msg(core, flags, ["medicine"] + (["medical"] if symptomatic else []))


def injured():
    rel = R.choice(REL)
    core = R.choice([f"{rel}ลื่นล้มหัวฟาดพื้นตอนขนของหนีน้ำ เลือดออก", f"{rel}ขาหักตอนปีนขึ้นหลังคา เดินไม่ได้",
                     f"{rel}โดนสังกะสีบาดขา แผลลึก เลือดไหลไม่หยุด", f"{rel}ตกบันไดตอนน้ำขึ้น ปวดหลังมาก ขยับไม่ได้",
                     f"แผลที่เท้า{rel}ติดเชื้อ บวมแดง มีหนอง แช่น้ำมาหลายวัน", f"{rel}แขนหักตอนเรือล่ม",
                     f"{rel}โดนไฟดูดตอนน้ำท่วม ตอนนี้ยังมึนๆ", f"มีคนบาดเจ็บ 1 คน หัวแตก ต้องการหมอด่วน"])
    return help_msg(core, ["injured"], ["medical", "evacuation"])


def labor_infant():
    kind = R.choice(["labor", "labor", "infant", "infant", "newborn", "pregnant"])
    rel = R.choice(["พี่สาว", "น้องสาว", "ภรรยา", "ลูกสาว", "หลานสาว", "เพื่อน"])
    if kind == "labor":
        core = R.choice([f"{rel}ท้องแก่ปวดท้องคลอดถี่ๆแล้วค่ะ", f"{rel}น้ำเดินแล้ว ต้องไปโรงพยาบาลด่วน",
                         f"{rel}ครบกำหนดคลอดวันนี้ เริ่มเจ็บท้องแล้ว", f"มีคนจะคลอด ปวดท้องมากค่ะ ช่วยด้วย"])
        return help_msg(core, ["pregnant", "in_labor"], ["medical", "evacuation"])
    if kind == "infant":
        m = R.randint(1, 11)
        core = R.choice([f"มีลูก{m}เดือน นมผงหมดแล้วค่ะ", f"หลานอายุ{m}เดือน ไม่มีนมกินมา2วัน", f"มีเด็กทารก {m} เดือน ผ้าอ้อมกับนมหมด"])
        return help_msg(core, [], ["milk", "evacuation"], kids=[round(m / 12, 2)])
    if kind == "newborn":
        d = R.randint(3, 25)
        core = R.choice([f"มีเด็กแรกเกิด {d} วัน กับแม่ที่เพิ่งคลอด", f"{rel}เพิ่งคลอดได้{d}วัน ลูกยังเล็กมาก ต้องการอพยพ"])
        return help_msg(core, [], ["milk", "evacuation"], kids=[0.05])
    core = f"{rel}ตั้งท้อง {R.randint(4, 8)} เดือน " + R.choice(["ยังไม่มีอาการอะไร แต่อยากอพยพออกก่อน", "ขาดอาหารมา2วัน", "เดินขึ้นลงบันไดลำบาก"])
    return help_msg(core, ["pregnant"], ["evacuation"] + (["food"] if "อาหาร" in core else []))


def resolved():
    rel = R.choice(REL)
    loc = place(R.random() < 0.6)
    t = R.choice([f"อัพเดทค่ะ {rel}ได้รับการช่วยเหลือแล้ว ออกมาอยู่ศูนย์อพยพ ม.อ. แล้วนะคะ ขอบคุณทีมกู้ภัยมากๆค่ะ🙏",
                  f"เคส{loc} ได้รับความช่วยเหลือแล้วครับ เรือเข้าไปรับเมื่อเช้า ขอบคุณครับ ไม่ต้องไปซ้ำแล้วนะครับ",
                  f"ปิดเคสค่ะ {rel}ปลอดภัยแล้ว ตอนนี้อยู่บ้านญาติ ขอบคุณทุกคนที่ช่วยแชร์",
                  f"ติดต่อ{rel}ได้แล้วค่ะ ปลอดภัยดี ทหารเข้าไปส่งอาหารแล้ว 🙏 รบกวนลบเคสนี้ออกด้วยนะคะ",
                  f"แจ้งค่ะ {loc} อพยพออกมาครบทุกคนแล้ว ขอบคุณพี่กันและทีมงานค่ะ",
                  f"ตามที่ฝากไว้เมื่อวาน ตอนนี้{rel}ออกมาได้แล้วนะคะ ขอบคุณที่ช่วยค่ะ ไปช่วยบ้านอื่นต่อได้เลย",
                  f"{rel}ถึงโรงพยาบาลแล้วค่ะ ได้ฟอกไตแล้ว ขอบคุณเจ้าหน้าที่ทุกท่าน",
                  f"✅ได้รับการช่วยเหลือแล้ว✅ {loc} ขอบคุณค่ะ"])
    return other_msg("status_update_resolved", t)


def hazard():
    loc = place(R.random() < 0.7)
    t = R.choice([f"⚠️ระวังไฟรั่ว {loc} เสาไฟล้ม สายไฟจมน้ำอยู่ เรืออย่าเพิ่งเข้า",
                  f"แจ้งเตือนค่ะ ตรงคอสะพาน{R.choice(ROADS)} น้ำเชี่ยวมาก เจ็ทสกีล่มไปแล้ว 2 ลำ",
                  f"มีงูเห่าว่ายอยู่ในซอย {loc} ระวังกันด้วยนะคะ",
                  f"ระวังบ่อพักไม่มีฝา {loc} น้ำขุ่นมองไม่เห็น มีคนตกไปแล้ว",
                  f"ถนนยุบเป็นหลุมลึก {loc} รถอย่าวิ่งผ่าน",
                  f"⚡️ไฟฟ้ายังไม่ตัด {loc} น้ำท่วมถึงปลั๊ก ใครเดินลุยน้ำระวังโดนไฟดูด",
                  f"ตึกร้าว {loc} มีเสียงดังตลอด อย่าเข้าไปหลบในตึกนี้",
                  f"แก๊สรั่ว กลิ่นแรงมาก {loc} อย่าจุดไฟแถวนั้น",
                  f"กระแสน้ำแรงมากตรง{R.choice(MARKS)} เรือพายเข้าไม่ได้ ต้องใช้เรือเครื่อง"])
    return other_msg("hazard_report", t)


def offer():
    loc = place(False)
    t = R.choice([f"มีเรือว่าง {R.randint(1, 5)} ลำ พร้อมคนขับ อยู่{R.choice(['หน้า ม.อ.', 'ปั๊มปตท.', loc])} ใครต้องการโทร {phone()}",
                  f"มีเจ็ทสกี 1 ลำ ขับเป็น พร้อมลงพื้นที่{loc}ครับ ประสานได้เลย",
                  f"รถยกสูง 2 คัน พร้อมช่วยขนคนออกจาก{loc} ติดต่อ {phone()}",
                  f"ร้านเราทำข้าวกล่องได้วันละ {R.randint(100, 500)} กล่อง ต้องส่งไปที่ไหนดีคะ",
                  f"เปิดบ้านให้ผู้ประสบภัยพักได้ {R.randint(5, 30)} คน มีที่จอดรถ ห้องน้ำ น้ำไฟพร้อม",
                  f"มีน้ำดื่ม {R.randint(50, 500)} แพ็ค จะเอาไปส่งจุดไหนดีครับ",
                  f"อาสาขับเรือได้ครับ ว่างทั้งวัน ไม่มีเรือแต่มีแรง",
                  f"มีพาวเวอร์แบงค์ {R.randint(20, 100)} ก้อนจะบริจาค ส่งศูนย์ไหนได้บ้างคะ",
                  f"ทีมเรามีเรือท้องแบน 3 ลำ กำลังจะเข้า{loc} ใครมีเคสแถวนั้นส่งพิกัดมาได้เลย",
                  f"รับขนส่งผู้ป่วยติดเตียงไปโรงพยาบาลฟรี มีรถตู้ยกสูง โทร {phone()}",
                  f"ครัวกลาง{R.choice(['วัด', 'มัสยิด', 'โรงเรียน'])}{loc} เปิดแจกข้าวทุกวัน 11 โมง ใครเดินทางได้มารับได้เลย",
                  f"มีหมอกับพยาบาลอาสา {R.randint(2, 6)} คน พร้อมลงพื้นที่ทำแผล ตรวจอาการ ประสานได้ที่ {phone()}",
                  f"ใครต้องการชูชีพ มีให้ยืม {R.randint(10, 60)} ตัว อยู่{loc}",
                  f"รับซ่อมเครื่องยนต์เรือฟรีให้ทีมกู้ภัย อยู่ใกล้{R.choice(MARKS)}",
                  f"มีรถกระบะยกสูงว่าง ขนของบริจาคไป{loc}ได้ครับ",
                  f"บริจาคเสื้อผ้า ผ้าห่ม {R.randint(1, 9)}0 ชุด ส่งที่ไหนดีคะ",
                  f"ทีมอาสาจากสตูล {R.randint(5, 20)} คน พร้อมเรือ 2 ลำ ถึงหาดใหญ่พรุ่งนี้เช้า ต้องการให้ไปช่วยโซนไหน",
                  f"ร้านกาแฟเราเปิดให้ชาร์จแบตฟรี มีเน็ต ที่{loc}",
                  f"มีเครื่องปั่นไฟให้ยืม 1 เครื่อง สำหรับบ้านที่มีผู้ป่วยใช้ออกซิเจน",
                  f"ผมมีโดรนช่วยสำรวจหาคนติดค้างได้ครับ ว่างทั้งสัปดาห์",
                  f"โรงแรมเราว่าง {R.randint(10, 40)} ห้อง ให้ผู้ประสบภัยพักฟรี"])
    return other_msg("donation_offer", t)


def hard_negatives():
    """Look like a rare class but aren't — teaches the model to read, not keyword-match."""
    rel = R.choice(REL)
    k = R.choice(["no_dialysis", "no_injury", "resolved_but_neighbour", "early_pregnancy_safe", "hazard_but_help"])
    if k == "no_dialysis":
        return help_msg(f"ไม่มีผู้ป่วยฟอกไตนะคะ ไม่มีคนป่วย แค่ขาดอาหารกับน้ำดื่มมา{R.randint(2, 4)}วัน", [], ["food", "water"])
    if k == "no_injury":
        return help_msg("ทุกคนปลอดภัย ไม่มีใครบาดเจ็บ แต่ต้องการอพยพออกก่อนน้ำขึ้นอีก", [], ["evacuation"])
    if k == "resolved_but_neighbour":
        return help_msg(f"บ้าน{rel}ได้รับการช่วยเหลือแล้ว แต่บ้านข้างๆ ยังมียายอายุ{R.randint(75, 90)}ติดอยู่คนเดียว", [], ["evacuation"],
                        old=[80])
    if k == "early_pregnancy_safe":
        return help_msg(f"{rel}ท้อง3เดือน ยังไม่มีอาการอะไร อยากได้ข้าวกับน้ำ", ["pregnant"], ["food", "water"])
    return help_msg("ตรงนี้น้ำเชี่ยวมาก ไฟรั่วด้วย แต่ยังมีคนติดอยู่ในบ้าน 4 คน ต้องการเรือเครื่องเข้าไปรับ", [], ["evacuation"])


PLAN = [("dialysis", dialysis, 110), ("missing_meds", missing_meds, 60), ("injured", injured, 110), ("labor_infant", labor_infant, 130),
        ("resolved", resolved, 130), ("hazard", hazard, 110), ("offer", offer, 120), ("hard_negative", hard_negatives, 80)]


def main():
    seen, rows, i = set(), [], 0
    for group, fn, n in PLAN:
        got, tries = 0, 0
        while got < n and tries < n * 30:
            tries += 1
            p = fn()
            key = re.sub(r"[\W\d_]+", "", p["text"])
            if key in seen:
                continue
            seen.add(key); got += 1; i += 1
            p.pop("_kids", None); p.pop("_old", None)
            rows.append({"row_id": f"SYN{i:04d}", "source": "synthetic", "synthetic_group": group, **p})
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    from collections import Counter
    print(f"{len(rows)} rows -> {OUT.name}")
    print("groups:", dict(Counter(r["synthetic_group"] for r in rows)))
    print("flags:", dict(Counter(f for r in rows for f in r["flags"])))
    print("types:", dict(Counter(r["message_type"] for r in rows)), "| priority:", dict(Counter(r["priority"] for r in rows)))


if __name__ == "__main__":
    main()

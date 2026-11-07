# -*- coding: utf-8 -*-
"""Generate 200 simulated Thai flood help-request messages with ground-truth labels.
All people, house numbers and phone numbers are fictional. Place names are real Hat Yai
areas; coordinates are approximate area centroids for demo only."""
import json, csv, random, datetime as dt, collections, sys

random.seed(2568)
t0 = dt.datetime(2025, 11, 22, 6, 0)
OUT = sys.argv[1]

AREAS = [  # (area, street/soi options, landmarks, lat, lng)
    ("เขต 8 หาดใหญ่", ["ถ.ศรีภูวนารถ", "ซ.ศรีภูวนารถ 6"], ["ตรงข้ามเซเว่น", "หลังตลาดสด"], 7.0040, 100.4790),
    ("คอหงส์", ["ถ.ปุณณกัณฑ์", "ซ.สังทิศ 2"], ["ใกล้ ม.อ.", "หลังปั๊ม ปตท."], 7.0080, 100.4980),
    ("ถนนครูจีน", ["ซ.ครูจีน 3", "ถ.ครูจีน"], ["หลังหมู่บ้านพฤกษาวิว", "ใกล้วัด"], 7.0150, 100.4620),
    ("ถนนเพชรเกษม", ["ซ.โรงเรียนกอบกาญจน์", "ซ.เพชรเกษม 21"], ["ปากซอยมีโชว์รูมรถ", "ข้างร้านข้าวมันไก่"], 7.0010, 100.4700),
    ("คลองแห", ["ซ.คลองแห 4", "ถ.คลองแห"], ["ใกล้ตลาดน้ำคลองแห", "หลังโรงเรียน"], 7.0300, 100.4850),
    ("คลองเตย หาดใหญ่", ["ซ.คลองเตย 1", "ถ.ราษฎร์อุทิศ"], ["ริมคลอง ร.1", "ข้างสะพาน"], 6.9950, 100.4830),
    ("บ้านพรุ", ["ถ.กาญจนวนิช", "ซ.บ้านพรุ 5"], ["ใกล้แม็คโคร", "หลังวัดบ้านพรุ"], 6.9550, 100.4780),
    ("ควนลัง", ["ถ.ควนลัง", "ซ.ควนลัง 7"], ["ใกล้ อบต.", "ข้างร้านซ่อมรถ"], 7.0050, 100.4350),
    ("ทุ่งเสา", ["ซ.ทุ่งเสา 2", "ถ.ทุ่งเสา"], ["ติดคลองอู่ตะเภา", "หลังโรงสี"], 6.9900, 100.4400),
    ("น้ำน้อย", ["ถ.น้ำน้อย", "ซ.น้ำน้อย 3"], ["ใกล้โรงเรียนบ้านน้ำน้อย", "ปากทางเข้าหมู่บ้าน"], 7.0400, 100.4600),
]
FIRST = ["แม่", "พ่อ", "ยาย", "ตา", "ป้า", "ลุง", "น้า", "พี่สาว", "น้องชาย"]
NAMES = ["คุณเอ", "คุณบี", "คุณซี", "คุณดี", "คุณอี", "คุณเอฟ", "คุณจี", "คุณเอช"]
WATER = [  # (code, phrases, severity 0-5)
    ("knee", ["น้ำถึงเข่า", "น้ำสูงประมาณเข่า"], 0),
    ("waist", ["น้ำถึงเอว", "น้ำท่วมระดับเอว"], 1),
    ("chest", ["น้ำถึงอก", "น้ำสูงเกือบมิดหัว"], 2),
    ("floor1", ["น้ำท่วมมิดชั้น 1", "ชั้นล่างจมหมดแล้ว"], 3),
    ("floor2", ["น้ำขึ้นมาถึงชั้น 2 แล้ว", "น้ำเข้าชั้น 2 แล้ว"], 4),
    ("roof", ["ต้องขึ้นไปอยู่บนหลังคา", "ตอนนี้อยู่บนหลังคาบ้าน"], 5),
]
CHANNELS = ["facebook_page", "facebook_page", "youtube_comment", "tiktok_comment", "line_group", "phone_transcript", "traffy"]
NEEDS = {"food": ["ไม่มีอาหาร", "อาหารหมดแล้ว", "เหลือมาม่าห่อเดียว"],
         "water": ["น้ำดื่มหมด", "ไม่มีน้ำกิน"],
         "milk": ["นมเด็กหมด", "ไม่มีนมให้ลูก"],
         "medicine": ["ยาหมด", "ยาความดันหมดแล้ว"],
         "evacuation": ["ขอเรือมารับ", "อยากให้มาอพยพออกไป"],
         "power": ["แบตใกล้หมด", "ไม่มีไฟชาร์จโทรศัพท์"]}

def typo(s):
    reps = [("ช่วย", "ชวย"), ("ด่วน", "ด่วนนนน"), ("น้ำ", "นำ้"), ("ครับ", "คับ"), ("ค่ะ", "คะ"), ("หลังคา", "หลังคาา"), ("ไม่", "ม่าย")]
    for a, b in reps:
        if a in s and random.random() < 0.35:
            s = s.replace(a, b, 1)
    return s

def make_case(cid):
    area = random.choice(AREAS)
    c = {"case_id": cid, "area": area[0], "street": random.choice(area[1]),
         "landmark": random.choice(area[2]), "house_no": f"{random.randint(1, 299)}" + random.choice(["", "", "/1", "/12"]),
         "lat": round(area[3] + random.uniform(-.004, .004), 5), "lng": round(area[4] + random.uniform(-.004, .004), 5),
         "adults": random.randint(1, 8), "children_ages": [], "elderly_ages": [], "flags": [], "days_trapped": random.randint(0, 5)}
    w = random.choices(WATER, weights=[3, 3, 3, 4, 3, 2])[0]
    c["water"], c["_water_phr"], c["_sev"] = w[0], random.choice(w[1]), w[2]
    if random.random() < .3: c["children_ages"] = sorted(random.sample([1, 2, 3, 5, 7, 10, 12], random.randint(1, 2)))
    if random.random() < .04: c["children_ages"] = [0.75] + c["children_ages"]
    if random.random() < .35: c["elderly_ages"] = sorted(random.sample(range(60, 96), random.randint(1, 2)))
    for f, p in [("bedridden", .12), ("dialysis", .03), ("heart", .03), ("pregnant", .03), ("injured", .03), ("disabled_blind", .02), ("wheelchair", .04)]:
        if random.random() < p: c["flags"].append(f)
    if "bedridden" in c["flags"] and not c["elderly_ages"]: c["elderly_ages"] = [random.randint(75, 95)]
    pool = [n for n in NEEDS if n != "milk" or any(a < 3 for a in c["children_ages"])]
    if c["_sev"] <= 1:
        pool = [n for n in pool if n != "evacuation" and (n not in ("food", "water") or random.random() < .3)]
        c["days_trapped"] = random.randint(0, 1)
    c["needs"] = random.sample(pool, random.randint(1, 2 if c["_sev"] <= 1 else 3))
    c["_t"] = t0 + dt.timedelta(minutes=random.randint(0, 60 * 24 * 4))
    if c["_sev"] >= 3 and "evacuation" not in c["needs"] and random.random() < .6: c["needs"].append("evacuation")
    c["priority"], c["priority_reason"] = priority(c)
    return c

def priority(c):
    f, sev = c["flags"], c["_sev"]
    infant = any(a < 1 for a in c["children_ages"])
    if "dialysis" in f: return "red", "ผู้ป่วยฟอกไต"
    if "heart" in f: return "red", "ผู้ป่วยโรคหัวใจ"
    if "injured" in f: return "red", "มีผู้บาดเจ็บ"
    if infant: return "red", "ทารกอายุต่ำกว่า 1 ปี"
    if "bedridden" in f and sev >= 4: return "red", "ผู้ป่วยติดเตียง + น้ำถึงชั้น 2/หลังคา"
    if "pregnant" in f and sev >= 3: return "red", "หญิงตั้งครรภ์ + น้ำท่วมมิดชั้น 1 ขึ้นไป"
    if "bedridden" in f: return "orange", "ผู้ป่วยติดเตียง"
    if any(x in f for x in ("disabled_blind", "wheelchair", "pregnant")): return "orange", "ผู้พิการ/หญิงตั้งครรภ์"
    if any(a >= 70 for a in c["elderly_ages"]): return "orange", "ผู้สูงอายุ 70+"
    if any(a < 6 for a in c["children_ages"]): return "orange", "เด็กเล็กต่ำกว่า 6 ปี"
    if sev >= 4: return "orange", "น้ำถึงชั้น 2/หลังคา"
    if sev >= 2 or c["days_trapped"] >= 2 or {"food", "water"} & set(c["needs"]): return "yellow", "ติดค้าง/ขาดอาหารน้ำ"
    return "green", "ต้องการสิ่งของ ไม่เร่งด่วน"

FLAG_TXT = {"bedridden": ["{r}ป่วยติดเตียง", "มีผู้ป่วยติดเตียง ({r})"], "dialysis": ["{r}ต้องฟอกไต ไม่ได้ฟอกมา {d} วันแล้ว", "มีคนป่วยไตต้องฟอกไต"],
            "heart": ["{r}เป็นโรคหัวใจ", "มีผู้ป่วยโรคหัวใจ ยาใกล้หมด"], "pregnant": ["มีคนท้อง 8 เดือน", "พี่สาวตั้งครรภ์ใกล้คลอด"],
            "injured": ["{r}ลื่นล้ม ขาน่าจะหัก", "มีคนโดนของบาดเลือดออกเยอะ"], "disabled_blind": ["{r}ตาบอด มองไม่เห็น"],
            "wheelchair": ["{r}นั่งวีลแชร์ เดินไม่ได้"]}

def render(c, variant=0, drop=None):
    """Return (text, fields_present). variant changes wording for duplicates."""
    drop = drop or set()
    parts, present = [], set()
    opener = random.choice(["ช่วยด้วยค่ะ", "ขอความช่วยเหลือด่วนครับ", "🙏🙏 ช่วยด้วยค่ะ", "รบกวนแจ้งกู้ภัยให้หน่อยค่ะ", "ด่วนมาก!!", "ฝากแชร์ด้วยครับ", ""])
    parts.append(opener)
    if "location" not in drop:
        style = random.random()
        if style < .4:
            parts.append(f"บ้านเลขที่ {c['house_no']} {c['street']} {c['area']}"); present |= {"house_no", "street", "area"}
        elif style < .75:
            parts.append(f"{c['street']} {c['landmark']} {c['area']}"); present |= {"street", "landmark", "area"}
        else:
            parts.append(f"แถว{c['area']} {c['landmark']}"); present |= {"area", "landmark"}
    if "people" not in drop:
        txt = f"มีผู้ใหญ่ {c['adults']} คน" if random.random() < .6 else f"อยู่กัน {c['adults'] + len(c['children_ages'])} คน"
        parts.append(txt); present.add("people_count")
        for a in c["children_ages"]:
            parts.append(f"เด็ก {int(a * 12)} เดือน" if a < 1 else f"เด็ก {a} ขวบ")
        for a in c["elderly_ages"]:
            parts.append(f"{random.choice(['ยาย', 'ตา', 'แม่', 'พ่อ'])}อายุ {a}")
        for f in c["flags"]:
            parts.append(random.choice(FLAG_TXT[f]).format(r=random.choice(FIRST), d=random.randint(2, 4)))
        if c["flags"] or c["elderly_ages"] or c["children_ages"]: present.add("vulnerable")
    if "water" not in drop:
        parts.append(c["_water_phr"]); present.add("water_level")
    if c["days_trapped"] and random.random() < .7:
        parts.append(f"ติดมา {c['days_trapped']} วันแล้ว"); present.add("days_trapped")
    parts += [random.choice(NEEDS[n]) for n in c["needs"]]; present.add("needs")
    if "contact" not in drop and random.random() < .6:
        parts.append(f"ติดต่อ 08{random.randint(1, 9)}-xxx-{random.randint(1000, 9999)}"); present.add("contact")
    if variant and random.random() < .5:
        parts.append(random.choice(["แจ้งไปแล้วเมื่อวานยังไม่มีใครมา", "ตอนนี้น้ำขึ้นอีกแล้ว", "โพสต์ซ้ำนะคะ ยังรออยู่"]))
    parts.append(random.choice(["", "ขอบคุณค่ะ", "ช่วยด้วยนะครับ", "😭😭", "ด่วนที่สุด"]))
    sep = random.choice([" ", " ", ", ", "\n"])
    text = sep.join(p for p in parts if p)
    if random.random() < .5: text = typo(text)
    if random.random() < .15: text = text.replace(" ", "")  # no-space style
    return text.strip(), present

REQUIRED = ["area", "people_count", "water_level", "contact"]
rows = []
def ts(): return (t0 + dt.timedelta(minutes=random.randint(0, 60 * 24 * 5))).strftime("%Y-%m-%dT%H:%M")

def add(c, text, present, mtype, channel, dup_of=None):
    t = (c["_t"] + dt.timedelta(minutes=random.randint(30, 60 * 30))) if dup_of else c["_t"]
    rows.append({"channel": channel, "timestamp": t.strftime("%Y-%m-%dT%H:%M"), "text": text, "gt_message_type": mtype, "gt_case_id": c["case_id"] if c else None,
                 "gt_duplicate_of_case": dup_of, "gt_priority": c["priority"] if c else None, "gt_priority_reason": c["priority_reason"] if c else None,
                 "gt_area": c["area"] if c else None, "gt_lat": c["lat"] if c else None, "gt_lng": c["lng"] if c else None,
                 "gt_water_level": c["water"] if c else None, "gt_adults": c["adults"] if c else None,
                 "gt_children_ages": c["children_ages"] if c else None, "gt_elderly_ages": c["elderly_ages"] if c else None,
                 "gt_flags": c["flags"] if c else None, "gt_needs": c["needs"] if c else None,
                 "gt_missing_fields": [f for f in REQUIRED if f not in present] if c else None})

# 1) seed cases modelled on the patterns in the TV clip (anonymised)
seeds = []
s = make_case("C001"); s.update(area="ถนนเพชรเกษม", street="ซ.โรงเรียนกอบกาญจน์", landmark="ปากซอยมีโชว์รูมรถ", adults=5, children_ages=[1, 3], elderly_ages=[92, 72],
    flags=["bedridden", "dialysis"], water="floor2", _water_phr="น้ำขึ้นชั้น 2 แล้ว", _sev=4, days_trapped=5, needs=["food", "milk", "evacuation"])
seeds.append((s, "ช่วยญาติผมด้วยครับ ซอยโรงเรียนกอบกาญจน์ ปากซอยเป็นโชว์รูมรถ ถนนเพชรเกษม ผู้ใหญ่5 เด็ก1ขวบกับ3ขวบ ยายอายุ92ติดเตียง ลุงอายุ72ต้องฟอกไตไม่ได้ฟอกตั้งแต่วันอังคาร ตัวเริ่มบวมแล้ว ติดมา5วัน เหลือนม2กล่องไข่1ฟอง ซอยตันน้ำเชี่ยวมาก แบตจะหมด จะเปิดเครื่องทุก2ชม.",
              {"street", "landmark", "area", "people_count", "vulnerable", "days_trapped", "needs"}))
s = make_case("C002"); s.update(area="ถนนครูจีน", street="ซ.ครูจีน 3", landmark="หลังหมู่บ้านพฤกษาวิว", house_no="88", adults=12, children_ages=[0.75], elderly_ages=[], flags=[],
    water="floor1", _water_phr="บ้านชั้นเดียวจมแล้ว", _sev=3, days_trapped=3, needs=["food", "milk", "evacuation"])
seeds.append((s, "ด่วนค่ะ บ้านเลขที่ 88 ซอยถนนครูจีน หลังหมู่บ้านพฤกษาวิว รวม 13 คน มีเด็ก 9 เดือน บ้านชั้นเดียวจมแล้วต้องย้ายไปอยู่บ้าน 2 ชั้นข้างๆ น้ำยังขึ้นเรื่อยๆ สัญญาณเริ่มไม่มี",
              {"house_no", "street", "landmark", "area", "people_count", "vulnerable", "water_level", "needs"}))
s = make_case("C003"); s.update(area="เขต 8 หาดใหญ่", street="ซ.ศรีภูวนารถ 6", landmark="หลังตลาดสด", adults=3, children_ages=[], elderly_ages=[93, 65], flags=[],
    water="floor1", _water_phr="น้ำท่วมมิดชั้น 1", _sev=3, days_trapped=3, needs=["food", "evacuation"])
seeds.append((s, "แม่อายุ93 กับน้า65 สองคน ติดอยู่ในบ้านตั้งแต่วันเสาร์ ซอยเล็กในเขต8 น้ำมิดชั้น1 อาหารแห้งเริ่มหมด ไม่รู้ว่ารถหรือเรือจะเข้าถึงหน้าบ้านได้ไหม",
              {"area", "people_count", "vulnerable", "water_level", "days_trapped", "needs"}))
for c, text, present in seeds:
    c["priority"], c["priority_reason"] = priority(c)
    add(c, text, present, "help_request", random.choice(["phone_transcript", "facebook_page"]))

# 2) generated unique cases
cases = [x[0] for x in seeds]
for i in range(4, 151):
    c = make_case(f"C{i:03d}"); cases.append(c)
    drop = set()
    if random.random() < .18: drop.add(random.choice(["location", "people", "water", "contact"]))
    text, present = render(c, drop=drop)
    add(c, text, present, "help_request", random.choice(CHANNELS))

# 3) duplicates: same case, other channel / relative / later update
for c in random.sample(cases[3:], 27) + cases[:3]:
    text, present = render(c, variant=1)
    if random.random() < .3: text = f"แชร์ต่อจากเพื่อน: {text}"
    add(c, text, present, "help_request_duplicate", random.choice(CHANNELS), dup_of=c["case_id"])

# 4) volunteer hazard reports, status updates, donations, noise
HAZ = ["ทีมเรือแจ้ง: {a} {s} มีรถกระบะจมอยู่ใต้น้ำ เรือท้องแบนชนแล้ว 1 ลำ ห้ามเข้าทางนี้",
       "จุดอันตราย {a} น้ำเชี่ยวมาก เจ็ตสกีพลิก แนะนำเข้าทาง{s}แทน",
       "{a} สายไฟฟ้าขาดแช่น้ำ อันตราย อย่าเข้าใกล้",
       "ทีมกู้ภัยรายงาน {s} {a} มีเศษไม้และสังกะสีลอยเต็ม เรือเข้าไม่ได้",
       "เจองูจงอางแถว {a} {s} ระวังด้วย"]
for _ in range(9):
    a = random.choice(AREAS)
    rows.append({"channel": random.choice(["line_group", "radio_transcript"]), "timestamp": ts(),
                 "text": random.choice(HAZ).format(a=a[0], s=random.choice(a[1])), "gt_message_type": "hazard_report",
                 "gt_area": a[0], "gt_lat": a[3], "gt_lng": a[4]})
for c in random.sample(cases, 6):
    rows.append({"channel": random.choice(["facebook_page", "line_group"]), "timestamp": ts(), "gt_message_type": "status_update_resolved",
                 "gt_case_id": c["case_id"], "gt_area": c["area"],
                 "text": random.choice([f"อัปเดตค่ะ ที่บ้าน{c['street']} {c['area']} กู้ภัยมารับแล้ว ขอบคุณทุกคน 🙏",
                                         f"เคส{c['area']} {c['landmark']} ได้รับความช่วยเหลือแล้วครับ ไม่ต้องแชร์ต่อ"])})
for t in ["มีเรือคายัค 2 ลำ พร้อมไปช่วยแถวบ้านพรุ ติดต่อได้ที่ไหนครับ", "ร้านเรามีข้าวกล่อง 300 กล่อง จะส่งไปจุดไหนดีคะ",
          "ขอส่งน้ำดื่ม 50 แพ็ค ไปโรงครัวกลางได้ไหมครับ"]:
    rows.append({"channel": "facebook_page", "timestamp": ts(), "text": t, "gt_message_type": "donation_offer"})
for t in ["ขอให้ทุกคนปลอดภัยนะคะ 🙏", "รัฐบาลทำอะไรอยู่!!!"]:
    rows.append({"channel": random.choice(["youtube_comment", "tiktok_comment"]), "timestamp": ts(), "text": t, "gt_message_type": "irrelevant"})

random.shuffle(rows)
rows.sort(key=lambda r: r["timestamp"])
for i, r in enumerate(rows, 1): r["msg_id"] = f"M{i:03d}"

cols = ["msg_id", "timestamp", "channel", "text", "gt_message_type", "gt_case_id", "gt_duplicate_of_case", "gt_priority", "gt_priority_reason",
        "gt_area", "gt_lat", "gt_lng", "gt_water_level", "gt_adults", "gt_children_ages", "gt_elderly_ages", "gt_flags", "gt_needs", "gt_missing_fields"]
with open(f"{OUT}/flood_messages.jsonl", "w", encoding="utf-8") as f:
    for r in rows: f.write(json.dumps({k: r.get(k) for k in cols}, ensure_ascii=False) + "\n")
with open(f"{OUT}/flood_messages.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
    for r in rows: w.writerow({k: (json.dumps(r.get(k), ensure_ascii=False) if isinstance(r.get(k), list) else r.get(k)) for k in cols})

print(len(rows))
print(collections.Counter(r["gt_message_type"] for r in rows))
print(collections.Counter(r.get("gt_priority") for r in rows if r["gt_message_type"] == "help_request"))
print(collections.Counter(r["channel"] for r in rows))
print(sum(1 for r in rows if r.get("gt_missing_fields")), "messages with missing fields")

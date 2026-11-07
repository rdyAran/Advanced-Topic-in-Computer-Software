"""Generate labelled TRAINING data for the FloodLink NLP model (v1).

Labels are decided first, then text is composed from varied phrase pools, so labels are exact.
The hand-written hard test set (05_evaluation/data/hard_messages.jsonl) is held out: no exact
phrase from it is used here.  For more natural variety, run generate_data_gemini.py (teacher LLM).

Usage: python generate_data.py --n 8000 --seed 7 --out data/train.jsonl
"""
import argparse, json, random

R = ["แม่", "พ่อ", "ยาย", "ตา", "ปู่", "ย่า", "ลุง", "ป้า", "น้า", "พี่ชาย", "พี่สาว", "สามี", "ภรรยา", "คุณยาย", "คุณตา"]
KIN_OLD = ["ยาย", "ตา", "ปู่", "ย่า", "แม่", "พ่อ", "คุณยาย", "คุณตา", "ลุง", "ป้า"]
AREAS = [("คอหงส์", ["ซ.สังทิศ 1", "ถ.ปุณณกัณฑ์", "หลัง ม.อ."]), ("ถนนครูจีน", ["ซ.ครูจีน 1", "ใกล้วัดครูจีน"]),
         ("ถนนเพชรเกษม", ["ซ.เพชรเกษม 12", "ข้างโชว์รูม", "ตรงข้ามโรงเรียน"]), ("คลองแห", ["ซ.คลองแห 2", "ใกล้ตลาดน้ำ"]),
         ("คลองเตย", ["ริมคลอง ร.1", "ซ.คลองเตย 3"]), ("บ้านพรุ", ["ถ.กาญจนวนิช", "หลังวัดบ้านพรุ"]),
         ("ควนลัง", ["ซ.ควนลัง 5", "ใกล้ อบต.ควนลัง"]), ("ทุ่งเสา", ["ติดคลองอู่ตะเภา", "ซ.ทุ่งเสา 4"]),
         ("น้ำน้อย", ["ซ.น้ำน้อย 1", "หมู่ 3 น้ำน้อย"]), ("เขต 8", ["ซ.ศรีภูวนารถ 2", "หลังตลาดเขต 8"]),
         ("Khlong Hae", ["soi 2"]), ("Kho Hong", ["near PSU"])]

FLAG = {
    "bedridden": ["{r}ติดเตียง", "{r}ป่วยติดเตียง", "{r}เป็นอัมพาต นอนอยู่บนเตียงตลอด", "มีผู้ป่วยติดเตียง", "{r}ป่วยหนักลุกจากเตียงไม่ได้",
                  "{r}เส้นเลือดในสมองแตก นอนติดเตียง", "{r} bedridden", "{r}เป็นอัมพฤกษ์ครึ่งซีก", "{r}ต้องให้อาหารทางสายยาง",
                  "{r}นอนป่วยมาหลายเดือน ลุกไม่ขึ้น", "{r}ต้องมีคนพลิกตัวให้", "{r}หลังผ่าตัดสมอง นอนอย่างเดียว", "{r} had a stroke, can't get up"],
    "dialysis": ["{r}ต้องฟอกไต", "{r}ป่วยไตวายต้องฟอกเลือด", "มีคนไข้ฟอกไต ขาดฟอกมา {d} วัน", "{r}ถึงคิวฟอกไตแล้วแต่ออกไปไม่ได้",
                 "{r}เป็นโรคไตระยะสุดท้าย", "{r} needs dialysis", "{r}ไตเสื่อม ต้องไปฟอกที่โรงพยาบาลอาทิตย์ละ 3 ครั้ง", "{r}ไตไม่ทำงาน ตัวเริ่มบวมน้ำ",
                 "{r}ต้องทำ dialysis", "{r}เป็นคนไข้ไต นัดฟอกเลือดเมื่อวานแต่ไปไม่ได้"],
    "heart": ["{r}เป็นโรคหัวใจ", "{r}ป่วยหัวใจ", "{r}หัวใจไม่ดี เจ็บหน้าอก", "{r}เพิ่งผ่าตัดหัวใจ", "{r}มีโรคหัวใจประจำตัว", "{r} has heart disease",
              "{r}เพิ่งทำบายพาส", "{r}แน่นหน้าอก หายใจไม่ออก", "{r}ใส่ขดลวดหัวใจ", "{r}หัวใจเต้นผิดจังหวะ"],
    "pregnant": ["มีคนท้อง {m} เดือน", "{f}ตั้งครรภ์ใกล้คลอด", "เมียท้องแก่จะคลอดแล้ว", "มีหญิงตั้งครรภ์อยู่ด้วย", "{f}ท้องได้ {m} เดือนแล้ว", "pregnant woman here",
                 "{f}ครรภ์ {m} เดือน", "{f}เริ่มมีอาการจะคลอด", "{f}น้ำคร่ำเดิน", "{f}กำหนดคลอดสัปดาห์นี้"],
    "injured": ["{r}ลื่นล้ม ขาหัก", "{r}โดนเศษกระจกบาด เลือดออกเยอะ", "{r}ถูกไฟดูด", "{r}หัวแตก", "{r}บาดเจ็บ แผลลึก", "{r}ตกจากหลังคา ขาผิดรูป",
                "{r} is injured, bleeding", "{r}โดนกระแสน้ำพัดชนกำแพง", "{r}แขนหัก", "{r}ล้มหัวฟาด ตอนนี้ซึมๆ", "{r}แผลติดเชื้อ บวมแดง", "{r}จมน้ำ หมดสติไปพักนึง",
                "{r}โดนสายไฟที่ขาดดูด", "{r}ถูกน้ำพัดกระแทกเสา เจ็บหนัก", "{r}โดนรถที่ลอยมาชน", "{r}ถูกงูกัด"],
    "disabled_blind": ["{r}ตาบอด", "{r}พิการทางสายตา", "{r}สายตาพิการ", "{r} is blind", "{r}ตาบอดทั้งสองข้าง", "{r}ตาบอดสนิท ต้องมีคนจูง"],
    "wheelchair": ["{r}นั่งวีลแชร์", "{r}ใช้รถเข็น", "{r}เดินไม่ได้", "{r}ขาพิการ ขยับเองไม่ได้", "{r} uses a wheelchair",
                   "{r}ขาลีบ", "{r}พิการแขนขา", "{r}เดินเองไม่ไหว", "{r} cannot walk"],
}
NEED = {
    "food": ["ไม่มีอาหาร", "อาหารหมด", "ข้าวสารหมดแล้ว", "ไม่มีอะไรจะกิน", "เหลือมาม่าห่อเดียว", "ไม่ได้กินข้าวมาทั้งวัน", "no food",
             "ข้าวก็หมด", "ขาดอาหาร", "ขอข้าวกล่อง", "หิวมาก", "ของกินหมดเกลี้ยง", "ขาดมาม่า"],
    "water": ["น้ำดื่มหมด", "ไม่มีน้ำกิน", "น้ำเปล่าหมดแล้ว", "ขาดน้ำดื่ม", "no drinking water", "ขอน้ำดื่ม", "น้ำขวดหมด"],
    "milk": ["นมเด็กหมด", "นมกล่องหมดแล้ว", "ไม่มีนมให้ลูก", "ขอนมสำหรับเด็ก", "need baby milk", "นมหมด", "ขาดนม", "นมสูตรหมด"],
    "medicine": ["ยาหมด", "ยาประจำตัวหมด", "ขอยาด้วย", "ยาความดันหมด", "ยาเบาหวานหมด", "need medicine",
                 "ยาเหลือ {d} วัน", "ไม่มียาลดไข้", "อินซูลินหมด", "ออกซิเจนใกล้หมด", "ยาใกล้หมด"],
    "evacuation": ["ขอเรือมารับ", "อยากอพยพออก", "ช่วยมารับออกไปที", "ขอเจ็ตสกีมารับ", "พาออกไปที่ปลอดภัยที", "please send a boat",
                   "ช่วยไปรับที", "อยากออกจากบ้าน", "รอเรือมารับ", "need rescue"],
    "power": ["แบตจะหมด", "ไม่มีไฟชาร์จมือถือ", "ไฟดับ โทรศัพท์ใกล้ดับ", "แบตเหลือ 5%", "phone battery dying", "ไฟดับ มือถือจะดับ", "ขอพาวเวอร์แบงค์"],
}
NEG = {"flags": ["ไม่มีผู้ป่วยนะ", "ทุกคนแข็งแรงดี", "ไม่มีคนเจ็บ", "ไม่มีใครป่วย", "ทุกคนโอเค"], "food": ["ข้าวยังมีพอ", "อาหารยังพอกินอีกหลายวัน", "อาหารมีพอ", "ของกินยังเหลือเยอะ"],
       "water": ["น้ำกินยังพอ", "น้ำดื่มยังมีพอ"], "evacuation": ["ยังไม่อยากออกจากบ้าน", "ยังไม่ต้องอพยพ"]}
WATER = {
    "knee": ["น้ำถึงเข่า", "น้ำสูงประมาณหัวเข่า", "น้ำท่วมระดับเข่า", "water knee deep", "น้ำถึงตาตุ่ม", "น้ำยังตื้นแค่ข้อเท้า", "น้ำเริ่มเข้าบ้าน ท่วมพื้น"],
    "waist": ["น้ำถึงเอว", "น้ำระดับเอว", "น้ำสูงเลยเอวแล้ว", "water waist high", "น้ำถึงสะโพก", "น้ำรอบบ้านลึกระดับเอว"],
    "chest": ["น้ำถึงอก", "น้ำสูงเกือบมิดหัว", "น้ำท่วมถึงคอ", "น้ำมิดอกแล้ว", "water chest deep", "น้ำถึงหน้าอก", "ลุยน้ำระดับอก"],
    "floor1": ["น้ำท่วมมิดชั้น 1", "ชั้นล่างจมทั้งหมด", "บ้านชั้นเดียวจมมิดแล้ว", "ชั้นล่างไม่เหลือแล้ว", "น้ำท่วมเต็มชั้นล่าง", "ground floor fully flooded",
               "น้ำมิดหน้าต่างชั้นล่าง", "น้ำท่วมชั้นล่างหมดแล้ว", "ชั้นล่างน้ำเต็ม"],
    "floor2": ["น้ำขึ้นชั้น 2 แล้ว", "น้ำเข้าชั้นสองแล้ว", "หนีขึ้นชั้นบนน้ำก็ตามมา", "น้ำท่วมถึงชั้นบนแล้ว", "flood reached second floor",
               "น้ำขึ้นถึงพื้นชั้นสอง", "น้ำเข้าห้องนอนชั้น 2"],
    "roof": ["อยู่บนหลังคา", "ต้องปีนขึ้นหลังคา", "ขึ้นไปรอบนหลังคาแล้ว", "นั่งอยู่บนหลังคาบ้าน", "we are on the roof", "หนีขึ้นดาดฟ้า", "น้ำปริ่มหลังคา"],
}
TH_NUM = {1: "หนึ่ง", 2: "สอง", 3: "สาม", 4: "สี่", 5: "ห้า", 6: "หก", 7: "เจ็ด", 8: "แปด", 9: "เก้า"}


def thai_num(n: int) -> str:
    if n < 10: return TH_NUM.get(n, str(n))
    t, u = divmod(n, 10)
    s = ("" if t == 1 else "ยี่" if t == 2 else TH_NUM[t]) + "สิบ"
    return s + ("เอ็ด" if u == 1 else TH_NUM.get(u, "") if u else "")


def num(n: int) -> str:
    return thai_num(n) if random.random() < .25 else str(n)


def typo(s: str) -> str:
    for a, b in [("ช่วย", "ชวย"), ("ด่วน", "ด่วนนน"), ("น้ำ", "นำ้"), ("ครับ", "คับ"), ("ค่ะ", "คะ"), ("ไม่", "ม่าย"), ("แล้ว", "แล้วว")]:
        if a in s and random.random() < .25:
            s = s.replace(a, b, 1)
    return s


def help_message():
    lab = {"message_type": "help_request", "flags": [], "needs": [], "water_level": None}
    parts = []
    if random.random() < .7:
        parts.append(random.choice(["ช่วยด้วยค่ะ", "ขอความช่วยเหลือด่วน", "ด่วนมาก!!", "แจ้งแทนญาติครับ", "ฝากแชร์หน่อย", "ใครอยู่ใกล้ช่วยที", "SOS", "help!",
                                    "🙏 ช่วยด้วย", "ญาติโทรมาบอกว่า", "บ้านข้างๆ ยังติดอยู่", "รบกวนประสานกู้ภัย", "เพื่อนส่งข้อความมาว่า", "ตอนนี้", "please help"]))
    if random.random() < .85:
        a, subs = random.choice(AREAS)
        parts.append(random.choice([f"{a} {random.choice(subs)}", f"แถว{a}", f"บ้านเลขที่ {random.randint(1, 300)} {random.choice(subs)} {a}", f"{random.choice(subs)} {a}"]))
    kids = []
    if random.random() < .3:
        for _ in range(random.randint(1, 2)):
            if random.random() < .07:
                dd = random.randint(3, 25); kids.append(round(dd / 365, 2))
                parts.append(random.choice([f"ลูกเพิ่งเกิดได้ {dd} วัน", f"ทารกแรกเกิด อายุ {dd} วัน", f"newborn {dd} days old"]))
            elif random.random() < .2:
                mo = random.randint(1, 11); kids.append(round(mo / 12, 2))
                parts.append(random.choice([f"เด็ก {num(mo)} เดือน", f"ทารก {mo} เดือน", f"ลูกอ่อน {mo} เดือน", f"baby {mo} months", f"เด็กอ่อน{thai_num(mo)}เดือน"]))
            else:
                y = random.randint(1, 12); kids.append(float(y))
                parts.append(random.choice([f"เด็ก {num(y)} ขวบ", f"ลูก {y} ขวบ", f"หลานอายุ {num(y)} ขวบ", f"kid {y} years old"]))
    if random.random() < .4:
        a = random.randint(60, 98)
        parts.append(random.choice([f"{random.choice(KIN_OLD)}อายุ {num(a)}", f"{random.choice(KIN_OLD)} {a} ปี", f"คนแก่ {a} ปี", f"{random.choice(KIN_OLD)}{thai_num(a)}", f"grandma {a} y/o"]))
    if random.random() < .7:
        t = random.randint(1, 9)
        parts.append(random.choice([f"ผู้ใหญ่ {num(t)} คน", f"อยู่กัน {num(t + len(kids))} คน", f"รวม {t + len(kids)} คน", f"ในบ้านมี {num(t + len(kids))} คน", f"{t + len(kids)} people"]))
    for f in random.sample(list(FLAG), k=random.choices([0, 1, 2], weights=[55, 38, 7])[0]):
        lab["flags"].append(f)
        parts.append(random.choice(FLAG[f]).format(r=random.choice(R), f=random.choice(["ลูกสาว", "เมีย", "พี่สาว", "น้องสาว"]), d=random.randint(2, 5), m=random.randint(6, 9)))
    if not lab["flags"] and random.random() < .12:
        parts.append(random.choice(NEG["flags"]))
    if random.random() < .85:
        lvl = random.choices(list(WATER), weights=[2, 3, 3, 4, 3, 2])[0]
        lab["water_level"] = lvl; parts.append(random.choice(WATER[lvl]))
    elif random.random() < .3:
        parts.append(random.choice(["อยู่คอนโดชั้น 6", "อยู่ตึกแถวชั้น 3", "ออกจากหมู่บ้านไม่ได้"]))
    for n in random.sample(list(NEED), k=random.choices([0, 1, 2, 3], weights=[15, 45, 30, 10])[0]):
        if n == "milk" and not any(k < 3 for k in kids) and random.random() < .7:
            continue
        lab["needs"].append(n); parts.append(random.choice(NEED[n]).replace("{d}", str(random.randint(1, 3))))
    for n, negs in NEG.items():
        if n != "flags" and n not in lab["needs"] and random.random() < .06:
            parts.append(random.choice(negs))
    if random.random() < .4:
        parts.append(random.choice([f"ติดมา {num(random.randint(1, 5))} วันแล้ว", f"{random.randint(1, 4)} คืนแล้ว", "ตั้งแต่เมื่อวาน", "since yesterday"]))
    if random.random() < .5:
        parts.append(random.choice([f"โทร 08{random.randint(1, 9)}-xxx-{random.randint(1000, 9999)}", f"ติดต่อ 09{random.randint(0, 9)}xxx{random.randint(1000, 9999)}"]))
    random.shuffle(parts[1:]) if len(parts) > 2 else None
    return parts, lab


HAZ_CORE = ["มีรถจมอยู่ใต้น้ำ เรือผ่านไม่ได้", "กระแสน้ำแรงมาก เรือเล็กพลิกไปแล้ว", "เสาไฟล้มขวางทาง", "มีงูเยอะ", "ท่อนไม้ลอยเต็มทาง",
            "น้ำลึกเกินเมตร รถเล็กอย่าเข้า", "ไฟรั่วลงน้ำ", "คันกั้นน้ำเริ่มรั่ว", "มีหลุมใหญ่ใต้น้ำ", "ถนนทรุด", "ตะขาบกับแมงป่องหนีน้ำขึ้นบ้าน",
            "มีจระเข้หลุดออกมา", "สะพานไม้พังแล้ว", "น้ำวนแรงตรงคอสะพาน", "ประตูระบายน้ำจะเปิดคืนนี้ น้ำจะขึ้นเร็ว", "strong current, boats capsized"]
HAZ_PRE = ["ระวัง!", "เตือนภัย", "แจ้งเตือน", "ทีมกู้ภัยแจ้ง", "อาสาเรือฝากบอก", "ข่าวจากหน้างาน", "⚠️", "", "warning:"]
HAZ_POST = ["", "อย่าใช้ทางนี้", "เลี่ยงไปทางอื่น", "ใครลุยน้ำแถวนั้นระวังด้วย", "ชาวบ้านแถวนั้นเตรียมย้ายของขึ้นที่สูง", "กู้ภัยกำลังเข้าไปดู", "avoid this route"]
RES = ["เรือมารับออกมาแล้ว", "ปลอดภัยแล้วนะคะ", "อยู่ศูนย์อพยพแล้ว", "ได้รับความช่วยเหลือแล้ว", "กู้ภัยพาออกมาครบทุกคนแล้ว", "ถึงโรงพยาบาลเรียบร้อยแล้ว",
       "ญาติมารับไปอยู่ด้วยแล้ว", "คลอดที่โรงพยาบาลแล้ว แม่ลูกปลอดภัย", "has been rescued", "is safe now"]
RES_PRE = ["อัปเดต:", "อัพเดตเคส", "ขอบคุณทุกคนที่แชร์", "ขอบคุณทีมกู้ภัยมากค่ะ", "แจ้งปิดเคส", "update:", "", "ลบโพสต์ได้แล้ว"]
RES_WHO = ["คุณยาย", "ครอบครัวเรา", "บ้านที่แจ้งไว้", "คนท้อง", "ผู้ป่วยติดเตียง", "เคสเด็กเล็ก", "พ่อแม่", "family"]
OFF = ["มีเรือพาย {k} ลำ พร้อมลงพื้นที่", "จะส่งน้ำดื่ม {n} แพ็ค", "ทำข้าวกล่องแจกได้ {n} กล่อง", "มีรถกระบะยกสูงว่าง", "มีเครื่องปั่นไฟให้ยืม {k} เครื่อง",
       "รับบริจาคเสื้อผ้า", "ขอเป็นอาสาขับเรือ", "มีเจ็ตสกีพร้อมคนขับ", "เปิดบ้านให้พักฟรี {k} ห้อง", "มีพาวเวอร์แบงค์แจก", "ทำข้าวแกงแจก {n} ห่อ",
       "มีชุดชูชีพ {n} ตัวให้ยืม", "we can donate {n} life jackets"]
OFF_POST = ["", "ใครต้องการทักมา", "ส่งไปที่ไหนดีครับ", "ต้องติดต่อใคร", "ใครขาดอะไรบอกได้", "ติดต่อได้ที่เพจ", "ใครอยากชาร์จแบตมาได้"]
CHAT = ["สู้ๆ นะชาวสงขลา", "ขอให้ทุกคนปลอดภัย 🙏", "ทำไมน้ำท่วมทุกปี แก้ไม่ได้สักที", "ฝนตกอีกแล้ว เบื่อ", "ดูข่าวแล้วใจหาย", "หน่วยงานไปไหนกันหมด",
        "รอดูว่าจะท่วมนานแค่ไหน", "แชร์ไปแล้วนะ", "stay safe everyone", "เป็นกำลังใจให้ทุกคน", "สงสารคนแก่กับเด็กมาก", "ขอให้น้ำลดไวๆ",
        "ช่วยกันแชร์เยอะๆ", "ดูไลฟ์อยู่", "ปีหน้าจะท่วมอีกไหมเนี่ย", "เมื่อไหร่ฝนจะหยุด", "ใครอยู่หาดใหญ่บ้าง ปลอดภัยไหม", "นี่แหละเมืองเรา"]


def other_message(t):
    a, subs = random.choice(AREAS)
    where = random.choice([f"แถว{a}", f"{a} {random.choice(subs)}", f"{random.choice(subs)} {a}", a])
    if t == "hazard_report":
        parts = [random.choice(HAZ_PRE), where, random.choice(HAZ_CORE), random.choice(HAZ_POST)]
    elif t == "status_update_resolved":
        parts = [random.choice(RES_PRE), random.choice(RES_WHO), f"ที่{a}" if random.random() < .7 else "", random.choice(RES)]
    elif t == "donation_offer":
        parts = [random.choice(OFF).format(k=random.randint(1, 6), n=random.choice([50, 100, 200, 300, 500])),
                 where if random.random() < .5 else "", random.choice(OFF_POST)]
    else:
        parts = [random.choice(CHAT)] + ([random.choice(CHAT)] if random.random() < .3 else [])
    return [p for p in parts if p], {"message_type": t, "flags": [], "needs": [], "water_level": None}


def make(n, seed):
    random.seed(seed)
    types = random.choices(["help_request", "hazard_report", "status_update_resolved", "donation_offer", "irrelevant"], weights=[70, 9, 8, 7, 6], k=n)
    rows = []
    for t in types:
        parts, lab = help_message() if t == "help_request" else other_message(t)
        text = random.choice([" ", " ", ", ", "\n"]).join(parts)
        text = typo(text)
        if random.random() < .1:
            text = text.replace(" ", "")
        rows.append({"text": text, **lab})
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=8000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="data/train.jsonl")
    a = ap.parse_args()
    rows = make(a.n, a.seed)
    with open(a.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} rows -> {a.out}")

"""Hand-written 'hard' messages: free-form Thai, implicit wording, negation, Thai number words,
English, dialect, traps for keyword rules. Labels are written by hand; colour + missing fields
are computed from the labels with the same rules as the system (so rules are applied consistently).

Run: python eval/build_hard_set.py  -> backend/data/hard_messages.jsonl
"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from app.schemas import Extraction            # noqa: E402
from app.triage import priority, missing_fields  # noqa: E402

H = "help_request"
# (case_id, type, dup_of, text, labels)
ITEMS = [
 ("H01", H, None, "แม่ผมนอนอยู่กับที่มา 3 ปีแล้ว ลุกเองไม่ได้ ตอนนี้น้ำขึ้นมาถึงชั้นบนแล้วครับ อยู่คอหงส์ ซอยสังทิศ 2 บ้านมีผม เมีย กับแม่ ติดต่อ 081-xxx-2231",
  dict(area="คอหงส์", adults=3, flags=["bedridden"], water_level="floor2", contact="081-xxx-2231")),
 ("H02", H, None, "ลุงต้องล้างไตทุกสัปดาห์ ตอนนี้เลยกำหนดมา 3 วัน ขาบวมหมดแล้ว บ้านอยู่ทุ่งเสา ติดคลองอู่ตะเภา น้ำเกือบถึงหลังคาบ้านชั้นเดียว",
  dict(area="ทุ่งเสา", flags=["dialysis"], water_level="floor1")),
 ("H03", H, None, "ลูกสาวเพิ่งคลอดได้สองอาทิตย์ ยังอยู่บ้านแถวควนลัง น้ำท่วมถึงเอว ออกไปไหนไม่ได้ นมผงหมดแล้ว",
  dict(area="ควนลัง", children_ages=[0.04], water_level="waist", needs=["milk"])),
 ("H04", H, None, "ที่บ้านมีสามคน ตาเก้าสิบ ยายแปดสิบห้า กับหลาน 4 ขวบ ชั้นล่างจมหมด อยู่ถนนครูจีนซอยสาม ใกล้วัด โทร 089-xxx-1182",
  dict(area="ถนนครูจีน", adults=2, elderly_ages=[85, 90], children_ages=[4], water_level="floor1", contact="089-xxx-1182")),
 ("H05", H, None, "ไม่มีคนป่วยหรือคนแก่นะคะ ผู้ใหญ่ 4 คน น้ำแค่หัวเข่า มีอาหารพอ แต่ไฟดับ โทรศัพท์จะหมดแบต อยู่บ้านพรุ ซ.บ้านพรุ 5",
  dict(area="บ้านพรุ", adults=4, water_level="knee", needs=["power"])),
 ("H06", H, None, "ไม่ต้องการอาหารค่ะ มีพอ ต้องการเรือมารับคนท้องแปดเดือนไปโรงพยาบาล เจ็บท้องแล้ว น้ำท่วมมิดชั้นล่าง คลองแห ซอย 4",
  dict(area="คลองแห", flags=["pregnant"], water_level="floor1", needs=["evacuation"])),
 ("X07", "hazard_report", None, "ใครจะเข้าแถวน้ำน้อย อย่าใช้ทางปากทางเข้าหมู่บ้านนะ มีรถเก๋งจมอยู่ เมื่อกี้เรืออาสาไปชนใบพัดหักไปลำนึง", dict(area="น้ำน้อย")),
 ("H01", "status_update_resolved", None, "ขอบคุณป่อเต็กตึ๊งมากๆ ค่ะ ตอนนี้พาแม่จากคอหงส์ออกมาถึงศูนย์พักพิงแล้ว ปลอดภัยแล้ว", dict(area="คอหงส์")),
 ("X09", "donation_offer", None, "ผมมีเจ็ตสกี 1 ลำ ขับเป็น อยู่สะเดา ถ้าต้องการคนช่วยทักมาได้เลยครับ", {}),
 ("X10", "irrelevant", None, "น้ำท่วมทุกปี ช่วยอะไรไม่ได้เลย ภาษีที่จ่ายไปไปไหนหมด", {}),
 ("H11", H, None, "help! my grandma 88 y/o stuck at Khlong Hae soi 4, water up to 2nd floor, no food since yesterday",
  dict(area="คลองแห", elderly_ages=[88], water_level="floor2", days_trapped=1, needs=["food"])),
 ("H12", H, None, "บ้านหนังลอยแล้ว ช่วยแหน่ น้ำถึงอก อยู่กันห้าคน มีเด็กน้อยสองขวบ ซอยคลองเตย 1 ริมคลอง ร.1",
  dict(area="คลองเตย หาดใหญ่", adults=4, children_ages=[2], water_level="chest")),
 ("H13", H, None, "พ่อเป็นโรคหัวใจ ยาเหลือแค่มื้อเดียว พวกเราสี่คนติดอยู่บนชั้นสองตั้งแต่เมื่อวานซืน เพชรเกษม ซอย 21",
  dict(area="ถนนเพชรเกษม", adults=4, flags=["heart"], water_level="floor2", days_trapped=2, needs=["medicine"])),
 ("H13", H, "H13", "ญาติดิฉันที่เพชรเกษม 21 พ่อป่วยหัวใจ ยาหมดแล้ว ตอนนี้น้ำขึ้นถึงหลังคาแล้วค่ะ ช่วยด่วน 086-xxx-7712",
  dict(area="ถนนเพชรเกษม", flags=["heart"], water_level="roof", needs=["medicine"], contact="086-xxx-7712")),
 ("H04", H, "H04", "ตายายกับหลานที่ครูจีน ซ.3 ใกล้วัด ยังไม่มีใครไปเลย น้ำเริ่มขึ้นชั้นสองแล้ว",
  dict(area="ถนนครูจีน", water_level="floor2")),
 ("H16", H, None, "น้องชายพิการขาทั้งสองข้าง ต้องมีคนอุ้ม น้ำถึงเอว ทุ่งเสาซอย 2 หลังโรงสี อยู่กับแม่สองคน",
  dict(area="ทุ่งเสา", adults=2, flags=["wheelchair"], water_level="waist")),
 ("H17", H, None, "ป้าข้างบ้านมองไม่เห็น อยู่คนเดียว น้ำมิดชั้น 1 แล้ว ช่วยไปดูหน่อย บ้านเลขที่ 45 ถ.ควนลัง",
  dict(area="ควนลัง", adults=1, flags=["disabled_blind"], water_level="floor1")),
 ("H18", H, None, "พี่ชายโดนสังกะสีเฉือนขาลึกมาก เลือดไม่หยุด อยู่บ้านพรุ หลังวัด น้ำถึงเอว 3 คน",
  dict(area="บ้านพรุ", adults=3, flags=["injured"], water_level="waist")),
 ("H19", H, None, "ด่วนมาก ยายอายุ 91 ติดเตียง อยู่บนหลังคากับลูกหลาน รวม 7 คน มา 2 คืนแล้ว",
  dict(adults=7, elderly_ages=[91], flags=["bedridden"], water_level="roof", days_trapped=2)),
 ("H20", H, None, "อยู่คอนโดชั้น 5 ย่านคอหงส์ ปลอดภัยแต่ลงไปไหนไม่ได้ อาหารเหลืออีก 2 วัน ผู้ใหญ่ 3 คน ขอน้ำดื่ม",
  dict(area="คอหงส์", adults=3, needs=["water"])),
 ("X21", "hazard_report", None, "แจ้งเตือน สายไฟแรงสูงขาดลงน้ำ ถนนกาญจนวนิช หน้าแม็คโคร อย่าเดินลุยน้ำแถวนั้น", dict(area="บ้านพรุ")),
 ("X22", "donation_offer", None, "โรงครัวเรามีข้าวต้ม 500 ถ้วย อยากรู้ว่าจุดไหนยังขาดอยู่", {}),
 ("H23", H, None, "บ้านข้างๆ กู้ภัยมารับแล้ว แต่บ้านเรายังไม่มีใครมา! มีเด็ก 9 เดือน น้ำถึงชั้นสอง ซ.ศรีภูวนารถ 6 เขต 8",
  dict(area="เขต 8 หาดใหญ่", children_ages=[0.75], water_level="floor2")),
 ("H24", H, None, "อัปเดต: ยังอยู่ที่เดิมนะคะ คนป่วยฟอกไตที่คลองเตยซอย 1 ตอนนี้หายใจเหนื่อยมาก", dict(area="คลองเตย หาดใหญ่", flags=["dialysis"])),
 ("H25", H, None, "ช่วยด้วยน้ำเข้าบ้านถึงเข่าคนแก่80ปีอยู่บ้านคนเดียวน้ำน้อยซอย3",
  dict(area="น้ำน้อย", adults=1, elderly_ages=[80], water_level="knee")),
 ("H26", H, None, "แจ้งแทนเพื่อนค่ะ เพื่อนติดต่อไม่ได้แล้ว ล่าสุดบอกว่าน้ำถึงอก อยู่กับลูกสองคนอายุ 5 กับ 8 ขวบ คลองแห ใกล้ตลาดน้ำ เบอร์เพื่อน 0812345xxx",
  dict(area="คลองแห", adults=1, children_ages=[5, 8], water_level="chest", contact="0812345xxx")),
 ("H03", H, "H03", "ช่วยแชร์ แม่ลูกอ่อนที่ควนลัง ลูกอายุ 2 อาทิตย์ นมหมด น้ำยังขึ้น", dict(area="ควนลัง", children_ages=[0.04], needs=["milk"])),
 ("X28", "irrelevant", None, "เป็นกำลังใจให้ชาวหาดใหญ่ทุกคนนะ สู้ๆ", {}),
 ("X29", "hazard_report", None, "งูเหลือมตัวใหญ่ลอยมากับน้ำแถวริมคลอง ร.1 เด็กๆ อย่าลงเล่นน้ำ", dict(area="คลองเตย หาดใหญ่")),
 ("H30", H, None, "แม่อายุ 76 เป็นความดันกับเบาหวาน ยาหมด อยู่ชั้น 2 น้ำยังไม่ถึง แต่ชั้นล่างจมแล้ว เพชรเกษม ซอยโรงเรียนกอบกาญจน์ อยู่กัน 2 คน 089-xxx-0091",
  dict(area="ถนนเพชรเกษม", adults=2, elderly_ages=[76], water_level="floor1", needs=["medicine"], contact="089-xxx-0091")),
]

rows = []
for i, (cid, mtype, dup, text, lab) in enumerate(ITEMS, 1):
    r = {"msg_id": f"HM{i:02d}", "timestamp": f"2025-11-25T{8 + i // 4:02d}:{(i * 7) % 60:02d}", "channel": "free_text",
         "text": text, "gt_message_type": "help_request_duplicate" if dup else mtype,
         "gt_case_id": cid if mtype in (H, "status_update_resolved") else None, "gt_duplicate_of_case": dup,
         "gt_area": lab.get("area")}
    if mtype == H:
        e = Extraction(message_type=H, **{k: v for k, v in lab.items()})
        color, reason = priority(e)
        r.update(gt_priority=color, gt_priority_reason=reason, gt_water_level=lab.get("water_level"), gt_adults=lab.get("adults"),
                 gt_children_ages=lab.get("children_ages", []), gt_elderly_ages=lab.get("elderly_ages", []),
                 gt_flags=lab.get("flags", []), gt_needs=lab.get("needs", []), gt_missing_fields=missing_fields(e))
    rows.append(r)

out = ROOT / "backend/data/hard_messages.jsonl"
out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
print(len(rows), "rows ->", out)

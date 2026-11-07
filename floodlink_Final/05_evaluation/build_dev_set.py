"""DEV set (38 hand-written messages) — used while TUNING the model.
The hard set (build_hard_set.py) is only used for the final score, so tuning can't overfit it.
Same labelling approach: facts written by hand, colour + missing fields computed by the shared rules.

Run: python 05_evaluation/build_dev_set.py  -> 05_evaluation/data/dev_messages.jsonl
"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "common"))
from floodcommon.schemas import Extraction            # noqa: E402
from floodcommon.triage import priority, missing_fields  # noqa: E402

H = "help_request"
ITEMS = [
 (H, "พ่อเป็นอัมพฤกษ์ ต้องมีคนพลิกตัวให้ทุกสองชั่วโมง น้ำเข้าบ้านถึงเอวแล้ว อยู่ควนลังซอย 5 กับแม่สองคน", dict(area="ควนลัง", adults=2, flags=["bedridden"], water_level="waist")),
 (H, "คุณตาไตเสื่อม ต้องไปโรงพยาบาลฟอกเลือดวันนี้ แต่รถออกไม่ได้ น้ำท่วมถนนถึงอก บ้านพรุ", dict(area="บ้านพรุ", flags=["dialysis"], water_level="chest")),
 (H, "เมียผมใกล้คลอดแล้ว เริ่มเจ็บท้องถี่ๆ ชั้นล่างน้ำเต็ม ขอเรือด่วน คลองแห", dict(area="คลองแห", flags=["pregnant"], water_level="floor1", needs=["evacuation"])),
 (H, "ลูกชายเพิ่งออกจากโรงพยาบาล ผ่าตัดหัวใจมา ยาเหลือ 2 วัน อยู่ทุ่งเสา น้ำท่วมเข่า", dict(area="ทุ่งเสา", flags=["heart"], water_level="knee", needs=["medicine"])),
 (H, "ป้าโดนตะปูตำเท้า แผลเปื่อยบวมแดง น้ำถึงเอว น้ำน้อย", dict(area="น้ำน้อย", flags=["injured"], water_level="waist")),
 (H, "มีเด็กอ่อนสามเดือนกับแม่ น้ำขึ้นถึงพื้นชั้นสองแล้ว นมหมด คอหงส์ ซ.สังทิศ 3", dict(area="คอหงส์", adults=1, children_ages=[0.25], water_level="floor2", needs=["milk"])),
 (H, "ตาเจ็ดสิบสี่ ยายเจ็ดสิบเอ็ด ติดอยู่บ้านไม้ชั้นเดียว น้ำมิดหน้าต่างชั้นล่างแล้ว ข้าวก็หมด เพชรเกษม ซอย 12", dict(area="ถนนเพชรเกษม", adults=2, elderly_ages=[71, 74], water_level="floor1", needs=["food"])),
 (H, "ผู้ใหญ่ 6 เด็ก 2 คน (5 ขวบ, 8 ขวบ) ปีนขึ้นไปบนดาดฟ้าแล้ว ไม่มีน้ำกิน เขต 8", dict(area="เขต 8 หาดใหญ่", adults=6, children_ages=[5, 8], water_level="roof", needs=["water"])),
 (H, "ไม่มีใครป่วย อาหารมีพอ แค่อยากรู้ว่าจะมีเรือมารับเมื่อไหร่ น้ำถึงเอว อยู่ 3 คน คลองเตยซอย 3", dict(area="คลองเตย หาดใหญ่", adults=3, water_level="waist", needs=["evacuation"])),
 (H, "พี่สาวตาบอดสนิท อยู่คนเดียว น้ำท่วมถึงคอแล้ว ถนนครูจีน", dict(area="ถนนครูจีน", adults=1, flags=["disabled_blind"], water_level="chest")),
 (H, "help please, my uncle is in a wheelchair, water at waist level, Thung Sao", dict(area="ทุ่งเสา", flags=["wheelchair"], water_level="waist")),
 (H, "ลูก 7 เดือนตัวร้อนจัด ไม่มียาลดไข้ น้ำท่วมชั้นล่างหมดแล้ว อยู่ 4 คน น้ำน้อย", dict(area="น้ำน้อย", adults=3, children_ages=[0.58], water_level="floor1", needs=["medicine"])),
 (H, "น้าเป็นเบาหวานกับความดัน อินซูลินหมด อยู่บ้านพรุ น้ำถึงเข่า", dict(area="บ้านพรุ", water_level="knee", needs=["medicine"])),
 (H, "ทั้งบ้านมีห้าคน ไม่มีคนแก่ไม่มีเด็ก น้ำยังแค่ตาตุ่ม แต่ไฟดับ มือถือจะดับ คอหงส์", dict(area="คอหงส์", adults=5, water_level="knee", needs=["power"])),
 (H, "ญาติโทรมาบอกว่าคุณย่า 89 ปี ติดอยู่บ้านคนเดียวที่คลองแห น้ำถึงชั้นสองแล้ว ช่วยไปรับที", dict(area="คลองแห", adults=1, elderly_ages=[89], water_level="floor2", needs=["evacuation"])),
 (H, "สามีถูกกระแสน้ำพัดกระแทกเสาไฟ ซี่โครงน่าจะหัก หายใจแล้วเจ็บ ตอนนี้อยู่บนหลังคาที่ทุ่งเสา", dict(area="ทุ่งเสา", flags=["injured"], water_level="roof")),
 (H, "ด่วน คนท้อง 9 เดือนน้ำคร่ำเดินแล้ว ติดอยู่ในบ้าน น้ำถึงอก ควนลัง", dict(area="ควนลัง", flags=["pregnant"], water_level="chest")),
 (H, "ขออาหารกับน้ำดื่มให้ 12 ชีวิต ติดอยู่ในวัดน้ำน้อยมา 3 วันแล้ว น้ำรอบวัดลึกถึงเอว", dict(area="น้ำน้อย", adults=12, days_trapped=3, water_level="waist", needs=["food", "water"])),
 ("hazard_report", "เตือนภัย! คันกั้นน้ำแถวคลองแหเริ่มรั่ว ชาวบ้านแถวนั้นเตรียมย้ายของขึ้นที่สูง", dict(area="คลองแห")),
 ("hazard_report", "ถนนเพชรเกษมช่วงหน้าห้าง มีหลุมใหญ่อยู่ใต้น้ำ รถกู้ภัยตกไปแล้วคันนึง", dict(area="ถนนเพชรเกษม")),
 ("hazard_report", "จระเข้หลุดจากฟาร์มแถวควนลัง ใครลุยน้ำแถวนั้นระวังตัวด้วย", dict(area="ควนลัง")),
 ("status_update_resolved", "ขอบคุณทีมเรือที่มารับคุณย่าที่คลองแหนะคะ ตอนนี้อยู่บ้านญาติแล้ว", dict(area="คลองแห")),
 ("status_update_resolved", "อัพเดตเคสคนท้องที่ควนลัง คลอดที่โรงพยาบาลเรียบร้อย แม่ลูกปลอดภัย", dict(area="ควนลัง")),
 ("donation_offer", "ใครขาดอาหารแถวคอหงส์ ทักมาได้ ร้านเราทำข้าวแกงแจกได้ 200 ห่อ", {}),
 ("donation_offer", "มีเครื่องปั่นไฟ 2 เครื่องให้ยืม ใครอยากชาร์จแบตมาได้ อยู่หาดใหญ่ใน", {}),
 ("donation_offer", "อาสามีเรือยาง 5 ลำ พร้อมไปช่วยอพยพ ต้องติดต่อใครครับ", {}),
 ("irrelevant", "ช่วยกันแชร์เยอะๆ นะคะ ขอให้น้ำลดไวๆ", {}),
 ("irrelevant", "ปีที่แล้วก็ท่วมแบบนี้ ไม่มีใครแก้อะไรเลย", {}),
 ("irrelevant", "ดูไลฟ์อยู่ สงสารชาวบ้านมาก", {}),
 (H, "ยายนอนป่วยลุกไม่ขึ้นมาหลายเดือน ต้องใช้ออกซิเจน ไฟดับ ถังออกซิเจนใกล้หมด ทุ่งเสา น้ำมิดชั้น 1", dict(area="ทุ่งเสา", flags=["bedridden"], water_level="floor1", needs=["power", "medicine"])),
 (H, "บ้านเลขที่ 22 ซ.คลองเตย 3 มีผู้ใหญ่ 2 เด็ก 1 ขวบ น้ำถึงหน้าอก ขาดนมผง", dict(area="คลองเตย หาดใหญ่", adults=2, children_ages=[1], water_level="chest", needs=["milk"])),
 (H, "ลุงอายุหกสิบแปด พิการแขนขา นั่งรถเข็นตลอด น้ำถึงเอว ควนลัง ซอย 5", dict(area="ควนลัง", elderly_ages=[68], flags=["wheelchair"], water_level="waist")),
 (H, "ตอนนี้น้ำปริ่มหลังคาแล้ว อยู่กันสี่คน ไม่มีอะไรกินมาตั้งแต่เมื่อวาน เขต 8", dict(area="เขต 8 หาดใหญ่", adults=4, days_trapped=1, water_level="roof", needs=["food"])),
 (H, "แม่อายุ 95 ความจำเสื่อม เดินเองไม่ได้ ต้องอุ้ม อยู่ถนนครูจีน น้ำถึงเข่า", dict(area="ถนนครูจีน", elderly_ages=[95], flags=["wheelchair"], water_level="knee")),
 (H, "พี่ชายลื่นล้มหัวฟาดพื้น เลือดออกที่หัว ซึมๆ น้ำถึงเอว ซ.น้ำน้อย 1", dict(area="น้ำน้อย", flags=["injured"], water_level="waist")),
 (H, "อยู่ 3 คนในหอพักชั้น 4 ปลอดภัยดี ขาดแค่น้ำดื่มกับมาม่า คอหงส์", dict(area="คอหงส์", adults=3, needs=["water", "food"])),
 (H, "แม่ลูกอ่อน ลูกเพิ่งเกิดได้ 10 วัน น้ำเริ่มเข้าบ้าน ถึงตาตุ่ม เพชรเกษม", dict(area="ถนนเพชรเกษม", children_ages=[0.03], water_level="knee")),
 (H, "ทุกคนในบ้านโอเค แต่บ้านข้างๆ ยายอายุ 90 ติดเตียง น้ำถึงชั้น 2 ยังไม่มีใครไป คลองแห ซ.2", dict(area="คลองแห", elderly_ages=[90], flags=["bedridden"], water_level="floor2")),
 (H, "เราอยู่บนหลังคา 7 คน มีคนท้องหนึ่งคน มีเด็กเล็ก 2 ขวบ กับ 4 ขวบ ฝนก็ตก หนาวมาก ควนลัง", dict(area="ควนลัง", adults=5, children_ages=[2, 4], flags=["pregnant"], water_level="roof")),
]

rows = []
for i, (mtype, text, lab) in enumerate(ITEMS, 1):
    r = {"msg_id": f"DV{i:02d}", "timestamp": f"2025-11-26T{8 + i // 4:02d}:{(i * 7) % 60:02d}", "channel": "free_text",
         "text": text, "gt_message_type": mtype, "gt_case_id": f"D{i:02d}" if mtype in (H, "status_update_resolved") else None,
         "gt_duplicate_of_case": None, "gt_area": lab.get("area")}
    if mtype == H:
        e = Extraction(message_type=H, **lab)
        color, reason = priority(e)
        r.update(gt_priority=color, gt_priority_reason=reason, gt_water_level=lab.get("water_level"), gt_adults=lab.get("adults"),
                 gt_children_ages=lab.get("children_ages", []), gt_elderly_ages=lab.get("elderly_ages", []),
                 gt_flags=lab.get("flags", []), gt_needs=lab.get("needs", []), gt_missing_fields=missing_fields(e))
    rows.append(r)
out = ROOT / "05_evaluation/data/dev_messages.jsonl"
out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
print(len(rows), "rows ->", out)

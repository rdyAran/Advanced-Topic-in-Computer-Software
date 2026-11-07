from agent.splitter import split_cases, looks_multi


class FakeLLM:
    def split_cases(self, text):
        return ["บ้านป้าแดง ติดอยู่ น้ำน้อย โทร 081-xxx-1111", "บ้านลุงดำ ติดอยู่ น้ำน้อย โทร 089-xxx-2222"]


def test_markers_inline_paragraphs():
    assert split_cases("เคส 1 ยายติดเตียง น้ำถึงชั้น 2 ทุ่งเสา\nเคส 2 คนท้อง น้ำถึงอก ทุ่งเสา ซ.2")["method"] == "rules:marker"
    r = split_cases("บ้านเลขที่ 5 ซ.ควนลัง 7 ผู้ใหญ่ 3 คน น้ำถึงเอว อีกบ้าน บ้านเลขที่ 9 ซอยเดียวกัน ตาอายุ 90 ติดเตียง")
    assert len(r["segments"]) == 2 and "ควนลัง" in r["segments"][1]       # area inherited
    assert len(split_cases("บ้านพรุ ซ.5 ผู้ใหญ่ 4 คน น้ำถึงเอว\n\nถ.กาญจนวนิช หลังวัด เด็ก 9 เดือน น้ำท่วมชั้นล่าง")["segments"]) == 2


def test_single_case_not_split():
    assert len(split_cases("ช่วยด้วยค่ะ ยายอายุ 85 ติดเตียง น้ำถึงชั้น 2 คอหงส์ โทร 081-xxx-2222")["segments"]) == 1


def test_llm_used_only_when_rules_cannot_split_but_looks_multi():
    t = "บ้านป้าแดงกับบ้านลุงดำติดอยู่ทั้งสองหลัง โทร 081-xxx-1111 หรือ 089-xxx-2222 น้ำน้อย"
    assert looks_multi(t)
    assert split_cases(t, FakeLLM())["method"] == "llm"
    assert split_cases(t)["note"]                    # no LLM -> tell the user how to format it


def test_each_line_with_its_own_place_is_a_case():
    t = """ฝากแชร์ด่วน คลองแห โทร 081-234-5678
บ้านเลขที่ 12 ซ.คลองแห 2 ยายอายุ 85 ติดเตียง น้ำถึงชั้น 2
บ้านเลขที่ 40 ซ.คลองแห 4 ผู้ใหญ่ 3 คน เด็ก 2 ขวบ น้ำถึงอก ไม่มีอาหาร
ซ.คลองแห 6 ลุงฟอกไต ขอเรือ พิกัด 7.0301, 100.4862"""
    r = split_cases(t)
    assert r["method"] == "rules:lines" and len(r["segments"]) == 3
    assert "ฟอกไต" in r["segments"][2] and "ฟอกไต" not in r["segments"][1]     # dialysis stays with soi 6, not house 40
    assert all("081-234-5678" in s for s in r["segments"])                        # reporter phone shared


def test_detail_lines_of_one_house_are_not_split():
    t = "บ้านเลขที่ 12 ซ.คลองแห 2\nยายอายุ 85 ติดเตียง\nน้ำถึงชั้น 2 แล้ว\nบ้านเลขที่ 12 ตอนนี้แบตจะหมด ยายเริ่มไม่ไหว"
    assert len(split_cases(t)["segments"]) == 1
    t2 = "ซ.ควนลัง 7 บ้านเลขที่ 5 ยายติดเตียง น้ำถึงชั้น 2\nซ.ควนลัง 7 ตอนนี้น้ำขึ้นอีก ยายเริ่มหนาว"
    assert len(split_cases(t2)["segments"]) == 1

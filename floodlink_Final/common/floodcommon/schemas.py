"""Data shapes shared by agents, API and evaluation."""
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class MessageType(str, Enum):
    help_request = "help_request"
    hazard_report = "hazard_report"
    status_update_resolved = "status_update_resolved"
    donation_offer = "donation_offer"
    irrelevant = "irrelevant"


class WaterLevel(str, Enum):
    knee = "knee"
    waist = "waist"
    chest = "chest"
    floor1 = "floor1"
    floor2 = "floor2"
    roof = "roof"


class Flag(str, Enum):
    bedridden = "bedridden"
    dialysis = "dialysis"
    heart = "heart"
    pregnant = "pregnant"
    injured = "injured"
    disabled_blind = "disabled_blind"
    wheelchair = "wheelchair"
    # added for the WangchanBERTa model trained on real Hat Yai messages (04_flood_nlp_model/floodwcb.py)
    in_labor = "in_labor"
    sick_now = "sick_now"
    chronic_illness = "chronic_illness"
    cannot_swim = "cannot_swim"


class Need(str, Enum):
    food = "food"
    water = "water"
    milk = "milk"
    medicine = "medicine"
    evacuation = "evacuation"
    power = "power"
    medical = "medical"


class Extraction(BaseModel):
    """What the Intake Agent pulls out of one raw message. Only facts stated in the text."""
    message_type: MessageType
    area: Optional[str] = Field(None, description="ชื่อพื้นที่/ตำบล/ถนนหลัก เช่น คอหงส์, ถนนครูจีน")
    street: Optional[str] = Field(None, description="ซอยหรือถนน")
    landmark: Optional[str] = Field(None, description="จุดสังเกต เช่น ใกล้วัด, ปากซอยมีโชว์รูมรถ")
    house_no: Optional[str] = None
    adults: Optional[int] = Field(None, description="จำนวนผู้ใหญ่ รวมผู้สูงอายุ ไม่รวมเด็ก")
    children_ages: list[float] = Field(default_factory=list, description="อายุเด็กเป็นปี เช่น 9 เดือน = 0.75")
    elderly_ages: list[int] = Field(default_factory=list, description="อายุผู้สูงอายุ 60 ปีขึ้นไป")
    building_floors: Optional[int] = Field(None, description="ที่พักมีกี่ชั้น: บ้านชั้นเดียว = 1, บ้าน 2 ชั้น = 2, ตึก/อาคาร 3 ชั้นขึ้นไป = 3 (ไม่บอก = null)")
    children_count: Optional[int] = Field(None, description="จำนวนเด็ก เมื่อบอกเป็นจำนวนคน เช่น 'เด็ก 12' 'เด็ก 3 คน' (ไม่ใช่อายุ)")
    elderly_count: Optional[int] = Field(None, description="จำนวนผู้สูงอายุ เมื่อบอกเป็นจำนวนคน เช่น 'ผู้สูงอายุ 5' (นับรวมอยู่ใน adults ด้วย)")
    flags: list[Flag] = Field(default_factory=list)
    water_level: Optional[WaterLevel] = None
    days_trapped: Optional[int] = None
    needs: list[Need] = Field(default_factory=list)
    contact: Optional[str] = None
    lost_contact: bool = Field(False, description="ญาติติดต่อผู้ประสบภัยไม่ได้แล้ว / แบตหมด / ขาดการติดต่อ")
    summary: str = Field("", description="สรุปสั้น 1 บรรทัดภาษาไทยสำหรับเจ้าหน้าที่")
    # Set only by our own model (never asked from an LLM, see LLM_HIDDEN): the model's colour when it is more urgent
    # than the fact-based rules could tell (e.g. "มีเด็กทารก", "ตัวซีด"); triage.priority() takes the more urgent one.
    priority_hint: Optional[str] = None
    priority_hint_reason: Optional[str] = None


LLM_HIDDEN = {"priority_hint", "priority_hint_reason"}     # removed from the JSON schema sent to Gemini / Groq


class IncomingMessage(BaseModel):
    channel: str = "web_form"
    text: str
    timestamp: Optional[str] = None
    photos: list[str] = Field(default_factory=list, description="รูปแนบ (data:image/jpeg;base64,...) สูงสุด 4 รูป")
    no_training: bool = Field(False, description="ผู้แจ้งไม่ยินยอมให้ใช้ข้อความนี้ปรับปรุง AI")


class CaseUpdate(BaseModel):
    status: Optional[str] = None          # new | verified | assigned | in_progress | resolved
    assigned_team: Optional[str] = None
    priority: Optional[str] = None        # human override

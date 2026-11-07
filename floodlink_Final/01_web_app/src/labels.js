export const PRIORITY = {
  red: { label: 'แดง · วิกฤต', color: '#d93025' },
  orange: { label: 'ส้ม · เร่งด่วน', color: '#f28b0c' },
  yellow: { label: 'เหลือง · รอได้', color: '#e0b400' },
  green: { label: 'เขียว · ไม่เร่งด่วน', color: '#1e8e3e' },
}
export const STATUS = {
  new: 'ใหม่', verified: 'ตรวจแล้ว', assigned: 'มีทีมรับ', in_progress: 'กำลังช่วย', resolved: 'ปิดเคส',
}
export const FLAGS = {
  bedridden: 'ติดเตียง', dialysis: 'ฟอกไต', heart: 'โรคหัวใจ', pregnant: 'ตั้งครรภ์',
  injured: 'บาดเจ็บ', disabled_blind: 'ผู้พิการ', wheelchair: 'เดินลำบาก/รถเข็น',
  in_labor: 'กำลังคลอด', sick_now: 'ป่วยหนักตอนนี้', chronic_illness: 'โรคประจำตัว', cannot_swim: 'ว่ายน้ำไม่เป็น',
}
export const NEEDS = {
  food: 'อาหาร', water: 'น้ำดื่ม', milk: 'นมเด็ก', medicine: 'ยา', evacuation: 'อพยพ/เรือ', power: 'ไฟ/แบต', medical: 'แพทย์/รถพยาบาล',
}
export const WATER = {
  knee: 'เข่า', waist: 'เอว', chest: 'อก', floor1: 'มิดชั้น 1', floor2: 'ถึงชั้น 2', roof: 'บนหลังคา',
}
export const MISSING = { area: 'ตำแหน่ง', people_count: 'จำนวนคน', water_level: 'ระดับน้ำ', contact: 'เบอร์ติดต่อ' }
export const CHANNEL = {
  web_form: 'เว็บฟอร์ม', facebook_page: 'Facebook', line_group: 'LINE', phone_transcript: 'โทรศัพท์', traffy: 'Traffy Fondue',
  fb_comment: 'คอมเมนต์เพจ FB', fb_post: 'โพสต์บนเพจ FB', fb_messenger: 'Messenger', chatbot: 'แชทบอท',
}
export const CLOSE_REASON = { rescued: 'ช่วยแล้ว', duplicate: 'เคสซ้ำ', not_found: 'ไปแล้วไม่พบ', self_safe: 'ปลอดภัยเอง' }
export const ROLE = { rescuer: 'หัวหน้าชุด', coordinator: 'เจ้าหน้าที่ศูนย์ประสาน', admin: 'ผู้ดูแลระบบ' }
export const STEPS = ['new', 'verified', 'assigned', 'in_progress', 'resolved']
export const TEAM_STATUS = { available: { label: 'ว่าง', color: '#1e8e3e' }, busy: { label: 'กำลังช่วย', color: '#f28b0c' }, offline: { label: 'พัก/ออฟไลน์', color: '#6b7280' } }
// everyone in a case: adults include the elderly; children = listed ages or a head count, whichever is bigger
export const peopleText = (e) => {
  if (!e) return ''
  const kids = Math.max((e.children_ages || []).length, e.children_count || 0)
  const oldN = Math.max((e.elderly_ages || []).length, e.elderly_count || 0)
  const adults = e.adults ?? (oldN || null)
  const total = (adults || 0) + kids
  const parts = [adults != null && `ผู้ใหญ่ ${adults}${oldN ? ` (ผู้สูงอายุ ${(e.elderly_ages || []).length ? e.elderly_ages.join(', ') + ' ปี' : oldN})` : ''}`,
    kids && `เด็ก ${kids}${(e.children_ages || []).length ? ` (${e.children_ages.map((a) => (a < 1 ? `${Math.round(a * 12)} เดือน` : `${a} ขวบ`)).join(', ')})` : ''}`].filter(Boolean)
  return total ? `รวม ${total} คน · ${parts.join(' · ')}` : ''
}
export const FLOORS = { 1: 'บ้านชั้นเดียว', 2: 'บ้าน 2 ชั้น', 3: 'ตึก/อาคาร 3 ชั้นขึ้นไป' }
export const TEAM_KIND = { gov: 'หน่วยงานรัฐ', volunteer: 'อาสา/มูลนิธิ' }
export const ago = (ts) => {
  if (!ts) return 'ไม่เคย'
  const m = Math.round((Date.now() - new Date(ts).getTime()) / 60000)
  return m < 1 ? 'เมื่อกี้' : m < 60 ? `${m} นาทีก่อน` : m < 1440 ? `${Math.round(m / 60)} ชม.ก่อน` : `${Math.round(m / 1440)} วันก่อน`
}

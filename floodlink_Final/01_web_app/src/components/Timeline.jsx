import { useState } from 'react'
import { api } from '../api.js'
import { STATUS, CLOSE_REASON, PRIORITY } from '../labels.js'

const t = (s) => new Date(s).toLocaleString('th-TH', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
const say = (a) => {
  const d = a.detail || {}
  switch (a.action) {
    case 'created': return 'สร้างเคสจากรายงาน'
    case 'merged': return 'มีรายงานซ้ำ รวมเข้าเคสนี้'
    case 'followup': return `ส่งข้อมูลเพิ่ม${d.photos ? ` + รูป ${d.photos}` : ''}`
    case 'note': return `บันทึก: ${d.text || '(รูป)'}`
    case 'assign': return d.to ? `มอบหมาย ${d.to}${d.from ? ` (เดิม ${d.from})` : ''}` : 'ยกเลิกทีม'
    case 'status': case 'reopen': return `${a.action === 'reopen' ? 'เปิดเคสใหม่ ' : ''}${STATUS[d.from] || d.from} → ${STATUS[d.to] || d.to}`
    case 'close': return `ปิดเคส: ${CLOSE_REASON[d.close_reason] || d.close_reason}`
    case 'priority': return `ปรับสี ${PRIORITY[d.from]?.label || d.from} → ${PRIORITY[d.to]?.label || d.to}`
    case 'correct_ai': return 'แก้ผล AI (เก็บเป็นข้อมูลเทรน)'
    case 'accept': return `✅ ${d.team} ตอบรับเคส`
    case 'claim': return `🙋 ${d.team} ขอรับเคสเอง`
    case 'decline': return `✋ ${d.team} ไปไม่ได้: ${d.reason}`
    case 'merge': return `🔗 รวมรายงานจาก ${d.from} (${d.reports} รายงาน)`
    case 'not_duplicate': return `ยืนยันว่าไม่ซ้ำกับ ${d.was || '-'}`
    default: return a.action
  }
}

// who did what on this case (audit log) — staff only
export default function Timeline({ caseId }) {
  const [rows, setRows] = useState(null)
  const [open, setOpen] = useState(false)
  const toggle = async () => {
    const n = !open; setOpen(n)
    if (n) setRows(await api.timeline(caseId).catch(() => []))
  }
  return (
    <div className="orig" onClick={(e) => e.stopPropagation()}>
      <button className="orig-toggle" onClick={toggle} aria-expanded={open}>{open ? '▾' : '▸'} 🕒 ประวัติเคส</button>
      {open && (
        <ul className="audit">
          {!rows && <li className="muted small">กำลังโหลด…</li>}
          {rows?.map((a) => <li key={a.id}><span className="muted small">{t(a.ts)}</span> <b>{a.actor}</b> {say(a)}</li>)}
        </ul>
      )}
    </div>
  )
}

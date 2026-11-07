import { useState } from 'react'
import { api } from '../api.js'
import { CHANNEL, FLAGS, NEEDS, WATER, peopleText } from '../labels.js'
import PhotoStrip from './PhotoStrip.jsx'

const TYPE = { help_request: 'ขอความช่วยเหลือ', status_update_resolved: 'แจ้งว่าได้รับการช่วยแล้ว', hazard_report: 'แจ้งจุดอันตราย',
  offer_help: 'เสนอความช่วยเหลือ', other: 'อื่น ๆ' }
const time = (t) => (t ? new Date(t).toLocaleString('th-TH', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '')

// highlight the lines of the original post that became THIS case
// (the splitter may append shared info such as the reporter's phone, so match line by line)
const partLines = (raw, part) => {
  if (!part || raw === part) return null
  const p = part.replace(/\s+/g, ' ')
  const hit = raw.split('\n').map((l) => { const t = l.trim().replace(/\s+/g, ' '); return t.length > 3 && p.includes(t) })
  return hit.some(Boolean) ? hit : null
}
function Raw({ raw, part }) {
  const hit = partLines(raw, part)
  if (!hit) return <div className="raw-text">{raw}</div>
  return <div className="raw-text">{raw.split('\n').map((l, i) => <div key={i}>{hit[i] ? <mark>{l}</mark> : l || '\u00a0'}</div>)}</div>
}

function AiRead({ m }) {
  const e = m.extraction || {}
  const people = peopleText(e)
  const row = (k, v) => <div className="ai-row"><span>{k}</span><b>{v || <i className="muted">— ไม่พบ —</i>}</b></div>
  return (
    <div className="ai-read">
      <div className="ai-read-head">🤖 AI อ่านได้ว่า <span className="muted small">
        ({m.provider || 'ไม่ทราบ'}{m.confidence != null ? ` · มั่นใจ ${Math.round(m.confidence * 100)}%` : ''}{m.escalated ? ' · ส่งต่อ LLM' : ''})</span></div>
      {row('ประเภท', TYPE[e.message_type] || e.message_type)}
      {row('พื้นที่', [e.area, e.street, e.house_no && `บ้านเลขที่ ${e.house_no}`, e.landmark].filter(Boolean).join(' · ')
        || (/maps\.app\.goo\.gl|google\.[a-z.]+\/maps|\d+\.\d{3,}\s*,\s*\d+\.\d{3,}/.test(m.raw_text || m.text || '') ? '📍 ตามลิงก์/พิกัดในข้อความ (ระบบใช้นำทาง)' : ''))}
      {row('จำนวนคน', people)}
      {row('กลุ่มเปราะบาง', (e.flags || []).map((f) => FLAGS[f] || f).join(', '))}
      {row('ระดับน้ำ', WATER[e.water_level])}
      {row('ต้องการ', (e.needs || []).map((n) => NEEDS[n] || n).join(', '))}
      {row('เบอร์โทร', e.contact)}
    </div>
  )
}

function Feedback({ caseId, messageId }) {
  const [open, setOpen] = useState(false)
  const [note, setNote] = useState('')
  const [state, setState] = useState('')
  if (state === 'ok') return <span className="fb-ok">✓ บันทึกแล้ว ทีมจะใช้ปรับปรุง AI</span>
  if (!open) return <button className="ghost warn-btn" onClick={() => setOpen(true)}>⚠️ AI อ่านผิด</button>
  const send = async () => {
    if (!note.trim()) return
    setState('busy')
    try { await api.aiFeedback(caseId, { note, message_id: messageId }); setState('ok') } catch (e) { setState('ผิดพลาด: ' + e.message) }
  }
  return (
    <div className="fb-form">
      <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} autoFocus
        placeholder="ผิดตรงไหน เช่น ข้อความบอกว่ามีเด็ก 2 คน แต่ AI ไม่เห็น / พื้นที่ผิด" />
      <div className="row">
        {state && state !== 'busy' && <span className="error small">{state}</span>}
        <button className="ghost" onClick={() => setOpen(false)}>ยกเลิก</button>
        <button onClick={send} disabled={state === 'busy' || !note.trim()}>ส่ง</button>
      </div>
    </div>
  )
}

export default function OriginalMessages({ caseId, count = 1 }) {
  const [open, setOpen] = useState(false)
  const [msgs, setMsgs] = useState(null)
  const [err, setErr] = useState('')
  const toggle = async () => {
    const next = !open; setOpen(next)
    if (next) {                      // always reload: new reports may have been merged into this case
      try { setMsgs((await api.caseDetail(caseId)).messages || []); setErr('') } catch (e) { setErr(e.message) }
    }
  }
  const copy = (t) => navigator.clipboard?.writeText(t)

  return (
    <div className="orig" onClick={(e) => e.stopPropagation()}>
      <button className="orig-toggle" onClick={toggle} aria-expanded={open}>
        {open ? '▾' : '▸'} 📄 ข้อความต้นฉบับ{count > 1 ? ` (${count} รายงาน)` : ''}
      </button>
      {open && (
        <div className="orig-body">
          {err && <div className="error small">โหลดไม่ได้: {err}</div>}
          {!msgs && !err && <div className="muted small">กำลังโหลด…</div>}
          {msgs?.map((m, i) => (
            <div className="orig-item" key={m.id}>
              <div className="orig-meta">
                {msgs.length > 1 && <b>รายงานที่ {i + 1}</b>}
                <span>{time(m.received_at)}</span>
                <span className="chip">{CHANNEL[m.channel] || m.channel}</span>
                {m.author && <span>โดย {m.author}</span>}
                {m.source_url && <a href={m.source_url} target="_blank" rel="noopener noreferrer">🔗 ดูโพสต์ต้นทาง</a>}
              </div>
              {m.was_split && <div className="split-note">✂️ ข้อความนี้มี {m.n_cases} เคส — <mark>ส่วนที่ไฮไลต์</mark> คือส่วนที่เป็นเคสนี้</div>}
              <Raw raw={m.raw_text} part={m.text} />
              {m.photos?.length > 0 && <PhotoStrip photos={m.photos} />}
              {m.was_split && !partLines(m.raw_text, m.text) && (
                <div className="raw-part"><span className="muted small">ส่วนที่ AI ใช้เป็นเคสนี้:</span><div>{m.text}</div></div>
              )}
              <AiRead m={m} />
              <div className="orig-actions">
                <button className="ghost" onClick={() => copy(m.raw_text)}>📋 คัดลอก</button>
                <Feedback caseId={caseId} messageId={m.id} />
              </div>
            </div>
          ))}
          {msgs?.length === 0 && <div className="muted small">ไม่มีข้อความต้นฉบับ (เคสจากระบบเวอร์ชันเก่า)</div>}
        </div>
      )}
    </div>
  )
}

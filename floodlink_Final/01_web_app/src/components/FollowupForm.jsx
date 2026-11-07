import { useState } from 'react'
import { api } from '../api.js'
import { MISSING } from '../labels.js'
import { MAX_PHOTOS, shrinkPhoto } from '../photos.js'

const HINT = {
  area: 'ตำแหน่ง: บ้านเลขที่ ซอย ถนน จุดสังเกต หรือกด 📍 ส่งพิกัด',
  people_count: 'จำนวนคน: ผู้ใหญ่กี่คน เด็ก/ผู้สูงอายุอายุเท่าไหร่',
  water_level: 'ระดับน้ำ: เข่า / เอว / อก / ชั้น 1 / ชั้น 2 / หลังคา',
  contact: 'เบอร์ติดต่อกลับ',
}

// "ส่งข้อมูลเพิ่ม" for a case that already exists: goes straight into THIS case (no new case, no duplicate guess).
// track = the reporter's private token (no login); without it the staff endpoint is used (coordinator after a call-back)
export default function FollowupForm({ caseId, missing = [], onDone, compact = false, track = null }) {
  const [open, setOpen] = useState(!compact)
  const [text, setText] = useState('')
  const [photos, setPhotos] = useState([])
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [left, setLeft] = useState(missing)
  const [done, setDone] = useState(0)

  if (!open) return <button type="button" className="ghost" onClick={(e) => { e.stopPropagation(); setOpen(true) }}>➕ เพิ่มข้อมูล</button>

  const addLocation = () => {
    if (!navigator.geolocation) return setMsg('เบราว์เซอร์นี้ไม่รองรับ GPS')
    setMsg('กำลังหาตำแหน่ง…')
    navigator.geolocation.getCurrentPosition(
      (p) => { setText((t) => (t ? t.trimEnd() + ' ' : '') + `พิกัด ${p.coords.latitude.toFixed(6)}, ${p.coords.longitude.toFixed(6)}`); setMsg('') },
      (err) => setMsg('หาตำแหน่งไม่ได้: ' + err.message), { enableHighAccuracy: true, timeout: 10000 })
  }
  const addPhotos = async (e) => {
    const files = [...(e.target.files || [])].slice(0, MAX_PHOTOS - photos.length); e.target.value = ''
    const out = []
    for (const f of files) { try { out.push(await shrinkPhoto(f)) } catch (err) { setMsg(err.message) } }
    setPhotos((p) => [...p, ...out].slice(0, MAX_PHOTOS))
  }
  const send = async () => {
    if (!text.trim() && !photos.length) return
    setBusy(true); setMsg('')
    try {
      const ph = photos.map((p) => p.dataUrl)
      const r = track ? await api.trackFollowup(track, caseId, text, ph) : await api.followup(caseId, text, ph)
      setText(''); setPhotos([]); setLeft(r.missing_fields || []); setDone((n) => n + 1); onDone?.(r)
    } catch (err) { setMsg('ส่งไม่สำเร็จ: ' + err.message) } finally { setBusy(false) }
  }

  return (
    <div className="followup-form" onClick={(e) => e.stopPropagation()}>
      <div className="fu-head">
        <b>➕ ส่งข้อมูลเพิ่มให้เคส <code>{caseId}</code></b>
        {compact && <button type="button" className="link" onClick={() => setOpen(false)}>ปิด</button>}
      </div>
      {done > 0 && <div className="fu-ok">✓ อัปเดตเคสแล้ว{left.length ? ' — ยังขาด ' + left.map((m) => MISSING[m]).join(', ') : ' — ข้อมูลครบแล้ว ขอบคุณค่ะ'}</div>}
      {left.length > 0 && (
        <ul className="fu-missing">{left.map((m) => <li key={m}>{HINT[m] || MISSING[m]}</li>)}</ul>
      )}
      <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)}
        placeholder={left.includes('area') ? 'เช่น ซ.ควนลัง 7 บ้านเลขที่ 12 ตรงข้ามร้านข้าวมันไก่' : 'พิมพ์ข้อมูลเพิ่ม เช่น ระดับน้ำ เบอร์ติดต่อ อาการผู้ป่วย'} />
      {photos.length > 0 && (
        <div className="photo-pick">
          {photos.map((p, i) => (
            <div className="thumb-wrap" key={i}><img src={p.dataUrl} alt={`รูปที่ ${i + 1}`} />
              <button type="button" className="thumb-x" onClick={() => setPhotos((x) => x.filter((_, k) => k !== i))} aria-label="ลบรูป">✕</button></div>
          ))}
        </div>
      )}
      <div className="row fu-row">
        <button type="button" className="ghost" onClick={addLocation}>📍 ตำแหน่งปัจจุบัน</button>
        <label className={`ghost photo-btn ${photos.length >= MAX_PHOTOS ? 'disabled' : ''}`}>📷 รูป
          <input type="file" accept="image/*" multiple hidden disabled={photos.length >= MAX_PHOTOS} onChange={addPhotos} /></label>
        {msg && <span className="muted small">{msg}</span>}
        <span className="spacer" />
        <button type="button" className="primary" disabled={busy || (!text.trim() && !photos.length)} onClick={send}>
          {busy ? 'กำลังส่ง…' : 'ส่งข้อมูลเพิ่ม'}</button>
      </div>
    </div>
  )
}

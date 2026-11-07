import { useState } from 'react'
import { api } from '../api.js'
import { MAX_PHOTOS, shrinkPhoto } from '../photos.js'

// progress note from a rescue team / officer: kept on the case, NOT read by the AI (does not change flags or colour)
export default function NoteForm({ caseId, onDone, label = '📝 บันทึก/รูปจากทีม' }) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [photos, setPhotos] = useState([])
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  if (!open) return <button type="button" className="ghost" onClick={(e) => { e.stopPropagation(); setOpen(true) }}>{label}</button>
  const addPhotos = async (e) => {
    const files = [...(e.target.files || [])].slice(0, MAX_PHOTOS - photos.length); e.target.value = ''
    const out = []
    for (const f of files) { try { out.push(await shrinkPhoto(f)) } catch (err) { setMsg(err.message) } }
    setPhotos((p) => [...p, ...out].slice(0, MAX_PHOTOS))
  }
  const send = async () => {
    setBusy(true); setMsg('')
    try { await api.note(caseId, text, photos.map((p) => p.dataUrl)); setText(''); setPhotos([]); setMsg('✓ บันทึกแล้ว'); onDone?.() }
    catch (err) { setMsg('ไม่สำเร็จ: ' + err.message) } finally { setBusy(false) }
  }
  return (
    <div className="followup-form note-form" onClick={(e) => e.stopPropagation()}>
      <div className="fu-head"><b>{label}</b><button type="button" className="link" onClick={() => setOpen(false)}>ปิด</button></div>
      <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="เช่น ถึงแล้ว น้ำเชี่ยว เข้าทางหลังวัด / รับคนออกมาแล้ว 3 คน เหลือ 1" />
      {photos.length > 0 && <div className="photo-pick">{photos.map((p, i) => <div className="thumb-wrap" key={i}><img src={p.dataUrl} alt={`รูปที่ ${i + 1}`} /></div>)}</div>}
      <div className="row fu-row">
        <label className="ghost photo-btn">📷 รูป<input type="file" accept="image/*" capture="environment" multiple hidden onChange={addPhotos} /></label>
        {msg && <span className="small">{msg}</span>}
        <span className="spacer" />
        <button type="button" className="primary" disabled={busy || (!text.trim() && !photos.length)} onClick={send}>{busy ? 'กำลังบันทึก…' : 'บันทึก'}</button>
      </div>
    </div>
  )
}

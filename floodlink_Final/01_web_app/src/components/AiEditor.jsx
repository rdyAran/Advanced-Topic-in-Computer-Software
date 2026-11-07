import { useState } from 'react'
import { api } from '../api.js'
import { FLAGS, NEEDS, WATER, PRIORITY } from '../labels.js'

// officer fixes what the AI read. Saved on the case AND as a labelled example for the next training round.
export default function AiEditor({ c, onDone }) {
  const [open, setOpen] = useState(false)
  const [f, setF] = useState(null)
  const [msg, setMsg] = useState('')
  const start = (e) => {
    e.stopPropagation()
    setF({ flags: [...c.flags], needs: [...c.needs], water_level: c.water_level || '', adults: c.adults ?? '', priority: '' }); setOpen(true)
  }
  if (!open) return <button className="ghost" onClick={start} title="แก้กลุ่มเปราะบาง สิ่งที่ต้องการ ระดับน้ำ — ใช้เทรนโมเดลรอบหน้า">✏️ แก้ผล AI</button>
  const tog = (k, v) => setF((x) => ({ ...x, [k]: x[k].includes(v) ? x[k].filter((y) => y !== v) : [...x[k], v] }))
  const save = async () => {
    const body = { flags: f.flags, needs: f.needs, water_level: f.water_level || null }
    if (f.adults !== '') body.adults = Number(f.adults)
    if (f.priority) body.priority = f.priority
    try { await api.correctAi(c.id, body); setOpen(false); onDone?.() } catch (e) { setMsg(e.message) }
  }
  return (
    <div className="ai-editor" onClick={(e) => e.stopPropagation()}>
      <div className="fu-head"><b>✏️ แก้สิ่งที่ AI อ่าน — เคส {c.id}</b><button className="link" onClick={() => setOpen(false)}>ยกเลิก</button></div>
      <fieldset><legend>กลุ่มเปราะบาง</legend>
        {Object.entries(FLAGS).map(([k, v]) => <label key={k} className="check"><input type="checkbox" checked={f.flags.includes(k)} onChange={() => tog('flags', k)} />{v}</label>)}
      </fieldset>
      <fieldset><legend>สิ่งที่ต้องการ</legend>
        {Object.entries(NEEDS).map(([k, v]) => <label key={k} className="check"><input type="checkbox" checked={f.needs.includes(k)} onChange={() => tog('needs', k)} />{v}</label>)}
      </fieldset>
      <div className="row">
        <label>ระดับน้ำ <select value={f.water_level} onChange={(e) => setF({ ...f, water_level: e.target.value })}>
          <option value="">— ไม่ทราบ —</option>{Object.entries(WATER).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label>ผู้ใหญ่ <input type="number" min="0" max="200" value={f.adults} onChange={(e) => setF({ ...f, adults: e.target.value })} style={{ width: 70 }} /></label>
        <label>สี <select value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}>
          <option value="">ให้กฎคำนวณใหม่</option>{Object.entries(PRIORITY).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</select></label>
      </div>
      {msg && <div className="error small">{msg}</div>}
      <div className="row"><span className="muted small">บันทึกแล้วจะถูกใช้เป็นข้อมูลเทรนรอบหน้า (ผู้ดูแลระบบ export ได้)</span><span className="spacer" /><button className="primary" onClick={save}>บันทึก</button></div>
    </div>
  )
}

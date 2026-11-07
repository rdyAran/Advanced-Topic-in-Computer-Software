import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { ROLE } from '../labels.js'

const t = (s) => (s ? new Date(s).toLocaleString('th-TH', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—')
const EMPTY = { username: '', display_name: '', role: 'rescuer', team: '', password: '' }

function Users() {
  const [rows, setRows] = useState([])
  const [f, setF] = useState(EMPTY)
  const [msg, setMsg] = useState('')
  const load = useCallback(() => api.users().then(setRows).catch((e) => setMsg(e.message)), [])
  useEffect(() => { load() }, [load])
  const create = async (e) => {
    e.preventDefault()
    try { await api.createUser({ ...f, team: f.role === 'rescuer' ? f.team : null }); setF(EMPTY); setMsg('✓ สร้างบัญชีแล้ว'); load() } catch (x) { setMsg(x.message) }
  }
  const patch = async (u, body, confirmText) => {
    if (confirmText && !confirm(confirmText)) return
    try { await api.updateUser(u.id, body); load() } catch (x) { alert(x.message) }
  }
  const resetPw = (u) => {
    const pw = prompt(`รหัสผ่านใหม่ของ ${u.username} (8 ตัวขึ้นไป) — บอกเจ้าของบัญชีทางช่องทางส่วนตัว`)
    if (pw) patch(u, { password: pw })
  }
  return (
    <section className="card">
      <h2>บัญชีผู้ใช้</h2>
      <div className="table-wrap">
        <table className="area-table">
          <thead><tr><th>ชื่อผู้ใช้</th><th>ชื่อที่แสดง</th><th>บทบาท</th><th>ทีม</th><th>เข้าล่าสุด</th><th>สถานะ</th><th /></tr></thead>
          <tbody>
            {rows.map((u) => (
              <tr key={u.id} className={u.active ? '' : 'muted'}>
                <td><code>{u.username}</code></td><td>{u.display_name}</td>
                <td><select value={u.role} onChange={(e) => patch(u, { role: e.target.value, ...(e.target.value === 'rescuer' && !u.team ? { team: prompt('ชื่อทีม') || '' } : {}) })}>
                  {Object.entries(ROLE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></td>
                <td>{u.role === 'rescuer' ? <button className="link" onClick={() => { const x = prompt('ชื่อทีม', u.team || ''); if (x) patch(u, { team: x }) }}>{u.team || '—'}</button> : '—'}</td>
                <td className="small">{t(u.last_login)}</td>
                <td>{u.active ? 'ใช้งาน' : 'ปิดแล้ว'}</td>
                <td className="row">
                  <button className="ghost" onClick={() => resetPw(u)}>🔑 ตั้งรหัสใหม่</button>
                  {u.active
                    ? <button className="ghost warn-btn" onClick={() => patch(u, { active: false }, `ปิดบัญชี ${u.username}? (ออกจากระบบทันที)`)}>ปิดบัญชี</button>
                    : <button className="ghost" onClick={() => patch(u, { active: true })}>เปิดใช้</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <form className="user-form" onSubmit={create}>
        <b>➕ เพิ่มบัญชี</b>
        <input placeholder="ชื่อผู้ใช้ (a-z 0-9)" value={f.username} onChange={(e) => setF({ ...f, username: e.target.value.toLowerCase() })} />
        <input placeholder="ชื่อที่แสดง" value={f.display_name} onChange={(e) => setF({ ...f, display_name: e.target.value })} />
        <select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>{Object.entries(ROLE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        {f.role === 'rescuer' && <input placeholder="ชื่อทีม เช่น ทีมเรือ 3" value={f.team} onChange={(e) => setF({ ...f, team: e.target.value })} />}
        <input type="password" placeholder="รหัสผ่านเริ่มต้น (8+)" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} autoComplete="new-password" />
        <button className="primary" disabled={!f.username || f.password.length < 8}>สร้าง</button>
        {msg && <span className="small">{msg}</span>}
      </form>
    </section>
  )
}

function System() {
  const [s, setS] = useState(null)
  useEffect(() => { api.system().then(setS).catch(() => {}) }, [])
  if (!s) return null
  const a = s.agent || {}
  return (
    <section className="card">
      <h2>ระบบ AI และข้อมูล</h2>
      <p>🤖 {a.ok === false ? 'Intake AI Agent ออฟไลน์' : `${a.strategy || ''} · ${a.own_model || '-'}${a.llm ? ' + ' + a.llm : ''}`}</p>
      {a.llm && <p className="muted small">ข้อความที่ส่งต่อ LLM ปิดบังเบอร์/บ้านเลขที่/พิกัด/ชื่อแล้ว แต่ยังมีอาการป่วย (ข้อมูลอ่อนไหวตาม PDPA) — ถ้าไม่ต้องการให้ข้อความออกนอกระบบเลย ตั้ง <code>AGENT_STRATEGY=own</code> ใน .env (ใช้ AI ในเครื่องอย่างเดียว)</p>}
      {a.llm && <p className={a.pii_masking ? 'ok-chip' : 'wait-chip late'} style={{ display: 'inline-block' }}>
        {a.pii_masking ? '🔒 ปิดบังข้อมูลส่วนตัวก่อนส่ง LLM ภายนอก: เปิด' : '⚠️ ปิดบังข้อมูลส่วนตัว: ปิดอยู่ (LLM_MASK_PII=0)'}</p>}
      <div className="tiles small-tiles">{Object.entries(s.counts).map(([k, v]) => <div className="tile" key={k}><b>{v}</b><span>{k}</span></div>)}</div>
      <h3>ข้อมูลสำหรับเทรนรอบถัดไป</h3>
      {s.training && (
        <div className="tiles small-tiles">
          <div className="tile"><b>{s.training.rows}</b><span>ข้อความที่ AI อ่าน</span></div>
          <div className="tile"><b>{s.training.help_requests}</b><span>คำขอความช่วยเหลือ</span></div>
          <div className="tile"><b>{s.training.human_reviewed}</b><span>เจ้าหน้าที่ตรวจ/แก้แล้ว</span></div>
          <div className="tile"><b>{s.training.with_ai_feedback}</b><span>ถูกแจ้งว่า AI อ่านผิด</span></div>
          <div className="tile"><b>{s.training.escalated_to_llm}</b><span>ส่งต่อ LLM (มีป้ายจาก LLM)</span></div>
        </div>
      )}
      <p><a className="primary-link" href="/api/admin/export/training.jsonl" download>⬇ ทุกข้อความที่ส่งเข้ามา — ปิดบังข้อมูลส่วนตัว (floodlink_training.jsonl)</a></p>
      <p><a className="primary-link" href={api.exportCorrectionsUrl} download>⬇ เฉพาะเคสที่เจ้าหน้าที่แก้ผล AI (officer_corrections.jsonl)</a></p>
      <p className="muted small">รูปแบบเดียวกับ labels*.jsonl · แถวที่ <code>human_reviewed: true</code> ใช้เทรนได้ทันที แถวอื่นเป็นป้ายจาก AI ควรตรวจก่อน
        (เริ่มจากแถวที่มี <code>ai_feedback</code> และ <code>ai_confidence</code> ต่ำ) · เบอร์ บ้านเลขที่ พิกัด ลิงก์ ชื่อ ถูกแทนด้วย [เบอร์1] ฯลฯ · ไม่รวมข้อมูลเดโมและบันทึกของทีม
        · ป้ายที่ LLM ตอบอยู่ที่ <code>04_flood_nlp_model/data/teacher_labels.jsonl</code> ในเครื่อง</p>
    </section>
  )
}

const ACT = { login: 'เข้าสู่ระบบ', created: 'สร้างเคส', merged: 'รวมเคส', assign: 'มอบหมายทีม', status: 'เปลี่ยนสถานะ', close: 'ปิดเคส', reopen: 'เปิดเคสใหม่',
  priority: 'ปรับสี', correct_ai: 'แก้ผล AI', note: 'บันทึก', followup: 'ข้อมูลเพิ่ม', user_create: 'สร้างบัญชี', user_update: 'แก้บัญชี',
  demo_seed: 'โหลดเดโม', demo_delete: 'ลบเดโม', reset_all: 'ล้างข้อมูล', export_corrections: 'export ข้อมูลเทรน', change_password: 'เปลี่ยนรหัส', place_upsert: 'แก้จุดบริการ' }

function Audit() {
  const [rows, setRows] = useState([])
  const [q, setQ] = useState('')
  useEffect(() => { api.audit(500).then(setRows).catch(() => {}) }, [])
  const shown = rows.filter((r) => !q || [r.actor, r.action, r.case_id, JSON.stringify(r.detail)].join(' ').includes(q))
  return (
    <section className="card">
      <div className="card-head"><h2>บันทึกการใช้งาน (audit log)</h2>
        <input placeholder="ค้นหา ชื่อผู้ใช้ / เคส / การกระทำ" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      <div className="table-wrap tall">
        <table className="area-table">
          <thead><tr><th>เวลา</th><th>ใคร</th><th>ทำอะไร</th><th>เคส</th><th>รายละเอียด</th></tr></thead>
          <tbody>{shown.map((r) => (
            <tr key={r.id}><td className="small">{t(r.ts)}</td><td>{r.actor}</td><td>{ACT[r.action] || r.action}</td><td>{r.case_id || ''}</td>
              <td className="small detail">{Object.keys(r.detail).length ? JSON.stringify(r.detail) : ''}</td></tr>
          ))}</tbody>
        </table>
      </div>
    </section>
  )
}

export default function AdminPanel({ onBack }) {
  return (
    <main className="admin">
      <div className="row"><button className="ghost" onClick={onBack}>← กลับคิวเคส</button><h2>⚙️ จัดการระบบ</h2></div>
      <Users />
      <System />
      <Audit />
    </main>
  )
}

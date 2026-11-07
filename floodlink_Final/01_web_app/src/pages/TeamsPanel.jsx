import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { PRIORITY, TEAM_STATUS, TEAM_KIND, ago } from '../labels.js'

const EMPTY = { team: '', org: '', kind: 'volunteer', username: '', password: '', display_name: '', phone: '', boats: '', seats: '', has_medic: false }

function NewTeam({ onDone }) {
  const [f, setF] = useState(EMPTY)
  const [msg, setMsg] = useState('')
  const [open, setOpen] = useState(false)
  if (!open) return <button className="primary" onClick={() => setOpen(true)}>➕ เพิ่มชุด + บัญชีหัวหน้าชุด</button>
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const save = async (e) => {
    e.preventDefault()
    const body = { ...f, boats: f.boats === '' ? null : Number(f.boats), seats: f.seats === '' ? null : Number(f.seats) }
    try { await api.createTeamAccount(body); setMsg(`✓ สร้างชุด ${f.team} แล้ว — ส่งชื่อผู้ใช้/รหัสให้หัวหน้าชุดทางช่องทางส่วนตัว`); setF(EMPTY); onDone() }
    catch (x) { setMsg(x.message) }
  }
  return (
    <form className="card team-form" onSubmit={save}>
      <div className="fu-head"><b>➕ ชุดใหม่ (1 ชุด = 1 บัญชีหัวหน้าชุด)</b><button type="button" className="link" onClick={() => setOpen(false)}>ปิด</button></div>
      <div className="grid-form">
        <label>ชื่อชุด *<input value={f.team} onChange={set('team')} placeholder="เช่น ชุดเรือ 3 ป่อเต็กตึ๊ง" /></label>
        <label>หน่วยงาน<input value={f.org} onChange={set('org')} placeholder="เช่น มูลนิธิป่อเต็กตึ๊ง / ปภ.สงขลา" /></label>
        <label>ประเภท<select value={f.kind} onChange={set('kind')}>{Object.entries(TEAM_KIND).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label>ชื่อหัวหน้าชุด<input value={f.display_name} onChange={set('display_name')} placeholder="ชื่อที่แสดง" /></label>
        <label>เบอร์หัวหน้าชุด<input value={f.phone} onChange={set('phone')} placeholder="08x-xxx-xxxx" inputMode="tel" /></label>
        <label>เรือ (ลำ)<input type="number" min="0" value={f.boats} onChange={set('boats')} /></label>
        <label>รับคนได้ (คน)<input type="number" min="0" value={f.seats} onChange={set('seats')} /></label>
        <label className="check"><input type="checkbox" checked={f.has_medic} onChange={set('has_medic')} /> มีพยาบาล/กู้ชีพในชุด</label>
        <label>ชื่อผู้ใช้ *<input value={f.username} onChange={(e) => setF({ ...f, username: e.target.value.toLowerCase() })} placeholder="a-z 0-9" autoComplete="off" /></label>
        <label>รหัสผ่านเริ่มต้น *<input type="password" value={f.password} onChange={set('password')} placeholder="8 ตัวขึ้นไป" autoComplete="new-password" /></label>
      </div>
      <div className="row">{msg && <span className="small">{msg}</span>}<span className="spacer" />
        <button className="primary" disabled={!f.team || !f.username || f.password.length < 8}>สร้างชุด</button></div>
    </form>
  )
}

function TeamCard({ t, onChanged, onShowCase }) {
  const st = TEAM_STATUS[t.status] || TEAM_STATUS.offline
  const act = async (fn, ok) => { try { await fn(); onChanged() } catch (e) { alert(e.message) } }
  const lead = t.lead
  return (
    <article className="case team-card" style={{ borderLeftColor: st.color }}>
      <div className="case-top">
        <span className="badge" style={{ background: st.color }}>{st.label}</span>
        <b>{t.name}</b>
        <span className="muted">{[t.org, TEAM_KIND[t.kind]].filter(Boolean).join(' · ')}</span>
        <span className="status">{t.open_cases} งาน{t.red_cases ? ` · 🔴 ${t.red_cases}` : ''}{t.pending ? ` · ⏳ รอตอบรับ ${t.pending}` : ''}</span>
      </div>
      <div className="chips">
        {t.boats != null && <span className="chip">🚤 เรือ {t.boats}</span>}
        {t.seats != null && <span className="chip">👥 รับได้ {t.seats} คน</span>}
        {t.has_medic && <span className="chip need">🩺 มีพยาบาล</span>}
        <span className="chip">📍 ตำแหน่งล่าสุด {ago(t.located_at)}</span>
        {t.note && <span className="chip">📝 {t.note}</span>}
      </div>
      {t.case_ids.length > 0 && <p className="small">งานที่ถือ: {t.case_ids.map((id) => <button key={id} className="link" onClick={() => onShowCase(id)}>{id}</button>).reduce((a, b) => [a, ' ', b])}</p>}
      <div className="case-actions">
        <span className="team">{lead ? <>หัวหน้าชุด: <b>{lead.display_name}</b> (<code>{lead.username}</code>) · เข้าล่าสุด {ago(lead.last_login)}{!lead.active && ' · ⛔ ปิดบัญชีแล้ว'}</> : '⚠️ ยังไม่มีบัญชีหัวหน้าชุด'}</span>
        {t.phone && <a className="ghost call" href={`tel:${t.phone.replace(/[^\d]/g, '')}`}>☎ {t.phone}</a>}
        <select value="" onChange={(e) => e.target.value && act(() => api.updateTeam(t.name, { status: e.target.value }))} aria-label="ตั้งสถานะชุด">
          <option value="">ตั้งสถานะ…</option>{Object.entries(TEAM_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
        {lead && <button className="ghost" onClick={() => { const pw = prompt(`รหัสผ่านใหม่ของ ${lead.username} (8 ตัวขึ้นไป)`); if (pw) act(() => api.updateTeamAccount(lead.id, { password: pw })) }}>🔑 ตั้งรหัสใหม่</button>}
        {lead && (lead.active
          ? <button className="ghost warn-btn" onClick={() => confirm(`ปิดบัญชี ${lead.username}? (ออกจากระบบทันที งานที่ถืออยู่ยังอยู่กับชุด)`) && act(() => api.updateTeamAccount(lead.id, { active: false }))}>ปิดบัญชี</button>
          : <button className="ghost" onClick={() => act(() => api.updateTeamAccount(lead.id, { active: true }))}>เปิดบัญชี</button>)}
      </div>
    </article>
  )
}

// centre's view of every field team: who is free, where, how big, what they hold — and assignments nobody answered
export default function TeamsPanel({ onBack, onShowCase }) {
  const [b, setB] = useState(null)
  const [err, setErr] = useState('')
  const load = useCallback(() => api.teamBoard().then((d) => { setB(d); setErr('') }).catch((e) => setErr(e.message)), [])
  useEffect(() => { load(); const i = setInterval(load, 10000); return () => clearInterval(i) }, [load])
  const free = b?.teams.filter((t) => t.status === 'available' && t.lead?.active).length || 0
  return (
    <main className="admin">
      <div className="row"><button className="ghost" onClick={onBack}>← กลับคิวเคส</button><h2>👥 ชุดปฏิบัติการ</h2>
        {b && <span className="muted">{b.teams.length} ชุด · ว่าง {free}</span>}<span className="spacer" /><NewTeam onDone={load} /></div>
      {err && <div className="error">{err}</div>}
      {b?.late.length > 0 && (
        <div className="late-box">⏳ <b>มอบหมายแล้วแต่ชุดยังไม่ตอบรับเกิน {b.accept_minutes} นาที</b> — โทรหาหัวหน้าชุด หรือมอบหมายชุดอื่น
          <ul>{b.late.map((l) => <li key={l.id}><button className="link" onClick={() => onShowCase(l.id)}>{l.id}</button> {PRIORITY[l.priority]?.label} · {l.team} · {l.minutes} นาที</li>)}</ul>
        </div>
      )}
      <p className="muted small">1 ชุด มี 1 บัญชีหัวหน้าชุด หัวหน้าชุดเห็นเฉพาะเคสของชุดตัวเอง ตอบรับ/ปฏิเสธเคส ขอรับเคสใกล้ตัวที่ยังไม่มีทีม และอัปเดตสถานะ/ตำแหน่งชุด แล้วประสานกับลูกทีมเอง</p>
      <div className="cases">{b?.teams.map((t) => <TeamCard key={t.name} t={t} onChanged={load} onShowCase={onShowCase} />)}</div>
    </main>
  )
}

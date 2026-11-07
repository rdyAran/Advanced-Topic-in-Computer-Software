import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { PRIORITY, STATUS, FLAGS, NEEDS, WATER, CLOSE_REASON, MISSING, TEAM_STATUS, ago, peopleText, FLOORS } from '../labels.js'
import NavButton from '../components/NavButton.jsx'
import PhotoStrip from '../components/PhotoStrip.jsx'
import OriginalMessages from '../components/OriginalMessages.jsx'
import NoteForm from '../components/NoteForm.jsx'
import Timeline from '../components/Timeline.jsx'
import CaseMap from '../components/CaseMap.jsx'
import UserMenu from '../components/UserMenu.jsx'
import { askNotify, canNotify, notifyOn, useNewItems, useToasts } from '../notify.jsx'

const people = (c) => peopleText(c)
const DECLINE = ['เรือเข้าไม่ได้ / น้ำเชี่ยว', 'ไกลเกินไป', 'ชุดเต็ม รับคนเพิ่มไม่ได้', 'ไม่มีอุปกรณ์ที่ต้องใช้ (เช่น เปลหาม)']
const gps = () => new Promise((ok, no) => navigator.geolocation
  ? navigator.geolocation.getCurrentPosition((p) => ok({ lat: p.coords.latitude, lng: p.coords.longitude }), no, { enableHighAccuracy: true, timeout: 10000 })
  : no(new Error('เครื่องนี้ไม่รองรับ GPS')))

// team status + location + capacity: what the centre uses to decide who to send
function TeamBar({ team, onSaved }) {
  const [edit, setEdit] = useState(false)
  const [f, setF] = useState({})
  const [msg, setMsg] = useState('')
  if (!team) return null
  const save = async (patch) => { try { await api.updateMyTeam(patch); setMsg(''); onSaved() } catch (e) { setMsg(e.message) } }
  const locate = async () => { setMsg('กำลังหาตำแหน่ง…'); try { await save(await gps()); setMsg('✓ ส่งตำแหน่งชุดแล้ว') } catch (e) { setMsg('หาตำแหน่งไม่ได้: ' + e.message) } }
  return (
    <div className="team-bar">
      <div className="seg" role="group" aria-label="สถานะชุด">
        {Object.entries(TEAM_STATUS).map(([k, v]) => (
          <button key={k} className={team.status === k ? 'on' : ''} style={team.status === k ? { background: v.color } : undefined} onClick={() => save({ status: k })}>{v.label}</button>
        ))}
      </div>
      <div className="row tb-row">
        <button className="ghost" onClick={locate}>📍 ส่งตำแหน่งชุด</button>
        <span className="small muted">ล่าสุด {ago(team.located_at)}</span>
        <span className="spacer" />
        <button className="link" onClick={() => { setF({ boats: team.boats ?? '', seats: team.seats ?? '', has_medic: team.has_medic, phone: team.phone || '', note: team.note || '' }); setEdit((v) => !v) }}>
          {team.boats != null ? `🚤 ${team.boats} · ` : ''}{team.seats != null ? `👥 ${team.seats} · ` : ''}{team.has_medic ? '🩺 · ' : ''}แก้ข้อมูลชุด</button>
      </div>
      {msg && <div className="small">{msg}</div>}
      {edit && (
        <div className="grid-form tb-edit">
          <label>เรือ (ลำ)<input type="number" min="0" value={f.boats} onChange={(e) => setF({ ...f, boats: e.target.value })} /></label>
          <label>รับคนได้<input type="number" min="0" value={f.seats} onChange={(e) => setF({ ...f, seats: e.target.value })} /></label>
          <label>เบอร์ชุด<input value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} inputMode="tel" /></label>
          <label className="check"><input type="checkbox" checked={!!f.has_medic} onChange={(e) => setF({ ...f, has_medic: e.target.checked })} /> มีพยาบาล/กู้ชีพ</label>
          <label className="wide">หมายเหตุถึงศูนย์<input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} placeholder="เช่น เรือลำ 2 ซ่อมอยู่ / น้ำมันเหลือครึ่งถัง" /></label>
          <button className="primary" onClick={async () => { await save({ ...f, boats: f.boats === '' ? null : Number(f.boats), seats: f.seats === '' ? null : Number(f.seats) }); setEdit(false) }}>บันทึก</button>
        </div>
      )}
    </div>
  )
}

function JobCard({ c, onUpdate, onChanged, onMap }) {
  const p = PRIORITY[c.priority] || PRIORITY.green
  const closed = c.status === 'resolved'
  const pending = !closed && c.assign_state === 'pending'
  const close = (reason) => confirm(reason === 'rescued' ? 'ยืนยัน: ช่วยเหลือเสร็จแล้ว ปิดเคส?' : 'ยืนยัน: ไปถึงแล้วไม่พบผู้ประสบภัย ปิดเคส?') &&
    onUpdate(c.id, { status: 'resolved', close_reason: reason })
  const act = async (fn) => { try { await fn() } catch (e) { alert(e.message) } onChanged() }
  const decline = () => {
    const r = prompt(`ไปไม่ได้เพราะอะไร? (ศูนย์จะหาชุดอื่น)\n${DECLINE.map((d, i) => `${i + 1}) ${d}`).join('\n')}\nพิมพ์เลข หรือพิมพ์เหตุผลเอง`)
    if (!r?.trim()) return
    act(() => api.decline(c.id, DECLINE[Number(r) - 1] || r.trim()))
  }
  return (
    <article className={`case job ${closed ? 'done' : ''} ${pending ? 'pending' : ''}`} style={{ borderLeftColor: p.color }}>
      <div className="case-top">
        <span className="badge" style={{ background: p.color }}>{p.label}</span>
        <span className="muted">{c.id}</span>
        <span className="status">{pending ? '📥 งานใหม่ รอตอบรับ' : STATUS[c.status]}{closed && c.close_reason ? ` · ${CLOSE_REASON[c.close_reason]}` : ''}</span>
      </div>
      <p className="case-sum">{c.summary || c.first_text?.slice(0, 120)}</p>
      <p className="small muted">เหตุผลที่ได้สีนี้: {c.priority_reason}</p>
      <p className="job-where">📍 <b>{[c.house_no && `บ้านเลขที่ ${c.house_no}`, c.street, c.area].filter(Boolean).join(' · ') || 'ไม่ทราบตำแหน่ง'}</b>
        {c.landmark ? ` (${c.landmark})` : ''}</p>
      {people(c) && <p className="small">👥 {people(c)}</p>}
      <div className="chips">
        {c.building_floors && <span className={`chip ${c.building_floors === 1 ? 'warn' : ''}`}>🏘 {FLOORS[c.building_floors]}</span>}
        {c.water_level && <span className="chip">🌊 {WATER[c.water_level]}</span>}
        {c.flags.map((f) => <span className="chip warn" key={f}>{FLAGS[f]}</span>)}
        {c.needs.map((n) => <span className="chip need" key={n}>{NEEDS[n]}</span>)}
        {c.missing_fields.map((m) => <span className="chip missing" key={m}>ขาด{MISSING[m]}</span>)}
        {c.nav?.precision === 'area' && <span className="chip missing">ตำแหน่งยังไม่ชัด — โทรยืนยันก่อน</span>}
      </div>
      {c.photos?.length > 0 && <PhotoStrip photos={c.photos} size="sm" />}
      <div className="job-actions">
        <NavButton nav={c.nav} />
        {c.contact && <a className="big-btn call" href={`tel:${c.contact.replace(/[^\d]/g, '')}`}>☎ โทร {c.contact}</a>}
        {c.lat && <button className="ghost" onClick={() => onMap(c)}>🗺️</button>}
      </div>
      {pending && (
        <div className="job-actions accept-row">
          <button className="big-btn ok" onClick={() => act(() => api.accept(c.id))}>✅ รับเคส</button>
          <button className="big-btn warn" onClick={decline}>✋ ไปไม่ได้</button>
        </div>
      )}
      {!closed && !pending && (
        <div className="job-actions">
          {c.status !== 'in_progress' && <button className="big-btn go" onClick={() => onUpdate(c.id, { status: 'in_progress' })}>🚤 ออกเดินทาง / เริ่มช่วย</button>}
          <button className="big-btn ok" onClick={() => close('rescued')}>✅ ช่วยแล้ว</button>
          <button className="big-btn warn" onClick={() => close('not_found')}>❓ ไม่พบ</button>
          <button className="ghost" onClick={decline}>✋ ส่งคืนศูนย์</button>
        </div>
      )}
      <NoteForm caseId={c.id} onDone={onChanged} />
      <OriginalMessages caseId={c.id} count={c.report_count} />
      <Timeline caseId={c.id} />
    </article>
  )
}

// open cases with no team yet, near the team — only what is needed to decide; details appear after claiming
function Nearby({ onClaimed }) {
  const [rows, setRows] = useState(null)
  const [msg, setMsg] = useState('')
  const load = useCallback(async (useGps = false) => {
    try {
      const pos = useGps ? await gps() : null
      setRows(await api.nearby(pos?.lat, pos?.lng)); setMsg(pos ? '📍 เรียงจากตำแหน่งปัจจุบัน' : '')
    } catch (e) { setMsg(e.message) }
  }, [])
  useEffect(() => { load(); const i = setInterval(() => load(), 20000); return () => clearInterval(i) }, [load])
  const claim = async (n) => {
    if (!confirm(`รับเคส ${n.id} (${PRIORITY[n.priority]?.label}) ${n.area || ''}?\nกดรับแล้วชุดอื่นจะรับไม่ได้ และคุณจะเห็นที่อยู่ เบอร์ รูป`)) return
    try { await api.claim(n.id); onClaimed(n.id) } catch (e) { alert(e.message); load() }
  }
  return (
    <>
      <div className="row nb-head"><h2>เคสที่ยังไม่มีชุดรับ</h2><span className="spacer" /><button className="ghost" onClick={() => load(true)}>📍 เรียงจากที่ฉันอยู่</button></div>
      <p className="muted small">แสดงเท่าที่ใช้ตัดสินใจ (ไม่มีเบอร์/บ้านเลขที่) — กดรับแล้วจึงเห็นรายละเอียดเต็ม {msg && `· ${msg}`}</p>
      {rows?.length === 0 && <p className="muted empty">ตอนนี้ทุกเคสมีชุดรับแล้ว 👍</p>}
      {rows?.map((n) => {
        const p = PRIORITY[n.priority] || PRIORITY.green
        return (
          <article key={n.id} className="case job" style={{ borderLeftColor: p.color }}>
            <div className="case-top"><span className="badge" style={{ background: p.color }}>{p.label}</span><span className="muted">{n.id}</span>
              <span className="status">{n.km != null ? `${n.km} กม.` : 'ไม่ทราบระยะ'}</span></div>
            <p className="job-where">📍 <b>{[n.street, n.area].filter(Boolean).join(' · ') || 'ไม่ทราบตำแหน่ง'}</b> <span className="small muted">แจ้งเมื่อ {ago(n.created_at)}</span></p>
            <div className="chips">
              {n.people && <span className="chip">👥 {n.people} คน</span>}
              {n.water_level && <span className="chip">🌊 {WATER[n.water_level]}</span>}
              {n.flags.map((f) => <span className="chip warn" key={f}>{FLAGS[f]}</span>)}
              {n.needs.map((x) => <span className="chip need" key={x}>{NEEDS[x]}</span>)}
            </div>
            <button className="big-btn go" onClick={() => claim(n)}>🙋 ชุดเรารับเคสนี้</button>
          </article>
        )
      })}
    </>
  )
}

// TEAM LEAD view (one account per team): the team's jobs, accept/decline, claim nearby, team status/location
export default function RescuerApp({ user, onLogout }) {
  const [cases, setCases] = useState(null)
  const [team, setTeam] = useState(null)
  const [tab, setTab] = useState('todo')
  const [focus, setFocus] = useState(null)
  const [selected, setSelected] = useState(null)
  const [err, setErr] = useState('')
  const [perm, setPerm] = useState(notifyOn())
  const [push, toasts] = useToasts()
  const load = useCallback(() => {
    api.cases('').then((c) => { setCases(c); setErr('') }).catch((e) => e.status !== 401 && setErr(e.message))
    api.myTeam().then(setTeam).catch(() => {})
  }, [])
  useEffect(() => { load(); const i = setInterval(load, 10000); return () => clearInterval(i) }, [load])
  const fresh = useNewItems(cases)
  useEffect(() => {
    const open = fresh.filter((c) => c.status !== 'resolved' && c.assign_state === 'pending')
    if (open.length) push(`📥 ศูนย์มอบหมายงานใหม่: ${open.map((c) => `${c.id} (${PRIORITY[c.priority]?.label})`).join(', ')} — กดรับหรือไปไม่ได้`,
      open.some((c) => c.priority === 'red') ? 'red' : 'info', { sound: true, system: true })
  }, [fresh, push])
  const update = async (id, patch) => { try { await api.updateCase(id, patch) } catch (e) { alert(e.message) } load() }
  const todo = (cases || []).filter((c) => c.status !== 'resolved')
  const pending = todo.filter((c) => c.assign_state === 'pending')
  const done = (cases || []).filter((c) => c.status === 'resolved')
  const onMap = (c) => { setSelected(c.id); setFocus({ key: Date.now(), lat: c.lat, lng: c.lng }); setTab('map') }

  return (
    <div className="app is-mobile rescuer">
      <header className="topbar slim">
        <div className="brand"><span className="logo" aria-hidden>≋</span><div><h1>FloodLink</h1><p className="team-name">{user.team}</p></div></div>
        <span className="spacer" />
        <UserMenu user={user} onLogout={onLogout} />
      </header>
      {err && <div className="error">{err}</div>}
      {canNotify() && !perm && <button className="notify-bar" onClick={() => askNotify().then((r) => setPerm(r === 'granted'))}>🔔 เปิดการแจ้งเตือนเมื่อมีงานใหม่</button>}
      <main className="rescuer-main">
        {tab !== 'map' && <TeamBar team={team} onSaved={load} />}
        {tab === 'todo' && (
          <>
            <h2>งานของชุด ({todo.length}){pending.length > 0 && <span className="wait-chip late"> 📥 รอตอบรับ {pending.length}</span>}</h2>
            {cases && todo.length === 0 && <p className="muted empty">ยังไม่มีงาน — ศูนย์จะส่งเคสมาที่นี่ (มีเสียงเตือน) หรือดูแท็บ “ใกล้ฉัน” เพื่อขอรับเคสเอง</p>}
            {[...pending, ...todo.filter((c) => c.assign_state !== 'pending')].map((c) => <JobCard key={c.id} c={c} onUpdate={update} onChanged={load} onMap={onMap} />)}
          </>
        )}
        {tab === 'near' && <Nearby onClaimed={() => { load(); setTab('todo') }} />}
        {tab === 'done' && (
          <>
            <h2>ปิดแล้ว ({done.length})</h2>
            {done.map((c) => <JobCard key={c.id} c={c} onUpdate={update} onChanged={load} onMap={onMap} />)}
          </>
        )}
        <div className={`rescuer-map ${tab === 'map' ? 'on' : ''}`}>
          <CaseMap cases={todo} hazards={[]} places={[]} selected={selected} setSelected={setSelected} focus={focus} visible={tab === 'map'} />
        </div>
      </main>
      {toasts}
      <nav className="bottom-nav" aria-label="เมนูหลัก">
        {[['todo', '🚤', 'งานของชุด'], ['near', '🙋', 'ใกล้ฉัน'], ['map', '🗺️', 'แผนที่'], ['done', '✅', 'ปิดแล้ว']].map(([k, i, l]) => (
          <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}><span className="ico" aria-hidden>{i}</span>{l}
            {k === 'todo' && todo.length > 0 && <span className="dot">{todo.length}</span>}</button>
        ))}
      </nav>
    </div>
  )
}

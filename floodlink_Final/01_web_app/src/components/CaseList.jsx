import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { PRIORITY, STATUS, FLAGS, NEEDS, WATER, MISSING, CLOSE_REASON, TEAM_STATUS } from '../labels.js'
import NavButton from './NavButton.jsx'
import OriginalMessages from './OriginalMessages.jsx'
import PhotoStrip from './PhotoStrip.jsx'
import FollowupForm from './FollowupForm.jsx'
import NoteForm from './NoteForm.jsx'
import Timeline from './Timeline.jsx'
import AiEditor from './AiEditor.jsx'
import { STATUS_TABS, SORTS, DEFAULT_FILTERS, applyFilters, isFiltered, LATE_MIN } from '../queue.js'
import { ago, peopleText, FLOORS } from '../labels.js'

const NEXT = { new: 'verified', assigned: 'in_progress' }
const NEXT_LABEL = { new: '✓ ตรวจแล้ว', assigned: '▶ เริ่มช่วย' }

// teams = the centre's team board (status, load). Suggestions (free > close > medic for patients) load when the menu is opened.
function AssignSelect({ c, teams, onUpdate }) {
  const [sug, setSug] = useState(null)
  const loadSug = () => { if (!sug) api.suggestTeams(c.id).then(setSug).catch(() => setSug([])) }
  const pick = (v) => {
    if (v === '__other') { const t = prompt('ชื่อชุด (ชุดที่ยังไม่มีบัญชี จะไม่ได้รับแจ้งเตือนในระบบ — ต้องโทรแจ้งเอง)'); if (t?.trim()) onUpdate(c.id, { assigned_team: t.trim() }) }
    else if (v === '__none') onUpdate(c.id, { assigned_team: '' })
    else if (v) onUpdate(c.id, { assigned_team: v })
  }
  const label = (t) => `${t.name} · ${TEAM_STATUS[t.status]?.label || '-'} · ${t.open_cases} งาน${t.lead?.active ? '' : ' · ไม่มีบัญชี'}`
  const known = new Set((teams || []).map((t) => t.name))
  const top = (sug || []).map((x) => x.team)
  return (
    <select className="assign" value="" onFocus={loadSug} onMouseDown={loadSug} onChange={(e) => pick(e.target.value)} aria-label="มอบหมายชุด">
      <option value="">{c.assigned_team ? '🔁 เปลี่ยนชุด…' : '👥 มอบหมายชุด…'}</option>
      {sug?.length > 0 && <optgroup label="⭐ แนะนำ (ว่าง · ใกล้ · มีพยาบาล)">
        {sug.map((x) => <option key={'s' + x.team} value={x.team} disabled={x.team === c.assigned_team}>
          ⭐ {x.team}{x.km != null ? ` · ${x.km} กม.` : ''} · {x.open_cases} งาน{x.has_medic ? ' · 🩺' : ''}</option>)}
      </optgroup>}
      <optgroup label="ทุกชุด">
        {(teams || []).filter((t) => !top.includes(t.name)).map((t) => <option key={t.name} value={t.name} disabled={t.name === c.assigned_team}>{label(t)}</option>)}
        {c.assigned_team && !known.has(c.assigned_team) && <option value={c.assigned_team} disabled>{c.assigned_team}</option>}
      </optgroup>
      <option value="__other">อื่น ๆ (พิมพ์ชื่อ)</option>
      {c.assigned_team && <option value="__none">ยกเลิกชุด</option>}
    </select>
  )
}

function CloseSelect({ c, onUpdate }) {
  return (
    <select className="close-sel" value="" onChange={(e) => e.target.value && onUpdate(c.id, { status: 'resolved', close_reason: e.target.value })} aria-label="ปิดเคส">
      <option value="">■ ปิดเคส…</option>
      {Object.entries(CLOSE_REASON).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
    </select>
  )
}

function TeamState({ c }) {
  if (!c.assigned_team) return <span className="muted">ยังไม่มีชุด</span>
  return <>👥 <b>{c.assigned_team}</b> {c.assign_state === 'accepted' ? <span className="ok-chip">✓ ตอบรับ</span>
    : c.waiting_accept_min != null && <span className={`wait-chip ${c.waiting_accept_min >= LATE_MIN ? 'late' : ''}`}>⏳ รอตอบรับ {c.waiting_accept_min} น.</span>}</>
}

// one row per case; the selected case opens in place with every detail and action
function CaseCard({ c, active, onSelect, onUpdate, onLocate, onChanged, teams }) {
  const p = PRIORITY[c.priority] || PRIORITY.green
  const closed = c.status === 'resolved'
  const stop = (e) => e.stopPropagation()
  return (
    <article id={`case-${c.id}`} className={`case qrow ${active ? 'active open-card' : ''} ${closed ? 'done' : ''}`}
      style={{ borderLeftColor: p.color }} onClick={() => onSelect(active ? null : c.id)} aria-expanded={active}>
      <div className="qrow-top">
        <span className="badge" style={{ background: p.color }}>{p.label.split(' · ')[0]}</span>
        <code className="cid">{c.id}</code>
        <span className={`st st-${c.status}`}>{STATUS[c.status]}{closed && c.close_reason ? ` · ${CLOSE_REASON[c.close_reason]}` : ''}</span>
        <span className="qrow-team"><TeamState c={c} /></span>
        <span className="spacer" />
        {c.report_count > 1 && <span className="dup" title="มีคนแจ้งบ้านนี้หลายครั้ง">×{c.report_count}</span>}
        {c.photos?.length > 0 && <span className="dup" title="มีรูปแนบ">📷{c.photos.length}</span>}
        <span className="muted small" title={c.created_at}>{ago(c.created_at)}</span>
        <span className="chev" aria-hidden>{active ? '▾' : '▸'}</span>
      </div>
      <p className="qrow-sum">{c.summary || c.first_text?.slice(0, 120)}</p>
      <div className="qrow-meta">
        <span>📍 {c.area || (['exact', 'link'].includes(c.nav?.precision) ? (c.nav.precision === 'exact' ? 'ตามพิกัดของผู้แจ้ง' : 'ตามลิงก์แผนที่ของผู้แจ้ง') : 'ไม่ทราบพื้นที่')}{c.street ? ` · ${c.street}` : ''}</span>
        {c.nav?.precision === 'area' && <span className="chip missing">ตำแหน่งยังไม่ชัด</span>}
        {(c.priority_reason || '').startsWith('AI: พบคำวิกฤต') && c.status !== 'resolved' &&
          <span className="chip warn" title={c.priority_reason}>🔑 แดงจากคำสำคัญ — โทรยืนยัน</span>}
        {c.possible_dup && c.status !== 'resolved' && (
          <button type="button" className="chip dupchip" onClick={(e) => { stop(e); onSelect(c.possible_dup) }}
            title="ความคล้ายก้ำกึ่ง ระบบจึงไม่รวมให้อัตโนมัติ — เปิดเคสนั้นเพื่อเทียบ">⚠️ อาจซ้ำกับ {c.possible_dup} ({c.possible_dup_score})</button>
        )}
        {c.missing_fields.map((m) => <span className="chip missing" key={m}>ขาด{MISSING[m]}</span>)}
        {!active && c.status === 'new' && <button className="mini" onClick={(e) => { stop(e); onUpdate(c.id, { status: 'verified' }) }}>✓ ตรวจแล้ว</button>}
        {!active && !closed && !c.assigned_team && c.status !== 'new' && <span onClick={stop}><AssignSelect c={c} teams={teams} onUpdate={onUpdate} /></span>}
      </div>

      {active && (
        <div className="qrow-detail" onClick={stop}>
          <p className="reason">เหตุผลที่ได้สีนี้: {c.priority_reason}{c.contact ? ` · ☎ ${c.contact}` : ''}</p>
          {c.possible_dup && c.status !== 'resolved' && (
            <div className="dup-box">
              ⚠️ อาจเป็นบ้านเดียวกับ <button className="link" onClick={() => onSelect(c.possible_dup)}>{c.possible_dup}</button>
              <span className="muted small"> (คล้าย {c.possible_dup_score} — ไม่มั่นใจพอจะรวมเอง)</span>
              <span className="spacer" />
              <button className="mini" onClick={async () => { if (!confirm(`รวมรายงานทั้งหมดของ ${c.id} เข้า ${c.possible_dup} แล้วปิด ${c.id} เป็นเคสซ้ำ?`)) return
                try { await api.mergeInto(c.id, c.possible_dup); onSelect(c.possible_dup) } catch (e) { alert(e.message) } onChanged() }}>รวมเข้า {c.possible_dup}</button>
              <button className="mini ghost" onClick={async () => { await api.notDuplicate(c.id).catch((e) => alert(e.message)); onChanged() }}>ไม่ใช่บ้านเดียวกัน</button>
            </div>
          )}
          <div className="chips">
            {c.house_no && <span className="chip">🏠 บ้านเลขที่ {c.house_no}</span>}
            {c.building_floors && <span className={`chip ${c.building_floors === 1 ? 'warn' : ''}`}>🏘 {FLOORS[c.building_floors]}</span>}
            {peopleText(c) && <span className="chip">👥 {peopleText(c)}</span>}
            {c.water_level && <span className="chip">🌊 {WATER[c.water_level]}</span>}
            {c.flags.map((f) => <span className="chip warn" key={f}>{FLAGS[f]}</span>)}
            {c.needs.map((n) => <span className="chip need" key={n}>{NEEDS[n]}</span>)}
          </div>
          {c.photos?.length > 0 && <PhotoStrip photos={c.photos} size="sm" />}
          <div className="case-actions">
            <NavButton nav={c.nav} />
            {c.lat && <button className="ghost" onClick={() => onLocate?.(c)}>🗺️ แผนที่</button>}
            {c.contact && <a className="ghost call" href={`tel:${c.contact.replace(/[^\d]/g, '')}`}>☎ โทร</a>}
            {NEXT[c.status] && <button onClick={() => onUpdate(c.id, { status: NEXT[c.status] })}>{NEXT_LABEL[c.status]}</button>}
            {!closed && <AssignSelect c={c} teams={teams} onUpdate={onUpdate} />}
            {!closed && <CloseSelect c={c} onUpdate={onUpdate} />}
            {closed && <button className="ghost" onClick={() => onUpdate(c.id, { status: c.assigned_team ? 'assigned' : 'verified' })}>↺ เปิดเคสใหม่</button>}
            <select className="recolor" value="" onChange={(e) => e.target.value && onUpdate(c.id, { priority: e.target.value })} title="เจ้าหน้าที่ปรับระดับเอง">
              <option value="">ปรับสี…</option>
              {Object.entries(PRIORITY).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </div>
          <div className="fu-slot">
            <AiEditor c={c} onDone={onChanged} />
            {!closed && <FollowupForm key={c.id} caseId={c.id} missing={c.missing_fields} compact onDone={onChanged} />}
            <NoteForm caseId={c.id} onDone={onChanged} label="📝 บันทึก" />
          </div>
          <OriginalMessages caseId={c.id} count={c.report_count} />
          <Timeline caseId={c.id} />
        </div>
      )}
    </article>
  )
}

function FilterBar({ f, setF, counts, colorCounts, areas, teams }) {
  const set = (k, v) => setF({ ...f, [k]: v })
  const togColor = (k) => set('colors', f.colors.includes(k) ? f.colors.filter((x) => x !== k) : [...f.colors, k])
  return (
    <div className="qfilters">
      <div className="qtabs" role="tablist" aria-label="สถานะเคส">
        {STATUS_TABS.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={f.status === k} className={`${f.status === k ? 'on' : ''} ${k === 'todo' && counts[k] ? 'hot' : ''}`}
            onClick={() => set('status', k)}>{label} <b>{counts[k]}</b></button>
        ))}
      </div>
      <div className="qtools">
        <div className="qcolors" role="group" aria-label="กรองตามสี">
          {Object.entries(PRIORITY).map(([k, v]) => (
            <button key={k} className={f.colors.includes(k) ? 'on' : ''} style={f.colors.includes(k) ? { background: v.color, borderColor: v.color } : { borderColor: v.color, color: v.color }}
              onClick={() => togColor(k)} aria-pressed={f.colors.includes(k)}>{v.label.split(' · ')[0]} {colorCounts[k]}</button>
          ))}
        </div>
        <select value={f.team} onChange={(e) => set('team', e.target.value)} aria-label="กรองตามชุด">
          <option value="">ทุกชุด</option><option value="__none">ยังไม่มีชุด</option>
          {[...new Set([...(teams || []).map((t) => t.name), ...areas.teams])].map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select value={f.area} onChange={(e) => set('area', e.target.value)} aria-label="กรองตามพื้นที่">
          <option value="">ทุกพื้นที่</option>{areas.list.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        <select value={f.sort} onChange={(e) => set('sort', e.target.value)} aria-label="เรียงลำดับ">
          {Object.entries(SORTS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <input className="qsearch" type="search" value={f.q} onChange={(e) => set('q', e.target.value)} placeholder="🔎 ค้นหา เลขเคส เบอร์ ซอย ชื่อพื้นที่" />
        {isFiltered(f) && <button className="link" onClick={() => setF({ ...DEFAULT_FILTERS, status: f.status })}>ล้างตัวกรอง</button>}
      </div>
    </div>
  )
}

export default function CaseList({ cases, filters, setFilters, selected, setSelected, onUpdate, onLocate, onChanged, teams, onNew }) {
  const { rows, counts, colorCounts, areas, teams: usedTeams } = applyFilters(cases, filters)
  const box = useRef(null)
  useEffect(() => {                       // keep the selected case in view (map click, toast click, chatbot link)
    if (!selected) return
    const t = setTimeout(() => document.getElementById(`case-${selected}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 80)
    return () => clearTimeout(t)
  }, [selected])
  return (
    <div className="card list">
      <div className="card-head">
        <h2>คิวเคส <span className="muted">({rows.length}{rows.length !== cases.length ? ` จาก ${cases.length}` : ''})</span></h2>
        {onNew && <button className="primary" onClick={onNew}>➕ รับเรื่องใหม่</button>}
      </div>
      <FilterBar f={filters} setF={setFilters} counts={counts} colorCounts={colorCounts} areas={{ list: areas, teams: usedTeams }} teams={teams} />
      <div className="cases" ref={box}>
        {rows.length === 0 && <p className="muted empty">{cases.length === 0 ? 'ยังไม่มีเคส — รับเรื่องใหม่ หรือให้ผู้ดูแลระบบโหลดข้อมูลเดโม'
          : filters.status === 'todo' ? '✅ ไม่มีเคสที่ต้องจัดการตอนนี้' : 'ไม่มีเคสตรงกับตัวกรอง'}</p>}
        {rows.map((c) => (
          <CaseCard key={c.id} c={c} active={selected === c.id} onSelect={setSelected} onUpdate={onUpdate} onLocate={onLocate}
            onChanged={onChanged} teams={teams} />
        ))}
      </div>
    </div>
  )
}

import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { PRIORITY, STEPS } from '../labels.js'
import FollowupForm from '../components/FollowupForm.jsx'
import PhotoStrip from '../components/PhotoStrip.jsx'
import { askNotify, canNotify, notifyOn, useToasts } from '../notify.jsx'
import { go } from '../App.jsx'

const STEP_TH = { new: 'รับเรื่อง', verified: 'ตรวจแล้ว', assigned: 'มีทีมรับ', in_progress: 'กำลังช่วย', resolved: 'ปิดเคส' }
const t = (s) => (s ? new Date(s).toLocaleString('th-TH', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '')

function Stepper({ status }) {
  const at = STEPS.indexOf(status)
  return (
    <ol className="stepper" aria-label="ความคืบหน้า">
      {STEPS.map((s, i) => <li key={s} className={i < at ? 'done' : i === at ? 'now' : ''}><span>{i < at ? '✓' : i + 1}</span>{STEP_TH[s]}</li>)}
    </ol>
  )
}

const ICON = { ok: '✓', partial: '!', missing: '✗' }
const missingKeys = (c) => c.checklist.filter((r) => r.level === 'need' && r.state !== 'ok').map((r) => TO_FOLLOWUP[r.key])
const STATE_TH = { ok: 'มีแล้ว', partial: 'ยังไม่ชัด', missing: 'ยังขาด' }
const TO_FOLLOWUP = { location: 'area', people: 'people_count', water: 'water_level', contact: 'contact' }

// what the team still needs to reach this house quickly — essentials first, then "helps a lot"
function Checklist({ c }) {
  const need = c.checklist.filter((r) => r.level === 'need'), help = c.checklist.filter((r) => r.level === 'help')
  const allOk = c.essential_ok === c.essential_total
  const row = (r) => (
    <li key={r.key} className={`ck ${r.state}`}>
      <span className="ck-ico" aria-hidden>{ICON[r.state]}</span>
      <div><b>{r.label}</b> <span className="ck-state">{STATE_TH[r.state]}</span>
        {r.state !== 'ok' && <div className="ck-hint">{r.hint}</div>}</div>
    </li>
  )
  return (
    <div className={`checklist-box ${allOk ? 'all-ok' : ''}`}>
      <div className="ck-head">
        {allOk ? '✅ ข้อมูลสำคัญครบแล้ว — ทีมพร้อมออกเมื่อได้รับมอบหมาย' : <>⚠️ ทีมยังต้องการข้อมูลเพิ่ม <b>({c.essential_ok}/{c.essential_total} ข้อสำคัญ)</b></>}
      </div>
      <ul>{need.map(row)}</ul>
      {help.some((r) => r.state !== 'ok') && (
        <details><summary>ข้อมูลที่ช่วยให้เร็วขึ้น ({help.filter((r) => r.state === 'ok').length}/{help.length})</summary><ul>{help.map(row)}</ul></details>
      )}
    </div>
  )
}

function TrackedCase({ c, token, onChanged, many }) {
  const p = PRIORITY[c.priority] || PRIORITY.green
  const [busy, setBusy] = useState(false)
  const closed = c.status === 'resolved'
  const safe = async () => {
    if (!confirm('ยืนยันว่าทุกคนในเคสนี้ปลอดภัยแล้ว ไม่ต้องการความช่วยเหลือ? (เจ้าหน้าที่จะปิดเคสและส่งทีมไปช่วยบ้านอื่น)')) return
    setBusy(true)
    try { await api.trackSafe(token, c.id); onChanged() } catch (e) { alert(e.message) } finally { setBusy(false) }
  }
  return (
    <article className="card tracked" style={{ borderTopColor: p.color }}>
      <div className="case-top">
        <span className="badge" style={{ background: p.color }}>{p.label}</span>
        <b>เคส {c.id}</b>
        <span className="status">{c.status_th}</span>
      </div>
      <Stepper status={c.status} />
      {closed
        ? <div className="fu-ok">✓ ปิดเคสแล้ว: {c.close_reason_th}. ถ้ายังต้องการความช่วยเหลือ กรุณาแจ้งเรื่องใหม่ หรือโทร 1784</div>
        : c.assigned_team ? <p>🚤 ทีมที่รับเคส: <b>{c.assigned_team}</b></p>
          : <p className="muted">ยังไม่มีทีมรับ — {c.priority === 'red' ? 'เคสของคุณอยู่ในกลุ่มวิกฤต จะได้รับการจัดทีมก่อน' : 'ศูนย์จัดทีมตามความเร่งด่วน (เคสวิกฤตก่อน) ข้อมูลที่ครบช่วยให้จัดทีมได้เร็วขึ้น'}</p>}
      {c.summary && <p className="case-sum">“{c.summary}”</p>}
      <p className="small muted">📍 {c.area || 'ยังไม่ทราบตำแหน่ง'}{c.street ? ` · ${c.street}` : ''} · อัปเดตล่าสุด {t(c.updated_at)}</p>
      {!closed && <Checklist c={c} />}
      <details className="timeline" open={!many}>
        <summary>ประวัติเคส ({c.timeline.length})</summary>
        <ul>{c.timeline.slice().reverse().map((e, i) => <li key={i}><span className="muted small">{t(e.ts)}</span> {e.text}</li>)}</ul>
      </details>
      {!closed && (
        <>
          <FollowupForm key={missingKeys(c).join()} caseId={c.id} missing={missingKeys(c)} track={token}
            compact={many && c.essential_ok === c.essential_total} onDone={onChanged} />
          <button className="safe-btn" disabled={busy} onClick={safe}>✅ ทุกคนปลอดภัยแล้ว</button>
        </>
      )}
    </article>
  )
}

export default function TrackPage({ token }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [push, toasts] = useToasts()
  const [perm, setPerm] = useState(notifyOn())
  const last = useRef(null)
  const load = useCallback(async () => {
    try {
      const d = await api.track(token)
      const sig = Object.fromEntries(d.cases.map((c) => [c.id, `${c.status}|${c.assigned_team || ''}`]))
      if (last.current) {
        for (const c of d.cases) {
          if (last.current[c.id] && last.current[c.id] !== sig[c.id]) {
            push(`เคส ${c.id}: ${c.timeline.at(-1)?.text || c.status_th}`, 'info', { sound: true, system: true })
          }
        }
      }
      last.current = sig; setData(d); setErr('')
    } catch (e) { setErr(e.status === 404 ? 'ไม่พบลิงก์ติดตามนี้ ตรวจสอบว่าคัดลอกครบ' : 'โหลดไม่ได้: ' + e.message) }
  }, [token, push])
  useEffect(() => { load(); const i = setInterval(load, 20000); return () => clearInterval(i) }, [load])

  return (
    <div className="public-shell">
      <header className="topbar slim">
        <button className="brand as-link" onClick={() => go('/')} aria-label="กลับหน้าแรก"><span className="logo" aria-hidden>≋</span><div><h1>FloodLink</h1><p>ติดตามเคสของคุณ</p></div></button>
        <span className="spacer" />
        <button className="ghost" onClick={() => go('/')}>📝 แจ้งเพิ่ม</button>
        <button className="ghost" onClick={() => go('/public')}>📊 สรุป</button>
        <a className="sos" href="tel:1669">☎ 1669</a>
      </header>
      <main className="public-main">
        {err && <div className="error">{err}</div>}
        {!data && !err && <p className="muted">กำลังโหลด…</p>}
        {data && (
          <>
            <div className="track-head">
              <p>แจ้งเมื่อ {t(data.received_at)}{data.cases.length > 1 ? ` · ข้อความนี้แยกเป็น ${data.cases.length} เคส` : ''}</p>
              {canNotify() && !perm && <button className="ghost" onClick={() => askNotify().then((r) => setPerm(r === 'granted'))}>🔔 แจ้งเตือนเมื่อสถานะเปลี่ยน</button>}
              {perm && <span className="small muted">🔔 จะแจ้งเตือนเมื่อสถานะเปลี่ยน (เปิดหน้านี้ไว้)</span>}
            </div>
            {data.cases.length === 0 && <div className="card">ข้อความนี้ยังไม่ได้สร้างเคส (ระบบอ่านแล้วไม่ใช่คำขอความช่วยเหลือ) — ถ้าต้องการความช่วยเหลือ <button className="link" onClick={() => go('/')}>แจ้งใหม่ที่นี่</button></div>}
            {data.cases.map((c) => <TrackedCase key={c.id} c={c} token={token} onChanged={load} many={data.cases.length > 1} />)}
            <details className="card my-reports">
              <summary>สิ่งที่คุณส่งมา ({data.my_reports.length})</summary>
              {data.my_reports.map((m) => (
                <div key={m.id} className="orig-item"><div className="muted small">{t(m.received_at)}</div>
                  <div className="raw-text">{m.raw_text}</div>{m.photos.length > 0 && <PhotoStrip photos={m.photos} />}</div>
              ))}
            </details>
            <div className="card track-nav">
              <button className="ghost" onClick={() => go('/')}>📝 แจ้งเหตุใหม่ (บ้านอื่น / คนอื่น)</button>
              <button className="ghost" onClick={() => go('/public')}>📊 ดูสรุปสถานการณ์</button>
              <span className="muted small">ข้อมูลเพิ่มของบ้านนี้ ส่งในช่อง “ส่งข้อมูลเพิ่ม” ด้านบน — ไม่ต้องแจ้งใหม่ (จะได้ไม่เป็นเคสซ้ำ)</span>
            </div>
            <p className="muted small privacy-note">🔒 ลิงก์นี้เป็นของคุณคนเดียว — ใครมีลิงก์จะเห็นสถานะเคสได้ อย่าโพสต์ในที่สาธารณะ</p>
          </>
        )}
      </main>
      {toasts}
    </div>
  )
}

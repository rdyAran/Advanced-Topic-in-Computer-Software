import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api.js'
import StatsBar from './components/StatsBar.jsx'
import CaseList from './components/CaseList.jsx'
import CaseMap from './components/CaseMap.jsx'
import SubmitForm from './components/SubmitForm.jsx'
import ChatWidget from './components/ChatWidget.jsx'
import UserMenu from './components/UserMenu.jsx'
import AdminPanel from './pages/AdminPanel.jsx'
import TeamsPanel from './pages/TeamsPanel.jsx'
import { useNewItems, useToasts } from './notify.jsx'
import { go } from './App.jsx'
import { DEFAULT_FILTERS, applyFilters } from './queue.js'

const MOBILE_Q = '(max-width: 899px)'
function useIsMobile() {
  const [m, setM] = useState(() => window.matchMedia(MOBILE_Q).matches)
  useEffect(() => {
    const mq = window.matchMedia(MOBILE_Q), on = () => setM(mq.matches)
    mq.addEventListener('change', on); return () => mq.removeEventListener('change', on)
  }, [])
  return m
}
const TABS = [['report', '📝', 'แจ้งเหตุ'], ['cases', '📋', 'คิวเคส'], ['map', '🗺️', 'แผนที่'], ['chat', '💬', 'ผู้ช่วย']]

// coordinator + admin: the whole queue, map, intake of phone calls, (admin) system management
export default function StaffApp({ user, onLogout }) {
  const [cases, setCases] = useState([])
  const [hazards, setHazards] = useState([])
  const [stats, setStats] = useState(null)
  const [filters, setFilters] = useState(() => {
    try { return { ...DEFAULT_FILTERS, ...JSON.parse(sessionStorage.getItem('fl_filters') || '{}'), q: '' } } catch { return DEFAULT_FILTERS }
  })
  useEffect(() => { try { sessionStorage.setItem('fl_filters', JSON.stringify(filters)) } catch { /* private mode */ } }, [filters])
  const [intakeOpen, setIntakeOpen] = useState(false)
  const [agentDown, setAgentDown] = useState(false)
  const [selected, setSelected] = useState(null)
  const [provider, setProvider] = useState('')
  const [error, setError] = useState('')
  const [teams, setTeams] = useState([])
  const [page, setPage] = useState('queue')            // queue | teams | admin
  const adminView = page !== 'queue'
  const [late, setLate] = useState(null)
  const [push, toasts] = useToasts()
  const isAdmin = user.role === 'admin'
  const [places, setPlaces] = useState([])
  const [focus, setFocus] = useState(null)
  const [pendingFocus, setPendingFocus] = useState(() => {
    const q = new URLSearchParams(window.location.search)      // links from the chatbot: /?case=ID or /?place=ID
    return q.get('case') ? { case: q.get('case') } : q.get('place') ? { place: q.get('place') } : null
  })
  const isMobile = useIsMobile()
  const [view, setView] = useState(() => (pendingFocus ? 'map' : 'cases'))   // mobile: which screen is shown
  const [chatOpen, setChatOpen] = useState(false)                           // desktop: floating chat panel
  const showChat = isMobile ? view === 'chat' : chatOpen

  const refresh = useCallback(async () => {
    try {
      const [c, h, s, p] = await Promise.all([api.cases(''), api.hazards(), api.stats(), api.places().catch(() => [])])   // filtered on screen
      setCases(c); setHazards(h); setStats(s); setPlaces(p); setError(''); setLoaded(true)
    } catch (e) {
      if (e.status !== 401) setError('เชื่อมต่อ backend ไม่ได้: ' + e.message)
    }
  }, [])
  useEffect(() => {                         // team board: status / distance / load for the assign menu + late answers
    const load = () => api.teamBoard().then((b) => { setTeams(b.teams); setLate(b.late) }).catch(() => {})
    load(); const i = setInterval(load, 10000); return () => clearInterval(i)
  }, [])
  const freshLate = useNewItems(late)
  useEffect(() => {
    if (freshLate.length) push(`⏳ มอบหมายแล้วยังไม่ตอบรับเกิน ${freshLate[0].minutes} นาที: ${freshLate.map((l) => `${l.id} (${l.team})`).join(', ')}`, 'red',
      { sound: true, system: true, actions: caseActions(freshLate.map((l) => l.id)) })
  }, [freshLate, push]) // eslint-disable-line react-hooks/exhaustive-deps
  // jump to a case from anywhere (toast, team board, chatbot): make sure the filters show it, open it, scroll to it
  const showCase = useCallback((id) => {
    setPage('queue'); setView('cases'); setIntakeOpen(false)
    setFilters((f) => {
      const c = casesRef.current.find((x) => x.id === id)
      return c && applyFilters([c], f).rows.length ? f : { ...DEFAULT_FILTERS, status: 'all' }
    })
    setSelected(id)
  }, [])
  const casesRef = useRef([])
  casesRef.current = cases
  const caseActions = (ids) => [...ids.slice(0, 4).map((id) => ({ label: `ดู ${id}`, onClick: () => showCase(id) })),
    ...(ids.length > 4 ? [{ label: `+${ids.length - 4} เคส`, onClick: () => setFilters({ ...DEFAULT_FILTERS, status: 'todo' }) }] : [])]
  const [loaded, setLoaded] = useState(false)
  const fresh = useNewItems(loaded ? cases : null)
  useEffect(() => {                         // a new red case came in -> sound + toast (+ system notification if allowed)
    const open = fresh.filter((c) => c.status !== 'resolved')
    const red = open.filter((c) => c.priority === 'red')
    if (red.length) push(`🔴 เคสแดงใหม่ ${red.length} เคส — ${red[0].summary || ''}`, 'red', { sound: true, system: true, actions: caseActions(red.map((c) => c.id)) })
    else if (open.length) push(`📥 เคสใหม่ ${open.length} เคส`, 'info', { actions: caseActions(open.map((c) => c.id)) })
  }, [fresh, push]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 5000) // ทั้งรัฐและอาสาเห็นข้อมูลอัปเดตทุก 5 วินาที
    return () => clearInterval(t)
  }, [refresh])

  useEffect(() => {
    api.health().then((h) => {
      const a = h.agent || {}
      setAgentDown(a.ok === false)
      setProvider(a.ok === false ? 'agent offline' : `${a.strategy || ''} · ${a.own_model || 'no model'}${a.llm ? ' + ' + a.llm : ''}`)
    }).catch(() => {})
  }, [])

  // show a case / place on the map (from chatbot cards or URL)
  const focusOn = useCallback((t) => {
    if (!t) return
    setView('map')          // on phones: jump to the map screen
    if (t.case) {
      const c = cases.find((x) => x.id === t.case)
      if (!c) { setPendingFocus(t); return }
      showCase(c.id); setView('map')
      if (c.lat) setFocus({ key: Date.now(), lat: c.lat, lng: c.lng })
    } else if (t.place) {
      const p = places.find((x) => x.id === t.place)
      if (!p) { setPendingFocus(t); return }
      setFocus({ key: Date.now(), lat: p.lat, lng: p.lng, place: p.id })
    }
  }, [cases, places, showCase])

  useEffect(() => {        // resolve a focus request once the data it needs has loaded
    if (!pendingFocus) return
    const ready = pendingFocus.case ? cases.some((c) => c.id === pendingFocus.case) : places.some((p) => p.id === pendingFocus.place)
    if (ready) { const t = pendingFocus; setPendingFocus(null); focusOn(t) }
  }, [pendingFocus, cases, places, focusOn])

  const visibleCases = applyFilters(cases, filters).rows       // the map shows exactly what the list shows
  const pickStat = (k) => {                                     // header numbers are shortcuts into the queue
    setPage('queue'); setView('cases')
    if (k === 'open') setFilters({ ...DEFAULT_FILTERS, status: 'open' })
    else if (k === 'unassigned_red') setFilters({ ...DEFAULT_FILTERS, status: 'open', colors: ['red'], team: '__none' })
    else setFilters({ ...DEFAULT_FILTERS, status: 'open', colors: [k] })
  }
  const locate = (c) => { setSelected(c.id); if (c.lat) setFocus({ key: Date.now(), lat: c.lat, lng: c.lng }); setView('map') }
  const update = async (id, patch) => {
    try { await api.updateCase(id, patch) } catch (e) { alert(e.message) }
    refresh()
  }
  const seed = async () => {
    if (!confirm('โหลดข้อความจำลอง 40 ข้อความ? (เดโมชุดเก่าจะถูกแทนที่ เคสจริงไม่ถูกลบ)')) return
    await api.seed(40); refresh()
  }
  const deleteDemo = async () => {
    if (!confirm('ลบเคสเดโมทั้งหมด? เคสที่ส่งเข้ามาจริงจะไม่ถูกลบ')) return
    const r = await api.deleteDemo(); alert(`ลบเคสเดโมแล้ว ${r.cases} เคส`); refresh()
  }
  const resetAll = async () => {
    if (prompt('ล้างข้อมูลทั้งหมด (ทุกเคส ทุกข้อความ ทุกรูป) — กู้คืนไม่ได้\nพิมพ์คำว่า ลบทั้งหมด เพื่อยืนยัน') !== 'ลบทั้งหมด') return
    const r = await api.resetAll(); alert(`ล้างแล้ว ${r.cases} เคส`); refresh()
  }

  useEffect(() => {        // close the ⋯ menu when tapping elsewhere
    const close = (e) => document.querySelectorAll('details.menu[open]').forEach((d) => !d.contains(e.target) && d.removeAttribute('open'))
    document.addEventListener('pointerdown', close); return () => document.removeEventListener('pointerdown', close)
  }, [])
  const redOpen = stats?.open_by_priority?.red || 0
  const pane = (v) => `pane pane-${v} ${view === v ? 'on' : ''}`

  return (
    <div className={`app ${isMobile ? 'is-mobile' : ''}`}>
      <header className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden>≋</span>
          <div>
            <h1>FloodLink</h1>
            <p>ศูนย์ประสานงานร่วม รัฐ × อาสา</p>
          </div>
        </div>
        <a className="sos" href="tel:1669" title="เจ็บป่วยฉุกเฉิน">☎ 1669</a>
        <details className="menu">
          <summary aria-label="เมนู">⋯</summary>
          <div className="menu-pop">
            <div className="provider" title="Intake AI Agent">🤖 {provider || 'กำลังเชื่อมต่อ…'}</div>
            <a href="tel:1784">☎ 1784 สายด่วน ปภ.</a>
            <a href="tel:1669">☎ 1669 เจ็บป่วยฉุกเฉิน</a>
            <button className="ghost" onClick={() => setPage(page === 'teams' ? 'queue' : 'teams')}>{page === 'teams' ? '← กลับคิวเคส' : '👥 ชุดปฏิบัติการ'}</button>
            <button className="ghost" onClick={() => go('/public')}>📊 หน้าสาธารณะ</button>
            <button className="ghost" onClick={() => go('/')}>📝 หน้าแจ้งเหตุ (ผู้ประสบภัย)</button>
            {isAdmin && <>
              <button className="ghost" onClick={() => setPage(page === 'admin' ? 'queue' : 'admin')}>{page === 'admin' ? '← กลับคิวเคส' : '⚙️ จัดการระบบ'}</button>
              <button className="ghost" onClick={seed}>โหลดข้อมูลเดโม</button>
              <button className="ghost" onClick={deleteDemo}>🗑 ลบเคสเดโม</button>
              <button className="ghost warn-btn" onClick={resetAll}>⚠️ ล้างข้อมูลทั้งหมด</button>
            </>}
          </div>
        </details>
        <UserMenu user={user} onLogout={onLogout} />
        <StatsBar stats={stats} onPick={pickStat} extra={
          <button className={`stat team-btn ${late?.length ? 'alert' : ''}`} onClick={() => setPage('teams')} title="ชุดปฏิบัติการ">
            <b>{teams.filter((t) => t.status === 'available' && t.lead?.active).length}/{teams.filter((t) => t.lead?.active).length}</b>
            <span>{late?.length ? `⏳ ไม่ตอบรับ ${late.length}` : '👥 ชุดว่าง'}</span>
          </button>} />
      </header>
      {error && <div className="error">{error}</div>}
      {agentDown && <div className="error">⚠️ Intake AI Agent ออฟไลน์ — รับเรื่องใหม่ไม่ได้ชั่วคราว (docker compose logs agent)</div>}
      {page === 'admin' && <AdminPanel onBack={() => setPage('queue')} onChanged={refresh} />}
      {page === 'teams' && <TeamsPanel onBack={() => setPage('queue')} onShowCase={showCase} />}
      {!adminView && <>
      <main className="layout">
        <section className="left">
          {isMobile && <div className={pane('report')}><SubmitForm onDone={refresh} onSeeCases={() => setView('cases')} /></div>}
          <div className={pane('cases')}>
            <CaseList cases={cases} filters={filters} setFilters={setFilters} onNew={isMobile ? null : () => setIntakeOpen(true)}
              selected={selected} setSelected={setSelected} onUpdate={update} onLocate={locate} onChanged={refresh} teams={teams} />
          </div>
        </section>
        <section className={`right ${pane('map')}`}>
          <CaseMap cases={visibleCases} hazards={hazards} places={places} selected={selected} setSelected={setSelected}
            focus={focus} visible={!isMobile || view === 'map'} />
        </section>
      </main>
      {intakeOpen && !isMobile && (
        <div className="modal" role="dialog" aria-label="รับเรื่องใหม่" onClick={() => setIntakeOpen(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <button className="modal-x" onClick={() => setIntakeOpen(false)} aria-label="ปิด">✕</button>
            <SubmitForm onDone={refresh} onSeeCases={() => setIntakeOpen(false)} />
          </div>
        </div>
      )}
      <ChatWidget open={showChat} fab={!isMobile} fullscreen={isMobile}
        onToggle={() => setChatOpen((v) => !v)} onClose={() => (isMobile ? setView('cases') : setChatOpen(false))}
        onFocus={focusOn} onChanged={refresh} />
      </>}
      {toasts}
      {isMobile && !adminView && (
        <nav className="bottom-nav" aria-label="เมนูหลัก">
          {TABS.map(([k, icon, label]) => (
            <button key={k} className={view === k ? 'on' : ''} onClick={() => setView(k)} aria-current={view === k ? 'page' : undefined}>
              <span className="ico" aria-hidden>{icon}</span>{label}
              {k === 'cases' && redOpen > 0 && <span className="dot">{redOpen}</span>}
            </button>
          ))}
        </nav>
      )}
    </div>
  )
}

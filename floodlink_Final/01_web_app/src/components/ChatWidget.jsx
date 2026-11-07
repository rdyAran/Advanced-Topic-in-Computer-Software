import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'

const SESSION = 'web-' + Math.random().toString(36).slice(2, 10)

// minimal markdown: **bold**, _italic_, line breaks
function Md({ text }) {
  const html = (text || '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/(^|\s)_(.+?)_(?=\s|$)/g, '$1<i>$2</i>')
    .replace(/\n/g, '<br/>')
  return <div className="md" dangerouslySetInnerHTML={{ __html: html }} />
}

function Card({ c, onFocus }) {
  return (
    <div className={`chat-card ${c.kind}`}>
      <div className="cc-title">{c.title}</div>
      {c.subtitle && <div className="cc-sub">{c.subtitle}</div>}
      {c.lines?.filter(Boolean).map((l, i) => <div className="cc-line" key={i}>{l}</div>)}
      <div className="cc-actions">
        {c.nav_url && <a className="nav-btn small" href={c.nav_url} target="_blank" rel="noopener noreferrer">🧭 นำทาง</a>}
        {c.tel && <a className="ghost-btn" href={`tel:${c.tel}`}>☎ โทร</a>}
        {onFocus && <button className="ghost-btn" onClick={() => onFocus(c.kind === 'case' ? { case: c.id } : { place: c.id })}>🗺 ดูบนแผนที่</button>}
        {c.page_url && <a className="ghost-btn" href={c.page_url} target="_blank" rel="noopener noreferrer">
          {c.page_url.includes('/track/') ? '🔗 ติดตามเคส' : '🔗 ลิงก์หน้าเพจ'}</a>}
      </div>
    </div>
  )
}

export default function ChatWidget({ open, fab = true, fullscreen = false, onToggle, onClose, onFocus, onChanged }) {
  const [msgs, setMsgs] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [loc, setLoc] = useState(null)
  const end = useRef(null)

  useEffect(() => { if (open && msgs.length === 0) send('สวัสดี', true) }, [open])
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs, busy])

  const send = async (text, silent = false, coords = loc) => {
    if (!text.trim()) return
    if (!silent) setMsgs((m) => [...m, { me: true, text }])
    setInput(''); setBusy(true)
    try {
      const r = await api.chat(text, SESSION, coords?.lat, coords?.lng)
      setMsgs((m) => [...m, { me: false, ...r }])
      if (['request_help', 'emergency'].includes(r.intent)) onChanged?.()      // new case -> refresh dashboard
    } catch (e) {
      setMsgs((m) => [...m, { me: false, reply: '⚠️ เชื่อมต่อไม่ได้: ' + e.message + '\nถ้าฉุกเฉินโทร 1669 หรือ 1784' }])
    } finally { setBusy(false) }
  }

  const shareLocation = (then) => {
    if (!navigator.geolocation) return send('ส่งตำแหน่งไม่ได้ เบราว์เซอร์ไม่รองรับ', true)
    navigator.geolocation.getCurrentPosition(
      (p) => { const c = { lat: p.coords.latitude, lng: p.coords.longitude }; setLoc(c); send(then || 'นี่คือตำแหน่งของฉัน', false, c) },
      () => setMsgs((m) => [...m, { me: false, reply: 'หาตำแหน่งไม่ได้ ลองพิมพ์ชื่อย่าน/ซอยแทนได้ครับ' }]),
      { enableHighAccuracy: true, timeout: 10000 })
  }
  const quick = (q) => (q.startsWith('📍') ? shareLocation() : send(q))
  const last = msgs[msgs.length - 1]

  return (
    <>
      {fab && (
        <button className={`chat-fab ${open ? 'open' : ''}`} onClick={onToggle} aria-label={open ? 'ปิดแชท' : 'เปิดแชทผู้ช่วย'}>
          {open ? '✕' : '💬 ผู้ช่วย'}
        </button>
      )}
      {open && (
        <div className={`chat-panel ${fullscreen ? 'full' : ''}`} role="dialog" aria-label="ผู้ช่วย FloodLink">
          <div className="chat-head">
            <div>
              <b>💬 ผู้ช่วย FloodLink</b>
              <span className="muted small">ขอความช่วยเหลือ · บริจาค · ศูนย์พักพิง · สถานะเคส</span>
            </div>
            <button className="chat-close" onClick={onClose} aria-label="ปิดแชท">✕</button>
          </div>
          <div className="chat-body">
            {msgs.map((m, i) => (
              <div key={i} className={`bubble ${m.me ? 'me' : 'bot'}`}>
                {m.me ? m.text : <>
                  <Md text={m.reply} />
                  {m.cards?.map((c) => <Card key={c.id} c={c} onFocus={onFocus} />)}
                  {m.links?.length > 0 && <div className="cc-actions">{m.links.map((l) => <a key={l.url} className="ghost-btn" href={l.url} target="_blank" rel="noopener noreferrer">{l.label}</a>)}</div>}
                  {m.sources?.length > 0 && <div className="sources">ที่มา: {[...new Set(m.sources.map((s) => s.title))].join(' · ')}</div>}
                </>}
              </div>
            ))}
            {busy && <div className="bubble bot typing">กำลังพิมพ์…</div>}
            <div ref={end} />
          </div>
          {!busy && last && !last.me && last.quick_replies?.length > 0 && (
            <div className="quick">{last.quick_replies.map((q) => <button key={q} onClick={() => quick(q)}>{q}</button>)}</div>
          )}
          <form className="chat-input" onSubmit={(e) => { e.preventDefault(); send(input) }}>
            <button type="button" className={`loc ${loc ? 'on' : ''}`} title="ส่งตำแหน่งของฉัน" onClick={() => shareLocation()}>📍</button>
            <input value={input} onChange={(e) => setInput(e.target.value)} enterKeyHint="send"
              placeholder="พิมพ์คำถามที่นี่…" aria-label="ข้อความถึงผู้ช่วย" />
            <button disabled={busy || !input.trim()} aria-label="ส่ง">ส่ง</button>
          </form>
        </div>
      )}
    </>
  )
}

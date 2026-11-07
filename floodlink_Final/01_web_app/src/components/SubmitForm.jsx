import { useEffect, useMemo, useRef, useState } from 'react'
import { api, trackUrl } from '../api.js'
import { FLAGS, NEEDS, WATER, PRIORITY, peopleText } from '../labels.js'
import NavButton from './NavButton.jsx'
import FollowupForm from './FollowupForm.jsx'
import { MAX_PHOTOS, shrinkPhoto } from '../photos.js'

const EXAMPLE = 'ช่วยญาติผมด้วยครับ ซอยโรงเรียนกอบกาญจน์ ถนนเพชรเกษม ผู้ใหญ่5 เด็ก1ขวบกับ3ขวบ ยายอายุ92ติดเตียง ลุงอายุ72ต้องฟอกไตไม่ได้ฟอกตั้งแต่วันอังคาร ติดมา5วัน น้ำขึ้นชั้น2แล้ว'
const EXAMPLE_MULTI = `ฝากแชร์ด่วน คลองแห โทร 081-234-5678
เคส 1 บ้านเลขที่ 12 ซ.คลองแห 2 ยายอายุ 85 ติดเตียง น้ำถึงชั้น 2
เคส 2 บ้านเลขที่ 40 ซ.คลองแห 4 ผู้ใหญ่ 3 คน เด็ก 2 ขวบ น้ำถึงอก ไม่มีอาหาร
เคส 3 ซ.คลองแห 6 ลุงฟอกไต ขอเรือ พิกัด 7.0301, 100.4862`
const ACTION = { created: 'สร้างเคสใหม่', merged: 'รวมเข้ากับเคสเดิม (ซ้ำ)', resolved: 'ปิดเคส', hazard: 'ปักหมุดจุดอันตราย', logged: 'บันทึกไว้ (ไม่ใช่คำขอ)' }

// live checklist: what the text already contains (rough, client-side — the AI does the real reading)
const CHECKS = [
  { key: 'location', label: 'ตำแหน่ง', rx: /บ้านเลขที่|ซ\.|ซอย|ถ\.|ถนน|หมู่|ใกล้|ตรงข้าม|หลัง|พิกัด|maps|\d+\.\d{3,}\s*,\s*\d+\.\d{3,}|คอหงส์|ครูจีน|เพชรเกษม|คลองแห|คลองเตย|บ้านพรุ|ควนลัง|ทุ่งเสา|น้ำน้อย|เขต\s*8/i },
  { key: 'contact', label: 'เบอร์โทร', rx: /0\d[\d-]{7,}/ },
  { key: 'people', label: 'จำนวนคน', rx: /\d+\s*(คน|ชีวิต)|ผู้ใหญ่|อยู่คนเดียว|สองคน|สามคน|สี่คน|ห้าคน/ },
  { key: 'vulnerable', label: 'ผู้ป่วย/เปราะบาง', rx: /ติดเตียง|ฟอกไต|หัวใจ|ท้อง|ครรภ์|บาดเจ็บ|เลือด|พิการ|เดินไม่ได้|ทารก|เด็ก|ผู้สูงอายุ|ยาย|ตา\s*\d|อายุ|ไม่มี(ใคร|คน)ป่วย/ },
  { key: 'water', label: 'ระดับน้ำ', rx: /เข่า|เอว|อก|ชั้น|หลังคา|ตาตุ่ม|ท่วม/ },
  { key: 'building', label: 'ที่พักกี่ชั้น', rx: /ชั้นเดียว|(?:บ้าน|ตึก|อาคาร|ทาวน์|ห้องแถว|ตึกแถว)\S{0,8}\s*(?:\d|สอง|สาม)\s*ชั้น|คอนโด|อาคารสูง|แฟลต/ },
  { key: 'needs', label: 'สิ่งที่ต้องการ', rx: /เรือ|อพยพ|อาหาร|ข้าว|น้ำดื่ม|นม|ยา(?!ย)|แบต|ไฟ/ },
]

// the kind of place + water height: "บ้านชั้นเดียว น้ำถึงเอว" is more dangerous than "บ้าน 2 ชั้น น้ำมิดชั้น 1" (they can go upstairs)
const BUILDINGS = [['บ้านชั้นเดียว', 1, '🏠'], ['บ้าน 2 ชั้น', 2, '🏡'], ['บ้าน/ตึก 3 ชั้นขึ้นไป', 3, '🏢'], ['คอนโด/อาคารสูง', 4, '🏬']]
const WATER_BY = {
  1: ['น้ำถึงเข่า', 'น้ำถึงเอว', 'น้ำถึงอก', 'น้ำเกือบมิดหลังคา ขึ้นไปอยู่บนหลังคา'],
  2: ['น้ำถึงเข่า', 'น้ำถึงเอว', 'น้ำมิดชั้น 1 ยังไม่ถึงชั้น 2 (อยู่ชั้น 2)', 'น้ำถึงชั้น 2 แล้ว', 'ขึ้นไปอยู่บนหลังคา'],
  3: ['น้ำถึงเข่า', 'น้ำถึงเอว', 'น้ำมิดชั้น 1 อยู่ชั้นบน', 'น้ำถึงชั้น 2 แล้ว'],
  4: ['น้ำท่วมชั้นล่าง ลงมาไม่ได้', 'ไฟดับ ลิฟต์ใช้ไม่ได้'],
}
const setLine = (text, label, value) => {           // replace "ที่พัก: ..." (or add it) so tapping again does not repeat it
  const lines = (text || '').split('\n')
  const i = lines.findIndex((l) => l.trim().startsWith(label))
  if (i >= 0) lines[i] = `${label} ${value}`
  else lines.push(`${label} ${value}`)
  return lines.filter((l, k) => l.trim() || k < lines.length - 1).join('\n').replace(/^\n+/, '')
}
function PlacePicker({ text, setText }) {
  const line = (label) => ((text || '').split('\n').find((l) => l.trim().startsWith(label)) || '').slice(label.length).trim()
  const b = BUILDINGS.find(([name]) => line('ที่พัก:') === name)
  const w = line('ระดับน้ำ:')
  return (
    <div className="place-pick">
      <div className="pp-row"><span className="pp-label">ที่พัก</span>
        {BUILDINGS.map(([name, n, ico]) => (
          <button type="button" key={name} className={`pp-chip ${b?.[1] === n ? 'on' : ''}`} onClick={() => setText((t) => {
            const out = setLine(t, 'ที่พัก:', name)                 // a water answer that does not fit the new place is removed
            return w && !WATER_BY[n].includes(w) ? out.split('\n').filter((l) => !l.trim().startsWith('ระดับน้ำ:')).join('\n') : out
          })}>{ico} {name}</button>
        ))}
      </div>
      {b && (
        <div className="pp-row"><span className="pp-label">น้ำตอนนี้</span>
          {WATER_BY[b[1]].map((x) => (
            <button type="button" key={x} className={`pp-chip ${w === x ? 'on' : ''}`} onClick={() => setText((t) => setLine(t, 'ระดับน้ำ:', x))}>{x}</button>
          ))}
        </div>
      )}
      {b?.[1] === 1 && <p className="pp-warn">⚠️ บ้านชั้นเดียว: ถ้าน้ำถึงอกหรือขึ้นเร็ว ไม่มีชั้นบนให้หนี — ระบบจัดเป็นเคสเร่งด่วน ถ้าอันตรายตอนนี้โทร 1784 / 1669</p>}
    </div>
  )
}

export default function SubmitForm({ onDone, onSeeCases, mode = 'staff' }) {
  const pub = mode === 'public'
  const [text, setText] = useState('')
  const [channel, setChannel] = useState(pub ? 'web_form' : 'phone_transcript')
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState(null)
  const [guide, setGuide] = useState(null)
  const [showGuide, setShowGuide] = useState(false)
  const [geoMsg, setGeoMsg] = useState('')
  const [photos, setPhotos] = useState([])          // [{name, dataUrl, kb}] already shrunk in the browser
  const [photoMsg, setPhotoMsg] = useState('')
  const [noTraining, setNoTraining] = useState(false)       // PDPA: the reporter may refuse use for AI training

  useEffect(() => { api.guide().then(setGuide).catch(() => {}) }, [])
  const checks = useMemo(() => CHECKS.map((c) => ({ ...c, ok: c.rx.test(text) })), [text])

  const addMyLocation = () => {
    if (!navigator.geolocation) return setGeoMsg('เบราว์เซอร์นี้ไม่รองรับ GPS')
    setGeoMsg('กำลังหาตำแหน่ง…')
    navigator.geolocation.getCurrentPosition(
      (p) => {
        const s = `พิกัด ${p.coords.latitude.toFixed(6)}, ${p.coords.longitude.toFixed(6)}`
        setText((t) => (t ? t.trimEnd() + ' ' : '') + s); setGeoMsg(`แนบแล้ว (แม่นยำ ±${Math.round(p.coords.accuracy)} ม.)`)
      },
      (err) => setGeoMsg('หาตำแหน่งไม่ได้: ' + err.message), { enableHighAccuracy: true, timeout: 10000 })
  }

  const addPhotos = async (e) => {
    const files = [...(e.target.files || [])]
    e.target.value = ''                                // same photo can be picked again after removing it
    const room = MAX_PHOTOS - photos.length
    if (files.length > room) setPhotoMsg(`แนบได้สูงสุด ${MAX_PHOTOS} รูป`)
    setPhotoMsg('กำลังย่อรูป…')
    const out = []
    for (const f of files.slice(0, Math.max(room, 0))) {
      try { out.push(await shrinkPhoto(f)) } catch (err) { setPhotoMsg(err.message) }
    }
    setPhotos((p) => [...p, ...out].slice(0, MAX_PHOTOS))
    if (out.length) setPhotoMsg(files.length > room ? `แนบได้สูงสุด ${MAX_PHOTOS} รูป` : '')
  }
  const removePhoto = (i) => setPhotos((p) => p.filter((_, k) => k !== i))

  const submit = async (e) => {
    e.preventDefault()
    if (!text.trim()) return
    setBusy(true)
    try {
      setRes(await api.sendMessage(text, channel, photos.map((p) => p.dataUrl), noTraining))
      setText(''); setGeoMsg(''); setPhotos([]); setPhotoMsg(''); onDone?.()
    } catch (err) {
      setRes({ error: err.message })
    } finally { setBusy(false) }
  }
  const results = res?.results || (res?.extraction ? [res] : [])
  const resultRef = useRef(null)
  useEffect(() => {                         // after sending, bring the answer (and what is still missing) into view
    if (res && !res.error) setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60)
  }, [res])
  if (pub && results.some((r) => r.case_id)) {
    return <PublicResult res={res} results={results} innerRef={resultRef} onNew={() => setRes(null)} />
  }

  return (
    <div className="card intake">
      <div className="card-head">
        <h2>{pub ? 'แจ้งขอความช่วยเหลือ' : 'รับเรื่อง (โทรศัพท์ / ข้อความจากช่องทางอื่น)'}</h2>
        <div className="links">
          <button className="link" type="button" onClick={() => setShowGuide((v) => !v)}>{showGuide ? 'ซ่อนคำแนะนำ' : 'ควรกรอกอะไรบ้าง?'}</button>
          {!pub && <button className="link" type="button" onClick={() => setText(EXAMPLE)}>ตัวอย่าง</button>}
          {!pub && <button className="link" type="button" onClick={() => setText(EXAMPLE_MULTI)}>ตัวอย่างหลายเคส</button>}
        </div>
      </div>

      {showGuide && guide && (
        <div className="guide">
          <b>{guide.title}</b>
          <ol>
            {guide.items.map((it) => (
              <li key={it.key}><b>{it.label}</b> — <span className="muted">{it.why}</span><br />
                <span className="eg">เช่น {it.examples.join(' · ')}</span></li>
            ))}
          </ol>
          <p className="tip">💡 {guide.multi_case_tip}</p>
          <button type="button" className="ghost" onClick={() => setText(guide.template)}>ใส่แบบฟอร์มให้กรอก</button>
        </div>
      )}

      <form onSubmit={submit}>
        <textarea rows={5} value={text} onChange={(e) => setText(e.target.value)}
          placeholder={pub ? 'เล่าสั้น ๆ ว่าอยู่ที่ไหน กี่คน มีผู้ป่วย/ผู้สูงอายุ/เด็กไหม น้ำสูงแค่ไหน ต้องการอะไร และเบอร์ที่โทรกลับได้\nแจ้งแทนญาติได้ · มีหลายบ้านใส่ เคส 1, เคส 2 ได้'
            : 'วางข้อความขอความช่วยเหลือ (มีหลายบ้านในข้อความเดียวได้ — AI จะแยกเคสให้)\nใส่: ตำแหน่ง · เบอร์โทร · จำนวนคน · ผู้ป่วย · ระดับน้ำ · สิ่งที่ต้องการ'} />
        <PlacePicker text={text} setText={setText} />
        <div className="checklist">
          {checks.map((c) => <span key={c.key} className={c.ok ? 'ok' : 'todo'}>{c.ok ? '✓' : '○'} {c.label}</span>)}
        </div>
        {photos.length > 0 && (
          <div className="photo-pick">
            {photos.map((p, i) => (
              <div className="thumb-wrap" key={i}>
                <img src={p.dataUrl} alt={`รูปที่ ${i + 1}`} />
                <button type="button" className="thumb-x" onClick={() => removePhoto(i)} aria-label={`ลบรูปที่ ${i + 1}`}>✕</button>
                <span className="thumb-kb">{p.kb} KB</span>
              </div>
            ))}
          </div>
        )}
        <div className="row form-row">
          <button type="button" className="ghost geo" onClick={addMyLocation} title="ใช้เมื่อผู้แจ้งอยู่ที่จุดเกิดเหตุ">📍 แนบตำแหน่งปัจจุบัน</button>
          <label className={`ghost photo-btn ${photos.length >= MAX_PHOTOS ? 'disabled' : ''}`} title="รูประดับน้ำ บ้าน หรือผู้ป่วย ช่วยให้ทีมตัดสินใจ">
            📷 แนบรูป{photos.length ? ` (${photos.length}/${MAX_PHOTOS})` : ''}
            <input type="file" accept="image/*" multiple hidden disabled={photos.length >= MAX_PHOTOS} onChange={addPhotos} />
          </label>
          {photoMsg && <span className="muted small geo-msg">{photoMsg}</span>}
          {geoMsg && <span className="muted small geo-msg">{geoMsg}</span>}
          <span className="spacer" />
          {!pub && (
            <select aria-label="ช่องทางที่รับข้อความ" value={channel} onChange={(e) => setChannel(e.target.value)}>
              <option value="phone_transcript">โทรศัพท์</option>
              <option value="facebook_page">Facebook</option>
              <option value="line_group">LINE</option>
              <option value="traffy">Traffy Fondue</option>
              <option value="web_form">เว็บฟอร์ม</option>
            </select>
          )}
          <button className="primary" disabled={busy || !text.trim()}>{busy ? 'AI กำลังอ่าน…' : pub ? 'ส่งเรื่อง' : 'ส่งให้ AI คัดแยก'}</button>
        </div>
        {pub && (
          <label className="consent small">
            <input type="checkbox" checked={noTraining} onChange={(e) => setNoTraining(e.target.checked)} />
            ไม่ยินยอมให้ใช้ข้อความนี้ปรับปรุง AI (ไม่มีผลกับการช่วยเหลือ)
          </label>
        )}
      </form>

      {res?.error && <div className="error small">{res.error}</div>}
      {results.length > 0 && (
        <div className="result">
          <button type="button" className="link close-result" onClick={() => setRes(null)} aria-label="ซ่อนผลลัพธ์">✕ ซ่อน</button>
          {res.n_cases > 1 && <div className="split-banner">✂️ AI แยกได้ <b>{res.n_cases} เคส</b> ({res.split_method})</div>}
          {res.split_note && res.n_cases <= 1 && <div className="split-hint">💡 {res.split_note}</div>}
          {res.photos?.length > 0 && <div className="split-hint">📷 แนบรูป {res.photos.length} รูป — ทีมเห็นในการ์ดเคส</div>}
          {res.track_token && results.some((r) => r.case_id) && <TrackLinkCard token={res.track_token} pub={pub} />}
          {results.map((r, i) => <ResultItem key={r.message_id || i} r={r} index={results.length > 1 ? i + 1 : null} onDone={onDone}
            pub={pub} token={res.track_token} />)}
          {onSeeCases && <button type="button" className="ghost see-cases" onClick={onSeeCases}>📋 ไปที่คิวเคส</button>}
        </div>
      )}
    </div>
  )
}

// the reporter's private link: status, add more info later, "ปลอดภัยแล้ว" — no login needed
export function TrackLinkCard({ token, pub }) {
  const url = trackUrl(token)
  const [copied, setCopied] = useState(false)
  const copy = () => navigator.clipboard?.writeText(url).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000) })
  const share = () => navigator.share?.({ title: 'ติดตามเคส FloodLink', url }).catch(() => {})
  return (
    <div className="track-card">
      <b>🔗 {pub ? 'ลิงก์ติดตามเคสของคุณ' : 'ลิงก์ติดตามสำหรับผู้แจ้ง'}</b>
      <p className="small">{pub ? 'เก็บลิงก์นี้ไว้ (แคปหน้าจอหรือคัดลอก) — ใช้ดูสถานะ ส่งข้อมูล/รูปเพิ่ม หรือแจ้งว่าปลอดภัยแล้ว · อย่าโพสต์ในที่สาธารณะ'
        : 'ส่งให้ผู้แจ้งทาง SMS/แชท เพื่อให้เขาติดตามและส่งข้อมูลเพิ่มเองได้'}</p>
      <div className="track-url"><code>{url}</code></div>
      <div className="row">
        <button type="button" className="primary" onClick={copy}>{copied ? '✓ คัดลอกแล้ว' : '📋 คัดลอกลิงก์'}</button>
        {navigator.share && <button type="button" className="ghost" onClick={share}>↗ แชร์</button>}
        <a className="ghost" href={`/track/${token}`}>เปิดหน้าติดตาม</a>
      </div>
    </div>
  )
}

const STATE_TH = { partial: 'ยังไม่ชัด', missing: 'ยังขาด' }

// the reporter sees FIRST what the team still needs, with the box to send it right there
function NeedInfoBox({ r, token, index }) {
  const [need, setNeed] = useState(r.needs_info || [])
  const [text, setText] = useState('')
  const [photos, setPhotos] = useState([])
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [sent, setSent] = useState(0)
  const box = useRef(null)
  useEffect(() => { if (index <= 1 && need.length) box.current?.querySelector('textarea')?.focus({ preventScroll: true }) }, []) // eslint-disable-line
  const addLocation = () => {
    if (!navigator.geolocation) return setMsg('เครื่องนี้ไม่รองรับ GPS — พิมพ์บ้านเลขที่/ซอย/จุดสังเกตแทน')
    setMsg('กำลังหาตำแหน่ง…')
    navigator.geolocation.getCurrentPosition(
      (p) => { setText((t) => (t ? t.trimEnd() + ' ' : '') + `พิกัด ${p.coords.latitude.toFixed(6)}, ${p.coords.longitude.toFixed(6)}`); setMsg('✓ แนบพิกัดแล้ว กดส่งได้เลย') },
      (e) => setMsg('หาตำแหน่งไม่ได้ (' + e.message + ') — พิมพ์บ้านเลขที่/ซอย/จุดสังเกตแทน'), { enableHighAccuracy: true, timeout: 10000 })
  }
  const addPhotos = async (e) => {
    const files = [...(e.target.files || [])].slice(0, MAX_PHOTOS - photos.length); e.target.value = ''
    const out = []
    for (const f of files) { try { out.push(await shrinkPhoto(f)) } catch (err) { setMsg(err.message) } }
    setPhotos((x) => [...x, ...out].slice(0, MAX_PHOTOS))
  }
  const send = async () => {
    setBusy(true); setMsg('')
    try {
      const out = await api.trackFollowup(token, r.case_id, text, photos.map((p) => p.dataUrl))
      const left = (out.case?.checklist || []).filter((x) => x.level === 'need' && x.state !== 'ok')
      setNeed(left); setText(''); setPhotos([]); setSent((n) => n + 1)
      setMsg(left.length ? `✓ ได้รับแล้ว — ยังขาดอีก ${left.length} อย่าง` : '')
    } catch (e) { setMsg('ส่งไม่สำเร็จ: ' + e.message) } finally { setBusy(false) }
  }
  if (!need.length) {
    return <div className="need-box ok">✅ <b>ข้อมูลสำคัญครบแล้ว</b>{sent ? ' ขอบคุณค่ะ' : ''} — ทีมใช้ข้อมูลนี้ออกไปช่วยได้เลย ส่งรูปหรือข้อมูลเพิ่มได้ที่หน้าติดตาม</div>
  }
  return (
    <div className="need-box" ref={box} role="alert">
      <div className="need-head">⚠️ <b>ทีมยังต้องการข้อมูลอีก {need.length} อย่าง</b> เพื่อไปถึงคุณได้เร็วขึ้น</div>
      <ul className="need-list">{need.map((n) => (
        <li key={n.key}><span className={`ck-ico ${n.state}`}>{n.state === 'partial' ? '!' : '✗'}</span>
          <div><b>{n.label}</b> <span className={`ck-state ${n.state}`}>{STATE_TH[n.state]}</span><div className="ck-hint">{n.hint}</div></div></li>
      ))}</ul>
      <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)}
        placeholder={'พิมพ์ข้อมูลที่ขาดตรงนี้ เช่น\nบ้านเลขที่ 12 ซ.คลองแห 2 ตรงข้ามร้านข้าวมันไก่ · โทร 08x-xxx-xxxx · น้ำถึงเอว'} />
      {photos.length > 0 && <div className="photo-pick">{photos.map((p, i) => <div className="thumb-wrap" key={i}><img src={p.dataUrl} alt={`รูปที่ ${i + 1}`} /></div>)}</div>}
      <div className="need-row">
        {need.some((n) => n.key === 'location') && <button type="button" className="ghost" onClick={addLocation}>📍 ส่งตำแหน่งตอนนี้</button>}
        <label className="ghost photo-btn">📷 รูป<input type="file" accept="image/*" multiple hidden onChange={addPhotos} /></label>
        <button type="button" className="primary" disabled={busy || (!text.trim() && !photos.length)} onClick={send}>{busy ? 'กำลังส่ง…' : 'ส่งข้อมูลเพิ่ม'}</button>
      </div>
      {msg && <div className="small need-msg">{msg}</div>}
    </div>
  )
}

function PublicResult({ res, results, innerRef, onNew }) {
  const cases = results.filter((r) => r.case_id)
  const anyMissing = cases.some((r) => r.needs_info?.length)
  return (
    <div className="card intake public-result" ref={innerRef}>
      {res.duplicate_submit && <div className="split-hint">ส่งข้อความเดิมซ้ำ — ระบบใช้เคสเดิม ไม่สร้างเคสใหม่</div>}
      <div className={`sent-head ${anyMissing ? 'warn' : 'ok'}`}>
        <b>✅ ส่งเรื่องแล้ว{cases.length > 1 ? ` — แยกเป็น ${cases.length} เคส` : ''}</b>
        <span>{anyMissing ? 'แต่ยังขาดข้อมูลสำคัญ กรุณาส่งเพิ่มด้านล่าง' : 'ศูนย์ประสานได้รับเรื่องแล้ว'}</span>
      </div>
      {cases.map((r, i) => {
        const p = PRIORITY[r.priority] || PRIORITY.green
        return (
          <section key={r.case_id} className="pub-case" style={{ borderLeftColor: p.color }}>
            <div className="case-top"><span className="badge" style={{ background: p.color }}>{p.label}</span><b>เคส {r.case_id}</b>
              {r.action === 'merged' && <span className="dup">มีคนแจ้งบ้านนี้แล้ว — รวมข้อมูลให้</span>}</div>
            {r.extraction?.summary && <p className="case-sum">“{r.extraction.summary}”</p>}
            <NeedInfoBox r={r} token={res.track_token} index={i + 1} />
          </section>
        )
      })}
      <TrackLinkCard token={res.track_token} pub />
      <div className="row"><button type="button" className="ghost" onClick={onNew}>📝 แจ้งเรื่องใหม่ (บ้านอื่น / คนอื่น)</button></div>
    </div>
  )
}

function ResultItem({ r, index, onDone, pub, token }) {
  const ex = r.extraction
  return (
    <div className="result-item">
      <div className="result-line">
        {index && <span className="idx">#{index}</span>}
        <span className="tag">{ACTION[r.action]}</span>
        {r.case_id && <code>{r.case_id}</code>}
        {r.duplicate_score != null && <span className="muted">ความคล้าย {r.duplicate_score}</span>}
        {r.nav?.url && <NavButton nav={r.nav} small />}
      </div>
      {!pub && <div className="agent-trace">
        <span>🤖 ตัดสินโดย <b>{r.provider_used || '-'}</b></span>
        {r.confidence != null && <span>ความมั่นใจโมเดลเรา {Math.round(r.confidence * 100)}%</span>}
        {r.escalated && <span className="esc">↗ ส่งต่อ LLM: {r.escalation_reason}</span>}
        {r.pii_masked && Object.keys(r.pii_masked).length > 0 && (
          <span className="pii" title="ข้อมูลส่วนตัวถูกแทนด้วยรหัสก่อนส่งให้ AI ภายนอก แล้วเติมกลับบนเซิร์ฟเวอร์เรา">
            🔒 ปิดบังก่อนส่ง: {Object.entries(r.pii_masked).map(([k, v]) => `${k} ${v}`).join(' · ')}</span>)}
        {r.latency_ms != null && <span className="muted">{r.latency_ms} ms</span>}
      </div>}
      {!pub && r.ai_error && <div className="error small">⚠️ LLM ใช้งานไม่ได้ ระบบใช้คำตอบจากโมเดลของเราแทน: {r.ai_error}</div>}
      {ex.summary && <p className="summary">“{ex.summary}”</p>}
      <div className="chips">
        {ex.area && <span className="chip">📍 {ex.area}</span>}
        {ex.water_level && <span className="chip">🌊 {WATER[ex.water_level]}</span>}
        {peopleText(ex) && <span className="chip">👥 {peopleText(ex)}</span>}
        {ex.flags.map((f) => <span className="chip warn" key={f}>{FLAGS[f]}</span>)}
        {ex.needs.map((n) => <span className="chip need" key={n}>ต้องการ{NEEDS[n]}</span>)}
      </div>
      {r.followup && <pre className="followup">↩ ข้อความตอบกลับอัตโนมัติ{'\n'}{r.followup}</pre>}
      {r.case_id && r.missing_fields?.length > 0 && <FollowupForm caseId={r.case_id} missing={r.missing_fields} onDone={onDone} track={token} />}
    </div>
  )
}

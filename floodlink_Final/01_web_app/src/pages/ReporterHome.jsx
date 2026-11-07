import { useState } from 'react'
import SubmitForm from '../components/SubmitForm.jsx'
import ChatWidget from '../components/ChatWidget.jsx'
import { go } from '../App.jsx'

// Landing page for people who need help (or report for a relative). No login: each report gets a private tracking link.
export default function ReporterHome({ user }) {
  const [chat, setChat] = useState(false)
  const [link, setLink] = useState('')
  const openLink = (e) => {
    e.preventDefault()
    const m = link.trim().match(/([\w-]{16,})\/?$/)
    if (m) go(`/track/${m[1]}`)
  }
  return (
    <div className="public-shell">
      <header className="topbar slim">
        <div className="brand">
          <span className="logo" aria-hidden>≋</span>
          <div><h1>FloodLink</h1><p>แจ้งขอความช่วยเหลือน้ำท่วม · หาดใหญ่</p></div>
        </div>
        <span className="spacer" />
        <button className="ghost" onClick={() => go('/public')}>📊 สถานการณ์</button>
        <button className="ghost" onClick={() => go('/staff')}>{user ? '🧑‍🚒 ไปหน้าเจ้าหน้าที่' : '🔐 เจ้าหน้าที่'}</button>
      </header>
      <main className="public-main">
        <div className="hotline">
          <b>อันตรายถึงชีวิตตอนนี้?</b> โทรก่อนเลย
          <a href="tel:1669" className="sos big">☎ 1669 เจ็บป่วยฉุกเฉิน</a>
          <a href="tel:1784" className="sos big alt">☎ 1784 ปภ.</a>
        </div>
        <SubmitForm mode="public" />
        <form className="card have-link" onSubmit={openLink}>
          <b>เคยแจ้งแล้ว?</b> <span className="muted small">วางลิงก์ติดตามที่ได้รับ เพื่อดูสถานะหรือส่งข้อมูลเพิ่ม</span>
          <div className="row">
            <input value={link} onChange={(e) => setLink(e.target.value)} placeholder="https://…/track/xxxxxxxx" aria-label="ลิงก์ติดตามเคส" />
            <button className="ghost" disabled={!/[\w-]{16,}/.test(link)}>เปิด</button>
          </div>
        </form>
        <p className="muted small privacy-note">🔒 ข้อมูลของคุณ (ชื่อ เบอร์ ที่อยู่ รูป) เห็นเฉพาะเจ้าหน้าที่ศูนย์ประสานและทีมที่ได้รับมอบหมายเท่านั้น
          · ถ้า AI ในระบบไม่มั่นใจ ข้อความ (ตัดเบอร์ บ้านเลขที่ พิกัด และชื่อออกแล้ว) อาจถูกส่งให้ AI ภายนอกช่วยอ่าน
          และอาจถูกใช้ปรับปรุง AI ให้คัดแยกเคสได้แม่นขึ้น — เลือกไม่ยินยอมได้ใต้ปุ่มส่ง</p>
      </main>
      <ChatWidget open={chat} fab onToggle={() => setChat((v) => !v)} onClose={() => setChat(false)} onFocus={null} onChanged={() => {}} />
    </div>
  )
}

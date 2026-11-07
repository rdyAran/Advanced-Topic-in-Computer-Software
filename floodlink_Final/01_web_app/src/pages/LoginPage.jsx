import { useState } from 'react'
import { api } from '../api.js'
import { go } from '../App.jsx'

export default function LoginPage({ onLogin }) {
  const [u, setU] = useState('')
  const [p, setP] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr('')
    try { onLogin((await api.login(u, p)).user) } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }
  return (
    <div className="center-page">
      <form className="card login" onSubmit={submit}>
        <div className="brand"><span className="logo" aria-hidden>≋</span><div><h1>FloodLink</h1><p>สำหรับเจ้าหน้าที่และทีมกู้ภัย</p></div></div>
        <label>ชื่อผู้ใช้<input value={u} onChange={(e) => setU(e.target.value)} autoComplete="username" autoFocus /></label>
        <label>รหัสผ่าน<input type="password" value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" /></label>
        {err && <div className="error small">{err}</div>}
        <button className="primary" disabled={busy || !u || !p}>{busy ? 'กำลังเข้าสู่ระบบ…' : 'เข้าสู่ระบบ'}</button>
        <p className="muted small">บัญชีสร้างโดยศูนย์ประสาน/ผู้ดูแลระบบ · ผู้ประสบภัยไม่ต้องล็อกอิน</p>
        <button type="button" className="link" onClick={() => go('/')}>← กลับไปหน้าแจ้งเหตุ</button>
      </form>
    </div>
  )
}

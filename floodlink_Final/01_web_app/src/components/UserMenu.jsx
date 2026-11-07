import { useState } from 'react'
import { api } from '../api.js'
import { ROLE } from '../labels.js'

// name + role chip in the header: change password, log out
export default function UserMenu({ user, onLogout, children }) {
  const [pw, setPw] = useState(false)
  const [f, setF] = useState({ old: '', new1: '', new2: '' })
  const [msg, setMsg] = useState('')
  const change = async (e) => {
    e.preventDefault()
    if (f.new1 !== f.new2) return setMsg('รหัสใหม่สองช่องไม่ตรงกัน')
    try { await api.changePassword(f.old, f.new1); setMsg('✓ เปลี่ยนรหัสแล้ว'); setF({ old: '', new1: '', new2: '' }) } catch (err) { setMsg(err.message) }
  }
  return (
    <details className="menu user-menu">
      <summary aria-label="บัญชีผู้ใช้"><span className="avatar" aria-hidden>{user.username[0]}</span>
        <span className="who"><b>{user.display_name || user.username}</b><small>{ROLE[user.role]}{user.team ? ` · ${user.team}` : ''}</small></span></summary>
      <div className="menu-pop">
        {children}
        <button className="ghost" onClick={() => setPw((v) => !v)}>🔑 เปลี่ยนรหัสผ่าน</button>
        {pw && (
          <form className="pw-form" onSubmit={change}>
            <input type="password" placeholder="รหัสเดิม" value={f.old} onChange={(e) => setF({ ...f, old: e.target.value })} autoComplete="current-password" />
            <input type="password" placeholder="รหัสใหม่ (8 ตัวขึ้นไป)" value={f.new1} onChange={(e) => setF({ ...f, new1: e.target.value })} autoComplete="new-password" />
            <input type="password" placeholder="ยืนยันรหัสใหม่" value={f.new2} onChange={(e) => setF({ ...f, new2: e.target.value })} autoComplete="new-password" />
            <button className="primary" disabled={!f.old || f.new1.length < 8}>บันทึก</button>
            {msg && <span className="small">{msg}</span>}
          </form>
        )}
        <button className="ghost warn-btn" onClick={onLogout}>⎋ ออกจากระบบ</button>
      </div>
    </details>
  )
}

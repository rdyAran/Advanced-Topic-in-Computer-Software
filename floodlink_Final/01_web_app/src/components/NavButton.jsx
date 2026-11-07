// Opens Google Maps directions (on phones this opens the Maps app).
const ICON = { exact: '🎯', link: '🔗', address: '🏠', area: '⚠️' }
const SHORT = { exact: 'พิกัดแม่น', link: 'ลิงก์ผู้แจ้ง', address: 'ตามที่อยู่', area: 'โดยประมาณ' }

export default function NavButton({ nav, small = false }) {
  if (!nav?.url) return <span className="muted small">ยังไม่มีตำแหน่ง</span>
  return (
    <a className={`nav-btn ${nav.precision} ${small ? 'small' : ''}`} href={nav.url} target="_blank" rel="noopener noreferrer"
      title={nav.label} onClick={(e) => e.stopPropagation()}>
      🧭 นำทาง <span className="prec">{ICON[nav.precision]} {SHORT[nav.precision]}</span>
    </a>
  )
}

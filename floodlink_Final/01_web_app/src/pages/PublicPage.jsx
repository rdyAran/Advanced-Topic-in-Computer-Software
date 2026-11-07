import { useEffect, useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, Tooltip } from 'react-leaflet'
import { api } from '../api.js'
import { PRIORITY, NEEDS, CLOSE_REASON } from '../labels.js'
import { go } from '../App.jsx'

// Public situation page: numbers and a rough map only — no names, phones, addresses or message text.
export default function PublicPage({ user }) {
  const [s, setS] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    const load = () => api.publicSummary().then((d) => { setS(d); setErr('') }).catch((e) => setErr(e.message))
    load(); const i = setInterval(load, 30000); return () => clearInterval(i)
  }, [])
  const topNeeds = (n) => Object.entries(n).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([k, v]) => `${NEEDS[k] || k} ${v}`).join(' · ')
  return (
    <div className="public-shell">
      <header className="topbar slim">
        <button className="brand as-link" onClick={() => go('/')} aria-label="กลับหน้าแรก"><span className="logo" aria-hidden>≋</span><div><h1>FloodLink</h1><p>สถานการณ์น้ำท่วม · ภาพรวม</p></div></button>
        <span className="spacer" />
        <button className="ghost" onClick={() => go('/')}>📝 แจ้งเหตุ</button>
        {user && <button className="ghost" onClick={() => go('/staff')}>🧑‍🚒 หน้าเจ้าหน้าที่</button>}
      </header>
      <main className="public-main wide">
        {err && <div className="error">โหลดไม่ได้: {err}</div>}
        {s && (
          <>
            <div className="tiles">
              <div className="tile"><b>{s.open_cases}</b><span>เคสที่ยังรอความช่วยเหลือ</span></div>
              {Object.keys(PRIORITY).map((k) => (
                <div className="tile" key={k}><b style={{ color: PRIORITY[k].color }}>{s.open_by_priority[k] || 0}</b><span>{PRIORITY[k].label}</span></div>
              ))}
              <div className="tile"><b>{s.resolved_cases}</b><span>ปิดเคสแล้ว</span></div>
            </div>
            <p className="muted small">อัปเดต {new Date(s.updated_at).toLocaleTimeString('th-TH')} · ปิดเคส: {Object.entries(s.closed_by_reason).filter(([, v]) => v).map(([k, v]) => `${CLOSE_REASON[k]} ${v}`).join(' · ') || '—'}</p>
            <div className="public-grid">
              <div className="card pub-map">
                <MapContainer center={[7.005, 100.47]} zoom={12} style={{ height: '100%', minHeight: 320 }} scrollWheelZoom={false}>
                  <TileLayer attribution="&copy; OpenStreetMap" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                  {s.points.map((p, i) => (
                    <CircleMarker key={i} center={[p.lat, p.lng]} radius={8 + Math.min(p.count, 20) * 1.5}
                      pathOptions={{ color: PRIORITY[p.worst]?.color, fillOpacity: 0.35 }}>
                      <Tooltip>{p.count} เคสในบริเวณนี้ (~1 กม.)</Tooltip>
                    </CircleMarker>
                  ))}
                </MapContainer>
                <p className="muted small">วงกลม = จำนวนเคสในรัศมีประมาณ 1 กม. (ไม่แสดงตำแหน่งบ้านจริง)</p>
              </div>
              <div className="card">
                <h2>รายพื้นที่</h2>
                <table className="area-table">
                  <thead><tr><th>พื้นที่</th><th>รอช่วย</th><th>แดง</th><th>ต้องการมากที่สุด</th></tr></thead>
                  <tbody>
                    {s.areas.map((a) => (
                      <tr key={a.area}><td>{a.area}</td><td>{a.open}</td><td style={{ color: a.red ? PRIORITY.red.color : undefined }}>{a.red}</td>
                        <td className="small">{topNeeds(a.needs) || '—'}</td></tr>
                    ))}
                    {s.areas.length === 0 && <tr><td colSpan={4} className="muted">ยังไม่มีเคสที่เปิดอยู่</td></tr>}
                  </tbody>
                </table>
                <p className="muted small">อยากช่วยบริจาค? ถามผู้ช่วยในหน้าแจ้งเหตุว่า “ควรเอาของไปบริจาคที่ไหน”</p>
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  )
}

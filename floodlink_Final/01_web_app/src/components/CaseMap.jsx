import { useEffect } from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup, Tooltip, useMap } from 'react-leaflet'
import { PRIORITY, STATUS, FLAGS } from '../labels.js'
import NavButton from './NavButton.jsx'

const HAT_YAI = [7.005, 100.47]

// Cases are geocoded to area centroids for now, so spread markers slightly (stable per case id).
function jitter(id, lat, lng) {
  let h = 0
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  const a = (h % 360) * (Math.PI / 180)
  const r = 0.0015 + ((h >> 9) % 100) / 100 * 0.003
  return [lat + Math.sin(a) * r, lng + Math.cos(a) * r]
}

const PLACE_STYLE = {
  donation_hub: { icon: '📦', color: '#1a73e8', label: 'จุดรับของบริจาค' },
  kitchen: { icon: '🍲', color: '#7b1fa2', label: 'ครัวกลาง' },
  shelter: { icon: '🏠', color: '#00897b', label: 'ศูนย์พักพิง' },
  distribution: { icon: '🍱', color: '#5d4037', label: 'จุดแจกของ' },
  medical: { icon: '🩺', color: '#c2185b', label: 'หน่วยปฐมพยาบาล' },
}

// fly to whatever the chatbot / URL asked to show
function Focus({ target }) {
  const map = useMap()
  useEffect(() => { if (target?.lat) map.flyTo([target.lat, target.lng], 16, { duration: 0.8 }) }, [target?.key])
  return null
}

// a hidden map (phone tab not shown) has size 0 — re-measure when it becomes visible
function Resize({ visible }) {
  const map = useMap()
  useEffect(() => { if (visible) setTimeout(() => map.invalidateSize?.(), 60) }, [visible])
  return null
}

export default function CaseMap({ cases, hazards, places = [], selected, setSelected, focus, visible = true }) {
  return (
    <div className="card map-card">
      <MapContainer center={HAT_YAI} zoom={13} className="map" scrollWheelZoom>
        <TileLayer attribution='&copy; OpenStreetMap contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        <Focus target={focus} />
        <Resize visible={visible} />
        {places.filter((p) => p.lat).map((p) => {
          const st = PLACE_STYLE[p.type] || PLACE_STYLE.donation_hub
          const on = focus?.place === p.id
          return (
            <CircleMarker key={p.id} center={[p.lat, p.lng]} radius={on ? 13 : 10}
              pathOptions={{ color: on ? '#000' : st.color, weight: 3, fillColor: '#fff', fillOpacity: 0.95 }}>
              <Tooltip permanent={on} direction="top">{st.icon} {p.name}</Tooltip>
              <Popup>
                <b>{st.icon} {p.name}</b><br />{st.label}{p.is_demo ? ' (ข้อมูลตัวอย่าง)' : ''}<br />
                {p.address}<br />{p.hours && <>🕘 {p.hours}<br /></>}
                {p.accepts?.length > 0 && <>รับ: {p.accepts.join(', ')}<br /></>}
                {p.short_of?.length > 0 && <b>ขาด: {p.short_of.join(', ')}<br /></b>}
                {p.contact && <>☎ {p.contact}<br /></>}
                <NavButton nav={{ url: p.nav_url, precision: 'exact', label: 'นำทาง' }} />
              </Popup>
            </CircleMarker>
          )
        })}
        {hazards.filter((h) => h.lat).map((h) => (
          <CircleMarker key={h.id} center={jitter(h.id, h.lat, h.lng)} radius={9}
            pathOptions={{ color: '#111', weight: 2, dashArray: '3 3', fillColor: '#ffd400', fillOpacity: 0.9 }}>
            <Popup><b>⚠️ จุดอันตราย</b><br />{h.text}</Popup>
          </CircleMarker>
        ))}
        {cases.filter((c) => c.lat).map((c) => {
          const p = PRIORITY[c.priority] || PRIORITY.green
          const done = c.status === 'resolved'
          return (
            <CircleMarker key={c.id} center={c.geo_precision === 'exact' ? [c.lat, c.lng] : jitter(c.id, c.lat, c.lng)} radius={selected === c.id ? 12 : 8}
              eventHandlers={{ click: () => setSelected(c.id) }}
              pathOptions={{ color: selected === c.id ? '#000' : '#fff', weight: 2, fillColor: done ? '#9aa0a6' : p.color, fillOpacity: done ? 0.5 : 0.95 }}>
              <Tooltip>{c.id} · {p.label}</Tooltip>
              <Popup>
                <b>{c.id}</b> · {p.label}<br />
                {c.summary}<br />
                {c.flags.map((f) => FLAGS[f]).join(', ')}<br />
                สถานะ: {STATUS[c.status]} {c.assigned_team ? `· ทีม ${c.assigned_team}` : ''}<br />
                {c.contact && <>☎ <a href={`tel:${c.contact.replace(/[^\d]/g, '')}`}>{c.contact}</a><br /></>}
                <NavButton nav={c.nav} />
              </Popup>
            </CircleMarker>
          )
        })}
      </MapContainer>
      <details className="legend" open={!window.matchMedia?.('(max-width: 899px)').matches}>
        <summary>สัญลักษณ์บนแผนที่</summary>
        <div className="legend-items">
        {Object.values(PRIORITY).map((p) => <span key={p.label}><i style={{ background: p.color }} />{p.label}</span>)}
        <span><i className="hz" />จุดอันตราย</span>
        <span>📦🍲🏠🍱🩺 จุดบริการ</span>
        <span className="muted">จุดที่ไม่มีพิกัดจากผู้แจ้ง = ตำแหน่งประมาณระดับพื้นที่</span>
        </div>
      </details>
    </div>
  )
}

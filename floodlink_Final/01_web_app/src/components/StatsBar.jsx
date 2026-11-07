import { PRIORITY } from '../labels.js'

// header numbers; each one is a shortcut that filters the queue (onPick)
export default function StatsBar({ stats, extra = null, onPick }) {
  if (!stats) return <div className="stats" />
  const p = stats.open_by_priority || {}
  const Stat = ({ k, children, className = '', title }) => (
    <button type="button" className={`stat ${className}`} onClick={() => onPick?.(k)} title={title || 'กดเพื่อกรองคิวเคส'}>{children}</button>
  )
  return (
    <div className="stats">
      <Stat k="open"><b>{stats.open_cases}</b><span>เคสเปิด</span></Stat>
      {Object.keys(PRIORITY).map((k) => (
        <Stat k={k} key={k}><b style={{ color: PRIORITY[k].color }}>{p[k] || 0}</b><span>{PRIORITY[k].label.split(' · ')[0]}</span></Stat>
      ))}
      <Stat k="unassigned_red" className={stats.unassigned_red ? 'alert' : ''}><b>{stats.unassigned_red}</b><span>แดงยังไม่มีชุด</span></Stat>
      {extra}
      <div className="stat"><b>{stats.duplicates_merged}</b><span>รวมเคสซ้ำ</span></div>
      {stats.ai?.own_model_share != null && (
        <div className="stat" title={`ส่งต่อ LLM ${stats.ai.escalated_to_llm} ข้อความ`}>
          <b>{Math.round(stats.ai.own_model_share * 100)}%</b><span>AI เราตัดสินเอง</span>
        </div>
      )}
    </div>
  )
}

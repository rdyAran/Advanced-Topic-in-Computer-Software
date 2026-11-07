// Case queue filtering / sorting for the coordination centre (pure functions — no React).
export const OPEN = ['new', 'verified', 'assigned', 'in_progress']
export const LATE_MIN = 10

// "what needs a human now": new and not checked yet, red without a team, or a team that has not answered
export const needsAction = (c) => OPEN.includes(c.status) &&
  (c.status === 'new' || (c.priority === 'red' && !c.assigned_team) || (c.waiting_accept_min ?? -1) >= LATE_MIN)

export const STATUS_TABS = [
  ['todo', '⚠️ ต้องจัดการ', needsAction],
  ['new', 'ใหม่ · รอตรวจ', (c) => c.status === 'new'],
  ['verified', 'ตรวจแล้ว · รอชุด', (c) => c.status === 'verified'],
  ['assigned', 'มอบหมายแล้ว', (c) => c.status === 'assigned'],
  ['in_progress', 'กำลังช่วย', (c) => c.status === 'in_progress'],
  ['open', 'เปิดทั้งหมด', (c) => OPEN.includes(c.status)],
  ['resolved', 'ปิดแล้ว', (c) => c.status === 'resolved'],
  ['all', 'ทั้งหมด', () => true],
]
const TAB = Object.fromEntries(STATUS_TABS.map(([k, , f]) => [k, f]))

export const DEFAULT_FILTERS = { status: 'todo', colors: [], team: '', area: '', q: '', sort: 'urgent' }
export const SORTS = { urgent: 'ด่วนที่สุดก่อน', oldest: 'รอนานที่สุดก่อน', newest: 'ใหม่ล่าสุดก่อน', updated: 'อัปเดตล่าสุด' }
const RANK = { red: 0, orange: 1, yellow: 2, green: 3 }

const norm = (s) => String(s || '').toLowerCase().replace(/[\s-]/g, '')
export function matches(c, f) {
  if (f.colors.length && !f.colors.includes(c.priority)) return false
  if (f.team === '__none' && c.assigned_team) return false
  if (f.team && f.team !== '__none' && c.assigned_team !== f.team) return false
  if (f.area && (c.area || 'ไม่ระบุพื้นที่') !== f.area) return false
  if (f.q) {
    const q = norm(f.q)
    const hay = norm([c.id, c.summary, c.area, c.street, c.house_no, c.landmark, c.contact, c.first_text, c.assigned_team].join(' '))
    if (!hay.includes(q)) return false
  }
  return true
}

export function sortCases(rows, sort) {
  const by = {
    urgent: (a, b) => (RANK[a.priority] ?? 9) - (RANK[b.priority] ?? 9) || (b.waiting_accept_min ?? -1) - (a.waiting_accept_min ?? -1) || a.created_at.localeCompare(b.created_at),
    oldest: (a, b) => a.created_at.localeCompare(b.created_at),
    newest: (a, b) => b.created_at.localeCompare(a.created_at),
    updated: (a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''),
  }[sort] || (() => 0)
  return [...rows].sort((a, b) => (a.status === 'resolved') - (b.status === 'resolved') || by(a, b))
}

// -> { rows, counts: {tab: n}, colorCounts, areas, teams } ; counts ignore the status tab, colours ignore the colour filter
export function applyFilters(cases, f) {
  const base = cases.filter((c) => matches(c, { ...f, colors: f.colors }))
  const counts = Object.fromEntries(STATUS_TABS.map(([k, , fn]) => [k, base.filter(fn).length]))
  const inTab = cases.filter(TAB[f.status] || TAB.open)
  const colorCounts = Object.fromEntries(Object.keys(RANK).map((k) => [k, inTab.filter((c) => c.priority === k && matches(c, { ...f, colors: [] })).length]))
  const rows = sortCases(base.filter(TAB[f.status] || TAB.open), f.sort)
  const areas = [...new Set(cases.map((c) => c.area || 'ไม่ระบุพื้นที่'))].sort()
  const teams = [...new Set(cases.map((c) => c.assigned_team).filter(Boolean))].sort()
  return { rows, counts, colorCounts, areas, teams }
}

export const isFiltered = (f) => f.colors.length || f.team || f.area || f.q

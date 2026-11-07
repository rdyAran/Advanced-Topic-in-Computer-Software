// All calls go to the same origin (Vite proxies /api), so the HttpOnly session cookie is sent automatically.
export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status }
}
const j = async (res) => {
  if (!res.ok) {
    let msg = await res.text()
    try { msg = JSON.parse(msg).detail || msg } catch { /* plain text */ }
    if (res.status === 401) window.dispatchEvent(new Event('fl:unauthorized'))
    throw new ApiError(res.status, typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return res.json()
}
const json = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
const get = (url) => fetch(url).then(j)
const send = (method, url, body) => fetch(url, json(method, body ?? {})).then(j)

export const api = {
  // auth
  me: () => get('/api/auth/me'),
  login: (username, password) => send('POST', '/api/auth/login', { username, password }),
  logout: () => send('POST', '/api/auth/logout'),
  changePassword: (old_password, new_password) => send('POST', '/api/auth/password', { old_password, new_password }),

  // public
  health: () => get('/api/health'),
  guide: () => get('/api/intake-guide'),
  places: () => get('/api/places'),
  chat: (message, session_id, lat, lng) => send('POST', '/api/chat', { message, session_id, lat, lng }),
  sendMessage: (text, channel = 'web_form', photos = [], no_training = false) => send('POST', '/api/messages', { text, channel, photos, no_training }),
  publicSummary: () => get('/api/public/summary'),
  track: (token) => get(`/api/track/${encodeURIComponent(token)}`),
  trackFollowup: (token, case_id, text, photos = []) => send('POST', `/api/track/${encodeURIComponent(token)}/followup`, { case_id, text, photos }),
  trackSafe: (token, case_id) => send('POST', `/api/track/${encodeURIComponent(token)}/safe`, { case_id }),

  // staff
  cases: (status) => get(`/api/cases${status ? `?status=${status}` : ''}`),
  hazards: () => get('/api/hazards'),
  stats: () => get('/api/stats'),
  teams: () => get('/api/teams'),
  caseDetail: (id) => get(`/api/cases/${id}`),
  timeline: (id) => get(`/api/cases/${id}/timeline`),
  aiFeedback: (id, body) => send('POST', `/api/cases/${id}/ai-feedback`, body),
  followup: (id, text, photos = []) => send('POST', `/api/cases/${id}/followup`, { text, photos }),
  note: (id, text, photos = []) => send('POST', `/api/cases/${id}/note`, { text, photos }),
  updateCase: (id, patch) => send('PATCH', `/api/cases/${id}`, patch),
  correctAi: (id, patch) => send('PATCH', `/api/cases/${id}/ai`, patch),
  mergeInto: (id, target) => send('POST', `/api/cases/${id}/merge-into`, { target }),
  notDuplicate: (id) => send('POST', `/api/cases/${id}/not-duplicate`),

  // field teams (one team-lead account per team)
  teamBoard: () => get('/api/team-board'),
  suggestTeams: (id) => get(`/api/cases/${id}/suggest-teams`),
  teamAccounts: () => get('/api/team-accounts'),
  createTeamAccount: (body) => send('POST', '/api/team-accounts', body),
  updateTeamAccount: (id, patch) => send('PATCH', `/api/team-accounts/${id}`, patch),
  updateTeam: (name, patch) => send('PATCH', `/api/teams/${encodeURIComponent(name)}`, patch),
  myTeam: () => get('/api/my-team'),
  updateMyTeam: (patch) => send('PATCH', '/api/my-team', patch),
  nearby: (lat, lng) => get(`/api/nearby${lat != null ? `?lat=${lat}&lng=${lng}` : ''}`),
  claim: (id) => send('POST', `/api/cases/${id}/claim`),
  accept: (id) => send('POST', `/api/cases/${id}/accept`),
  decline: (id, reason) => send('POST', `/api/cases/${id}/decline`, { reason }),

  // admin
  users: () => get('/api/admin/users'),
  createUser: (u) => send('POST', '/api/admin/users', u),
  updateUser: (id, patch) => send('PATCH', `/api/admin/users/${id}`, patch),
  audit: (limit = 300) => get(`/api/admin/audit?limit=${limit}`),
  system: () => get('/api/admin/system'),
  exportCorrectionsUrl: '/api/admin/export/corrections.jsonl',
  seed: (limit = 40) => send('POST', `/api/demo/seed?limit=${limit}`),
  deleteDemo: () => fetch('/api/demo', { method: 'DELETE' }).then(j),
  resetAll: () => send('POST', '/api/admin/reset?confirm=DELETE-ALL'),
}

export const trackUrl = (token) => `${window.location.origin}/track/${token}`

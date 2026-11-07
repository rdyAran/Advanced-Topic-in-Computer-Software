import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import ReporterHome from './pages/ReporterHome.jsx'
import TrackPage from './pages/TrackPage.jsx'
import PublicPage from './pages/PublicPage.jsx'
import LoginPage from './pages/LoginPage.jsx'
import RescuerApp from './pages/RescuerApp.jsx'
import StaffApp from './StaffApp.jsx'

// Very small router: /track/<token>  /public  /login  /staff  /  (no extra library)
export const go = (path) => { window.history.pushState({}, '', path); window.dispatchEvent(new Event('popstate')) }

export default function App() {
  const [path, setPath] = useState(window.location.pathname)
  const [user, setUser] = useState(undefined)          // undefined = still checking, null = not logged in
  useEffect(() => {
    const on = () => setPath(window.location.pathname)
    window.addEventListener('popstate', on); return () => window.removeEventListener('popstate', on)
  }, [])
  const loadMe = useCallback(() => api.me().then((r) => setUser(r.user)).catch(() => setUser(null)), [])
  useEffect(() => { loadMe() }, [loadMe])
  useEffect(() => {                                  // session expired / password changed elsewhere
    const on = () => setUser(null)
    window.addEventListener('fl:unauthorized', on); return () => window.removeEventListener('fl:unauthorized', on)
  }, [])
  const logout = async () => { await api.logout().catch(() => {}); setUser(null); go('/') }

  const track = path.match(/^\/track\/([\w-]{16,})/)
  if (track) return <TrackPage token={track[1]} />
  if (path.startsWith('/public')) return <PublicPage user={user} />
  if (user === undefined) return <div className="boot">FloodLink กำลังโหลด…</div>
  const staffWanted = path.startsWith('/staff') || path.startsWith('/login') || new URLSearchParams(window.location.search).has('case')
  if (!user) {
    return staffWanted
      ? <LoginPage onLogin={(u) => { setUser(u); go('/staff' + window.location.search) }} />
      : <ReporterHome />
  }
  if (!staffWanted && path === '/') return <ReporterHome user={user} />
  if (user.role === 'rescuer') return <RescuerApp user={user} onLogout={logout} />
  return <StaffApp user={user} onLogout={logout} />
}

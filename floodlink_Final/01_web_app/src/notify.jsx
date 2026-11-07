// In-app toast + (if the person allowed it) a system notification + a short beep. Used for
// "new case assigned to your team", "new red case", and the reporter's "status changed".
import { useCallback, useEffect, useRef, useState } from 'react'

export function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)()
    const o = ctx.createOscillator(), g = ctx.createGain()
    o.frequency.value = 880; g.gain.value = 0.08; o.connect(g); g.connect(ctx.destination)
    o.start(); o.stop(ctx.currentTime + 0.25)
  } catch { /* no audio */ }
}

export const canNotify = () => 'Notification' in window
export const notifyOn = () => canNotify() && Notification.permission === 'granted'
export const askNotify = () => (canNotify() ? Notification.requestPermission() : Promise.resolve('denied'))

export function useToasts() {
  const [toasts, setToasts] = useState([])
  // actions = [{label, onClick}] -> buttons in the toast (e.g. one per case id: jump to that case)
  const push = useCallback((text, kind = 'info', { sound = false, system = false, actions = [], ms = 12000 } = {}) => {
    const id = Math.random().toString(36).slice(2)
    setToasts((t) => [...t.slice(-3), { id, text, kind, actions }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), ms)
    if (sound) beep()
    if (system && notifyOn() && document.visibilityState !== 'visible') {
      try { new Notification('FloodLink', { body: text }) } catch { /* some phones need a service worker */ }
    }
  }, [])
  const view = (
    <div className="toasts" role="status" aria-live="polite">
      {toasts.map((t) => {
        const close = () => setToasts((x) => x.filter((y) => y.id !== t.id))
        const one = t.actions.length === 1
        return (
          <div key={t.id} className={`toast ${t.kind} ${t.actions.length ? 'has-actions' : ''}`} role={one ? 'button' : undefined}
            onClick={() => { if (one) t.actions[0].onClick(); close() }}>
            <div className="toast-text">{t.text}</div>
            {t.actions.length > 0 && (
              <div className="toast-actions">
                {t.actions.map((a) => <button key={a.label} onClick={(e) => { e.stopPropagation(); a.onClick(); close() }}>{a.label}</button>)}
              </div>
            )}
            <button className="toast-x" aria-label="ปิด" onClick={(e) => { e.stopPropagation(); close() }}>✕</button>
          </div>
        )
      })}
    </div>
  )
  return [push, view]
}

// remembers the previous value of a list so we can tell what is new since the last poll.
// items = null while not loaded yet; the first loaded list and every list after resetKey changes are taken as the baseline.
export function useNewItems(items, resetKey = '', key = (x) => x.id) {
  const prev = useRef(null)
  const lastKey = useRef(resetKey)
  const [fresh, setFresh] = useState([])
  useEffect(() => {
    if (lastKey.current !== resetKey) { prev.current = null; lastKey.current = resetKey }
    if (!items) return
    const ids = new Set(items.map(key))
    if (prev.current) setFresh(items.filter((x) => !prev.current.has(key(x))))
    prev.current = ids
  }, [items, resetKey]) // eslint-disable-line react-hooks/exhaustive-deps
  return fresh
}

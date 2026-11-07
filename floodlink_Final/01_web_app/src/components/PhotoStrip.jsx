import { useEffect, useState } from 'react'

// Thumbnails of the photos attached to a report; tap = full screen (Esc / tap again to close).
export default function PhotoStrip({ photos, size = 'md' }) {
  const [open, setOpen] = useState(null)
  useEffect(() => {
    if (open == null) return
    const k = (e) => { if (e.key === 'Escape') setOpen(null); if (e.key === 'ArrowRight') setOpen((i) => (i + 1) % photos.length) }
    window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k)
  }, [open, photos.length])
  if (!photos?.length) return null
  return (
    <div className={`photo-strip ${size}`} onClick={(e) => e.stopPropagation()}>
      {photos.map((p, i) => (
        <button type="button" key={p.id || i} className="thumb" onClick={() => setOpen(i)} aria-label={`ดูรูปที่ ${i + 1}`}>
          <img src={p.url || p.dataUrl} alt={`รูปแนบ ${i + 1}`} loading="lazy" />
        </button>
      ))}
      {open != null && (
        <div className="lightbox" role="dialog" aria-label="รูปแนบ" onClick={() => setOpen(null)}>
          <img src={photos[open].url || photos[open].dataUrl} alt={`รูปแนบ ${open + 1}`} />
          <div className="lightbox-bar">
            <span>รูป {open + 1}/{photos.length}</span>
            {photos[open].url && <a href={photos[open].url} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}>เปิดไฟล์เต็ม</a>}
            <button type="button" className="ghost" onClick={() => setOpen(null)}>✕ ปิด</button>
          </div>
        </div>
      )}
    </div>
  )
}

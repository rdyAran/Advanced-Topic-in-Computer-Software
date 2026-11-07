// Shrink a phone photo in the browser before upload: longest side 1600 px, JPEG ~0.8.
// A 4-8 MB camera photo becomes ~200-400 KB, which matters on a weak mobile signal during a flood.
// Re-drawing on a canvas also drops EXIF metadata (GPS, phone model) — the reporter's location is sent
// only when they press "แนบตำแหน่งปัจจุบัน".
export const MAX_PHOTOS = 4
const MAX_SIDE = 1600

const loadImage = async (file) => {
  if ('createImageBitmap' in window) {
    try { return await createImageBitmap(file, { imageOrientation: 'from-image' }) } catch { /* fall back below */ }
  }
  return await new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => { URL.revokeObjectURL(url); resolve(img) }
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('เปิดรูปนี้ไม่ได้')) }
    img.src = url
  })
}

export async function shrinkPhoto(file) {
  if (!file.type.startsWith('image/')) throw new Error(`${file.name} ไม่ใช่รูปภาพ`)
  const img = await loadImage(file)
  const w = img.width, h = img.height
  const k = Math.min(1, MAX_SIDE / Math.max(w, h))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(w * k); canvas.height = Math.round(h * k)
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height)       // PNG with transparency -> white
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
  img.close?.()
  const dataUrl = canvas.toDataURL('image/jpeg', 0.8)
  return { name: file.name, dataUrl, kb: Math.round((dataUrl.length * 3) / 4 / 1024) }
}

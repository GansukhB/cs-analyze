// VIZ-8: a coach's marks from the Replay (arrows, circles, words, in world
// units) on the Map's radar, small enough to sit beside a Briefing's lines.
import { useEffect, useRef, useState } from 'react'
import { $api } from '../api/client'
import type { Shape } from '../replay/player'

const INK = '#f2c94c'
const PX = 512

export default function DrawingThumb({ map, shapes, label }: { map: string; shapes: Shape[]; label: string }) {
  const plate = $api.useQuery('get', '/strats/plate/{map_name}', { params: { path: { map_name: map } } }, { staleTime: Infinity })
  const p = plate.data?.plate as { url: string | null; extent: [number, number, number, number] } | null | undefined
  const canvas = useRef<HTMLCanvasElement>(null)
  const [image, setImage] = useState<HTMLImageElement | null>(null)

  useEffect(() => {
    if (!p?.url) return
    const img = new Image()
    img.onload = () => setImage(img)
    img.src = p.url
  }, [p?.url])

  useEffect(() => {
    const g = canvas.current?.getContext('2d')
    if (!g || !p) return
    const [x0, x1, y0, y1] = p.extent
    const px = (x: number) => ((x - x0) / (x1 - x0)) * PX
    const py = (y: number) => (1 - (y - y0) / (y1 - y0)) * PX
    g.fillStyle = '#0d1116'
    g.fillRect(0, 0, PX, PX)
    if (image) {
      g.globalAlpha = 0.75
      g.drawImage(image, 0, 0, PX, PX)
      g.globalAlpha = 1
    }
    g.strokeStyle = INK
    g.fillStyle = INK
    g.lineWidth = 4
    g.lineCap = 'round'
    for (const s of shapes) {
      const [a, b] = s.points
      const [ax, ay] = [px(a[0]), py(a[1])]
      if (s.kind === 'arrow' && b) {
        const [bx, by] = [px(b[0]), py(b[1])]
        g.beginPath()
        g.moveTo(ax, ay)
        g.lineTo(bx, by)
        g.stroke()
        const angle = Math.atan2(by - ay, bx - ax)
        g.beginPath()
        g.moveTo(bx, by)
        g.lineTo(bx - 16 * Math.cos(angle - 0.45), by - 16 * Math.sin(angle - 0.45))
        g.lineTo(bx - 16 * Math.cos(angle + 0.45), by - 16 * Math.sin(angle + 0.45))
        g.closePath()
        g.fill()
      } else if (s.kind === 'circle' && b) {
        g.beginPath()
        g.arc(ax, ay, Math.hypot(px(b[0]) - ax, py(b[1]) - ay), 0, Math.PI * 2)
        g.stroke()
      } else if (s.kind === 'text' && s.text) {
        g.font = 'bold 20px ui-sans-serif, system-ui, sans-serif'
        g.textAlign = 'center'
        g.lineWidth = 5
        g.strokeStyle = '#0d1116'
        g.strokeText(s.text, ax, ay)
        g.fillText(s.text, ax, ay)
        g.strokeStyle = INK
        g.lineWidth = 4
      }
    }
  }, [p, image, shapes])

  return (
    <canvas
      ref={canvas}
      width={PX}
      height={PX}
      role="img"
      aria-label={label}
      className="aspect-square w-full max-w-[280px] rounded-lg border border-line bg-ground"
    />
  )
}

// SB-8: a Strat's board, drawn on the Map's radar: where each of our five
// stands, where the smokes, molotovs and flashes go, and the moves as arrows.
// Kept with the Strat in world units, so it lines up with the Replay's.
import { useEffect, useRef, useState } from 'react'
import { $api } from '../api/client'
import type { components } from '../api/schema'

type Shape = components['schemas']['BoardShape']
type Kind = Shape['kind']

// One look per kind; the Sides keep their colours, the grenades their own.
const LOOK: Record<Kind, { label: string; colour: string }> = {
  ct: { label: 'CT', colour: '#5b9bd8' },
  t: { label: 'T', colour: '#d39a55' },
  smoke: { label: 'Smoke', colour: '#c8d2dc' },
  molotov: { label: 'Molotov', colour: '#e0854a' },
  flash: { label: 'Flash', colour: '#e8e0a0' },
  arrow: { label: '➚ Сум', colour: '#f2c94c' },
  text: { label: 'T Текст', colour: '#f2c94c' },
}
// World radii of a smoke's and a molotov's cloud.
const RADIUS: Partial<Record<Kind, number>> = { smoke: 144, molotov: 110 }

export default function Board(props: { stratId: number; map: string; shapes: Shape[]; canEdit: boolean; onSaved?: () => void }) {
  const plate = $api.useQuery('get', '/strats/plate/{map_name}', { params: { path: { map_name: props.map } } }, { staleTime: Infinity })
  const [shapes, setShapes] = useState<Shape[]>(props.shapes)
  const [tool, setTool] = useState<Kind | null>(null)
  const [word, setWord] = useState('')
  const [drag, setDrag] = useState<Shape | null>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const image = useRef<HTMLImageElement | null>(null)
  const [loaded, setLoaded] = useState(0)
  const save = $api.useMutation('put', '/strats/{strat_id}/board', { onSuccess: () => props.onSaved?.() })
  const p = plate.data?.plate as { url: string | null; extent: [number, number, number, number] } | null | undefined

  useEffect(() => {
    if (!p?.url) return
    const img = new Image()
    img.onload = () => setLoaded((n) => n + 1)
    img.src = p.url
    image.current = img
  }, [p?.url])

  useEffect(() => {
    const c = canvas.current
    if (!c || !p) return
    const g = c.getContext('2d')!
    const W = c.width
    const H = c.height
    const [x0, x1, y0, y1] = p.extent
    const px = (x: number) => ((x - x0) / (x1 - x0)) * W
    const py = (y: number) => (1 - (y - y0) / (y1 - y0)) * H
    const scale = W / (x1 - x0)
    g.fillStyle = '#0d1116'
    g.fillRect(0, 0, W, H)
    if (image.current?.complete && image.current.naturalWidth) {
      g.globalAlpha = 0.7
      g.drawImage(image.current, 0, 0, W, H)
      g.globalAlpha = 1
    }
    g.font = '11px ui-sans-serif, system-ui, sans-serif'
    g.textAlign = 'center'
    g.fillStyle = 'rgba(227, 232, 237, 0.55)'
    for (const l of (plate.data?.labels ?? []) as { name: string; x: number; y: number }[]) g.fillText(l.name, px(l.x), py(l.y))
    const count: Record<string, number> = {}
    for (const s of drag ? [...shapes, drag] : shapes) {
      const look = LOOK[s.kind]
      const [a, b] = s.points
      g.save()
      g.strokeStyle = look.colour
      g.fillStyle = look.colour
      if (s.kind === 'ct' || s.kind === 't') {
        count[s.kind] = (count[s.kind] ?? 0) + 1
        g.beginPath()
        g.arc(px(a[0]), py(a[1]), 9, 0, Math.PI * 2)
        g.fill()
        g.fillStyle = '#0d1116'
        g.font = 'bold 11px ui-sans-serif, system-ui, sans-serif'
        g.textBaseline = 'middle'
        g.fillText(String(count[s.kind]), px(a[0]), py(a[1]) + 0.5)
      } else if (s.kind === 'smoke' || s.kind === 'molotov') {
        g.globalAlpha = 0.45
        g.beginPath()
        g.arc(px(a[0]), py(a[1]), (RADIUS[s.kind] ?? 120) * scale, 0, Math.PI * 2)
        g.fill()
      } else if (s.kind === 'flash') {
        g.beginPath()
        g.arc(px(a[0]), py(a[1]), 6, 0, Math.PI * 2)
        g.fill()
        g.globalAlpha = 0.5
        g.lineWidth = 2
        g.beginPath()
        g.arc(px(a[0]), py(a[1]), 14, 0, Math.PI * 2)
        g.stroke()
      } else if (s.kind === 'arrow' && b) {
        const [ax, ay, bx, by] = [px(a[0]), py(a[1]), px(b[0]), py(b[1])]
        g.lineWidth = 3
        g.lineCap = 'round'
        g.beginPath()
        g.moveTo(ax, ay)
        g.lineTo(bx, by)
        g.stroke()
        const angle = Math.atan2(by - ay, bx - ax)
        g.beginPath()
        g.moveTo(bx, by)
        g.lineTo(bx - 13 * Math.cos(angle - 0.45), by - 13 * Math.sin(angle - 0.45))
        g.lineTo(bx - 13 * Math.cos(angle + 0.45), by - 13 * Math.sin(angle + 0.45))
        g.closePath()
        g.fill()
      } else if (s.kind === 'text' && s.text) {
        g.font = 'bold 15px ui-sans-serif, system-ui, sans-serif'
        g.lineWidth = 4
        g.strokeStyle = '#0d1116'
        g.strokeText(s.text, px(a[0]), py(a[1]))
        g.fillText(s.text, px(a[0]), py(a[1]))
      }
      g.restore()
    }
  }, [shapes, drag, p, plate.data, loaded])

  const world = (e: React.PointerEvent<HTMLCanvasElement>): [number, number] => {
    const r = e.currentTarget.getBoundingClientRect()
    const [x0, x1, y0, y1] = p!.extent
    return [x0 + ((e.clientX - r.left) / r.width) * (x1 - x0), y0 + (1 - (e.clientY - r.top) / r.height) * (y1 - y0)]
  }
  if (!plate.data) return <p className="text-sm text-ink-3">Самбарыг ачаалж байна…</p>
  if (!p) return <p className="text-sm text-ink-3">Энэ map-д radar зураг алга.</p>
  const dirty = JSON.stringify(shapes) !== JSON.stringify(props.shapes)
  return (
    <div className="space-y-2">
      {props.canEdit && (
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          {(Object.keys(LOOK) as Kind[]).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setTool(tool === k ? null : k)}
              className={`rounded-md border px-2 py-1 ${tool === k ? 'border-ink-3 bg-raised text-ink' : 'border-line text-ink-3 hover:text-ink'}`}
            >
              <span style={{ color: LOOK[k].colour }}>●</span> {LOOK[k].label}
            </button>
          ))}
          {tool === 'text' && (
            <input
              value={word}
              onChange={(e) => setWord(e.target.value)}
              maxLength={60}
              placeholder="бичих үг"
              className="w-28 rounded-md border border-line bg-surface-2 px-2 py-1 text-ink"
            />
          )}
          <button type="button" onClick={() => setShapes(shapes.slice(0, -1))} disabled={!shapes.length} className="text-ink-3 hover:text-ink disabled:opacity-40">
            ↶ буцаах
          </button>
          <button type="button" onClick={() => setShapes([])} disabled={!shapes.length} className="text-ink-3 hover:text-crit disabled:opacity-40">
            цэвэрлэх
          </button>
          <button
            type="button"
            disabled={!dirty || save.isPending}
            onClick={() => save.mutate({ params: { path: { strat_id: props.stratId } }, body: { shapes } })}
            className="rounded-md bg-ct px-3 py-1 font-medium text-ground disabled:opacity-40"
          >
            {save.isPending ? 'Хадгалж байна…' : 'Самбарыг хадгалах'}
          </button>
        </div>
      )}
      <canvas
        ref={canvas}
        width={720}
        height={720}
        className="w-full max-w-[720px] rounded-lg"
        style={{ touchAction: 'none', cursor: tool ? 'crosshair' : 'default' }}
        onPointerDown={(e) => {
          if (!props.canEdit || !tool) return
          const at = world(e)
          if (tool === 'arrow') setDrag({ kind: 'arrow', points: [at, at], text: '' })
          else if (tool === 'text') {
            if (word) setShapes([...shapes, { kind: 'text', points: [at], text: word }])
          }
          else setShapes([...shapes, { kind: tool, points: [at], text: '' }])
        }}
        onPointerMove={(e) => drag && setDrag({ ...drag, points: [drag.points[0], world(e)] })}
        onPointerUp={() => {
          if (drag) setShapes([...shapes, drag])
          setDrag(null)
        }}
      />
    </div>
  )
}

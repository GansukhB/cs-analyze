// Ghost mode (docs/plans/09 VIZ-5): several Rounds played over each other from
// their freeze end, every Player a faint dot with a short trail, so a habit is
// seen moving at once. The Rounds ride in the URL (?r=match.map.round,...), from
// a Playbook line's evidence or a Playlist; one Team or Side can be singled out.
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { $api, fetchClient } from '../api/client'
import type { SceneData } from '../replay/player'

interface GhostPlayer {
  sid: string
  name: string
  team: string
  side: string
  x: (number | null)[]
  y: (number | null)[]
  hp: number[]
}
interface GhostRound {
  key: string
  label: string
  hz: number
  seconds: number
  players: GhostPlayer[]
}

const TRAIL = 3 // seconds
const COLOUR: Record<string, string> = { ct: '#5b9bd8', t: '#d8a24a' }

function parseRefs(raw: string | null) {
  return (raw ?? '')
    .split(',')
    .map((x) => x.split('.').map(Number))
    .filter((p) => p.length === 3 && p.every((n) => Number.isFinite(n) && n > 0))
    .slice(0, 30)
    .map(([match, map, round]) => ({ match, map, round }))
}

export default function GhostPage() {
  const [search, setSearch] = useSearchParams()
  const refs = useMemo(() => parseRefs(search.get('r')), [search])
  const side = search.get('side') ?? ''
  const team = search.get('team') ?? ''
  const first = refs[0]
  const detail = $api.useQuery(
    'get',
    '/matches/{match_id}/maps/{map_number}',
    { params: { path: { match_id: first?.match ?? 0, map_number: first?.map ?? 1 } } },
    { enabled: !!first },
  )
  const [rounds, setRounds] = useState<GhostRound[]>([])
  useEffect(() => {
    let cancelled = false
    void Promise.all(
      refs.map(async (r) => {
        const { data } = await fetchClient.GET('/matches/{match_id}/maps/{map_number}/rounds/{number}', {
          params: { path: { match_id: r.match, map_number: r.map, number: r.round } },
        })
        if (!data) return null
        const d = data as unknown as { hz: number; seconds: number; players: GhostPlayer[] }
        return { key: `${r.match}.${r.map}.${r.round}`, label: `R${r.round}`, hz: d.hz, seconds: d.seconds, players: d.players }
      }),
    ).then((found) => {
      if (!cancelled) setRounds(found.filter((x): x is GhostRound => x !== null))
    })
    return () => {
      cancelled = true
    }
  }, [refs])

  const set = (k: string, v: string) => {
    const next = new URLSearchParams(search)
    if (v) next.set(k, v)
    else next.delete(k)
    setSearch(next, { replace: true })
  }
  const teams = [...new Set(rounds.flatMap((r) => r.players.map((p) => p.team)).filter(Boolean))]
  const scene = detail.data?.scene as unknown as SceneData | undefined
  if (!first) return <p className="text-ink-3">Давхарлах раунд сонгогдоогүй байна.</p>
  return (
    <div className="space-y-3">
      <h1 className="text-2xl font-semibold text-ink">Ghost: {rounds.length} раунд давхар</h1>
      <p className="max-w-3xl text-sm text-ink-2">
        Раунд бүрийг freeze end-ээс эхлүүлж зэрэг тоглуулна. Тоглогч бүр бүдэг цэг, сүүлийн {TRAIL} секундын мөрөөр.{' '}
        {rounds.map((r) => {
          const [match, map, round] = r.key.split('.')
          return (
            <Link key={r.key} to={`/matches/${match}/m/${map}?round=${round}`} className="mr-1 font-mono text-xs text-ct">
              {r.label}
            </Link>
          )
        })}
      </p>
      <div className="flex flex-wrap gap-2 text-sm">
        {(['', 't', 'ct'] as const).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => set('side', s)}
            className={`rounded-md border px-2 py-0.5 ${side === s ? 'border-ink-3 bg-raised text-ink' : 'border-line text-ink-3'}`}
          >
            {s ? s.toUpperCase() : 'Хоёр тал'}
          </button>
        ))}
        <button
          type="button"
          onClick={() => set('team', '')}
          className={`rounded-md border px-2 py-0.5 ${!team ? 'border-ink-3 bg-raised text-ink' : 'border-line text-ink-3'}`}
        >
          Бүх баг
        </button>
        {teams.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => set('team', t)}
            className={`rounded-md border px-2 py-0.5 ${team === t ? 'border-ink-3 bg-raised text-ink' : 'border-line text-ink-3'}`}
          >
            {t}
          </button>
        ))}
      </div>
      {scene && rounds.length > 0 ? (
        <Canvas scene={scene} rounds={rounds} side={side} team={team} />
      ) : (
        <p className="text-ink-3">Уншиж байна…</p>
      )}
    </div>
  )
}

function Canvas(props: { scene: SceneData; rounds: GhostRound[]; side: string; team: string }) {
  const { scene, rounds, side, team } = props
  const ref = useRef<HTMLCanvasElement>(null)
  const [t, setT] = useState(0)
  const [playing, setPlaying] = useState(true)
  const [speed, setSpeed] = useState(1)
  const end = Math.max(...rounds.map((r) => r.seconds))
  const plate = useMemo(() => {
    if (!scene.plate.url) return null
    const img = new Image()
    img.src = scene.plate.url
    return img
  }, [scene])

  useEffect(() => {
    if (!playing) return
    let last = performance.now()
    let frame = 0
    const tick = (now: number) => {
      const dt = (now - last) / 1000
      last = now
      setT((v) => {
        const next = v + dt * speed
        if (next >= end) {
          setPlaying(false)
          return end
        }
        return next
      })
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [playing, speed, end])

  useEffect(() => {
    const canvas = ref.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return
    const W = scene.plate.width
    const H = scene.plate.height
    const EXT = scene.plate.extent
    const px = (x: number) => ((x - EXT[0]) / (EXT[1] - EXT[0])) * W
    const py = (y: number) => (1 - (y - EXT[2]) / (EXT[3] - EXT[2])) * H
    ctx.clearRect(0, 0, W, H)
    ctx.fillStyle = '#0b0d11'
    ctx.fillRect(0, 0, W, H)
    if (plate?.complete && plate.naturalWidth) {
      ctx.globalAlpha = 0.55
      ctx.drawImage(plate, 0, 0, W, H)
      ctx.globalAlpha = 1
    }
    for (const r of rounds) {
      const i = Math.min(Math.floor(t * r.hz), Math.max(0, r.players[0]?.x.length - 1))
      const back = Math.max(0, i - TRAIL * r.hz)
      for (const p of r.players) {
        if ((side && p.side !== side) || (team && p.team !== team)) continue
        if (!p.hp[i]) continue
        const colour = COLOUR[p.side] ?? '#999'
        ctx.strokeStyle = colour
        ctx.globalAlpha = 0.25
        ctx.lineWidth = 2
        ctx.beginPath()
        let moved = false
        for (let k = back; k <= i; k++) {
          const x = p.x[k]
          const y = p.y[k]
          if (x == null || y == null) continue
          if (!moved) ctx.moveTo(px(x), py(y))
          else ctx.lineTo(px(x), py(y))
          moved = true
        }
        ctx.stroke()
        const x = p.x[i]
        const y = p.y[i]
        if (x == null || y == null) continue
        ctx.globalAlpha = 0.65
        ctx.fillStyle = colour
        ctx.beginPath()
        ctx.arc(px(x), py(y), 5, 0, Math.PI * 2)
        ctx.fill()
      }
    }
    ctx.globalAlpha = 1
  }, [t, rounds, side, team, scene, plate])

  const clock = `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`
  return (
    <div className="space-y-2">
      <canvas
        ref={ref}
        width={scene.plate.width}
        height={scene.plate.height}
        className="h-auto w-full max-w-[900px] rounded-xl border border-line"
      />
      <div className="flex max-w-[900px] items-center gap-3 text-sm">
        <button type="button" onClick={() => (t >= end ? (setT(0), setPlaying(true)) : setPlaying(!playing))} className="text-ct">
          {playing ? '❚❚' : '▶'}
        </button>
        <span className="font-mono text-ink-2">{clock}</span>
        <input
          type="range"
          min={0}
          max={end}
          step={0.1}
          value={t}
          onChange={(e) => {
            setPlaying(false)
            setT(Number(e.target.value))
          }}
          className="flex-1"
        />
        {[1, 2, 4].map((v) => (
          <button key={v} type="button" onClick={() => setSpeed(v)} className={speed === v ? 'text-ink' : 'text-ink-3'}>
            {v}×
          </button>
        ))}
      </div>
    </div>
  )
}

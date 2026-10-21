import { useRef, useState } from 'react'
import type { components } from '../api/schema'
import { clock, swingText } from './format'

type Round = components['schemas']['ReviewRound']
type Event = Round['events'][number]

const W = 640
const H = 150
const PAD = { left: 34, right: 10, top: 10, bottom: 20 }
const PLOT_W = W - PAD.left - PAD.right
const PLOT_H = H - PAD.top - PAD.bottom

/**
 * One Round's Win probability: the CT side's chance over the Round's clock, a
 * single line with the CT half washed blue above 50% and the T half amber below.
 * Every kill, plant and defuse sits on the line as a marker; hovering shows the
 * moment, clicking one opens it in the Replay.
 */
export default function WinChart(props: {
  round: Round
  names: Record<string, string>
  ctTeam: string
  tTeam: string
  onGoto: (t: number, sid: string | null) => void
  // The Replay's second on this Round: a cursor follows it, and a click on the
  // chart goes there (VIZ-6).
  now?: number | null
}) {
  const { round, names, ctTeam, tTeam, onGoto, now } = props
  const box = useRef<HTMLDivElement>(null)
  const [hover, setHover] = useState<number | null>(null)
  const end = Math.max(1, round.seconds)
  const x = (t: number) => PAD.left + (Math.min(end, Math.max(0, t)) / end) * PLOT_W
  const y = (p: number) => PAD.top + (1 - p) * PLOT_H
  const mid = y(0.5)

  const line = round.wp.map(([t, p], i) => `${i ? 'L' : 'M'}${x(t).toFixed(1)},${y(p).toFixed(1)}`).join('')
  const area = `${line}L${x(end).toFixed(1)},${mid}L${x(0).toFixed(1)},${mid}Z`
  // The event's position on the line: after it, which is what it caused.
  const pAt = (t: number) => {
    let found = round.wp[0]?.[1] ?? 0.5
    for (const [wt, wp] of round.wp) {
      if (wt <= t + 1e-6) found = wp
      else break
    }
    return found
  }

  const near = hover === null ? null : nearest(round.wp, hover)
  const event = hover === null ? null : nearestEvent(round.events, hover)
  const clipId = `wp-${round.n}`

  function move(e: React.PointerEvent) {
    const rect = box.current?.getBoundingClientRect()
    if (!rect) return
    const px = ((e.clientX - rect.left) / rect.width) * W
    setHover(Math.max(0, Math.min(end, ((px - PAD.left) / PLOT_W) * end)))
  }

  return (
    <div className="relative" ref={box}>
      <div className="mb-1 flex justify-end gap-3 text-[11px] text-ink-3">
        <span>▲ CT · {ctTeam}</span>
        <span>▼ T · {tTeam}</span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="block h-auto w-full"
        role="img"
        aria-label={`Раунд ${round.n}: CT-ийн хожих магадлал раундын туршид`}
        onPointerMove={move}
        onPointerLeave={() => setHover(null)}
        onClick={(e) => {
          // A click on the chart, not on a marker, goes to that second.
          if ((e.target as Element).closest('[role="button"]') || hover === null) return
          onGoto(hover, null)
        }}
      >
        <defs>
          <clipPath id={`${clipId}-ct`}>
            <rect x={PAD.left} y={PAD.top} width={PLOT_W} height={mid - PAD.top} />
          </clipPath>
          <clipPath id={`${clipId}-t`}>
            <rect x={PAD.left} y={mid} width={PLOT_W} height={PAD.top + PLOT_H - mid} />
          </clipPath>
        </defs>
        {/* Recessive frame: the 50% line and the two edges. */}
        {[0, 0.5, 1].map((p) => (
          <line key={p} x1={PAD.left} x2={W - PAD.right} y1={y(p)} y2={y(p)} stroke="var(--line)" strokeWidth={1} />
        ))}
        <text x={PAD.left - 6} y={y(1) + 4} textAnchor="end" className="fill-ink-3 text-[10px]">100</text>
        <text x={PAD.left - 6} y={mid + 4} textAnchor="end" className="fill-ink-3 text-[10px]">50</text>
        <text x={PAD.left - 6} y={y(0) + 4} textAnchor="end" className="fill-ink-3 text-[10px]">0</text>
        {ticks(end).map((t) => (
          <text key={t} x={x(t)} y={H - 5} textAnchor="middle" className="fill-ink-3 text-[10px]">
            {clock(t)}
          </text>
        ))}
        <path d={area} fill="var(--ct)" fillOpacity={0.12} clipPath={`url(#${clipId}-ct)`} />
        <path d={area} fill="var(--t)" fillOpacity={0.12} clipPath={`url(#${clipId}-t)`} />
        <path d={line} fill="none" stroke="var(--ink-2)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {near && (
          <line x1={x(near[0])} x2={x(near[0])} y1={PAD.top} y2={PAD.top + PLOT_H} stroke="var(--ink-3)" strokeWidth={1} />
        )}
        {now != null && (
          <line x1={x(now)} x2={x(now)} y1={PAD.top} y2={PAD.top + PLOT_H} stroke="var(--ink)" strokeWidth={1.5} />
        )}
        {round.events.map((e, i) => {
          const cx = x(e.t)
          const cy = y(pAt(e.t))
          const side = e.sid ? round.sides[e.sid] : null
          const fill = side === 'ct' ? 'var(--ct)' : side === 't' ? 'var(--t)' : 'var(--ink-2)'
          const label = eventText(e, names)
          return (
            <g
              key={i}
              className="cursor-pointer"
              onClick={() => onGoto(e.t, e.sid ?? null)}
              role="button"
              aria-label={`${clock(e.t)} ${label}`}
            >
              {/* A hit target bigger than the mark. */}
              <circle cx={cx} cy={cy} r={9} fill="transparent" />
              {e.kind === 'kill' ? (
                <circle cx={cx} cy={cy} r={4} fill={fill} stroke="var(--surface)" strokeWidth={2} />
              ) : (
                <rect
                  x={cx - 4.5}
                  y={cy - 4.5}
                  width={9}
                  height={9}
                  transform={e.kind === 'plant' ? `rotate(45 ${cx} ${cy})` : undefined}
                  fill={fill}
                  stroke="var(--surface)"
                  strokeWidth={2}
                />
              )}
            </g>
          )
        })}
      </svg>
      {near && (
        <div
          className="pointer-events-none absolute top-6 z-10 w-max max-w-64 rounded-md border border-line bg-raised px-2 py-1 text-xs shadow-lg"
          style={{ left: `${(x(near[0]) / W) * 100}%`, transform: `translateX(${x(near[0]) > W * 0.6 ? '-105%' : '8px'})` }}
        >
          <div className="font-mono text-ink-3">{clock(near[0])}</div>
          <div>
            <b className="text-ink">{Math.round(near[1] * 100)}%</b> <span className="text-ink-2">CT</span>
            {' · '}
            <b className="text-ink">{Math.round((1 - near[1]) * 100)}%</b> <span className="text-ink-2">T</span>
          </div>
          {event && (
            <div className="text-ink-2">
              {eventText(event, names)} <span className="text-ink-3">({swingText(event.d_ct)} CT)</span>
            </div>
          )}
        </div>
      )}
      <details className="mt-1 text-xs text-ink-3">
        <summary className="cursor-pointer select-none">Хүснэгтээр</summary>
        <table className="mt-1 w-full tabular-nums">
          <thead className="text-left">
            <tr>
              <th className="py-0.5 font-normal">Цаг</th>
              <th className="py-0.5 font-normal">Үйл явдал</th>
              <th className="py-0.5 text-right font-normal">CT-ийн магадлал</th>
            </tr>
          </thead>
          <tbody>
            {round.events.map((e, i) => (
              <tr key={i} className="border-t-1 border-line-soft text-ink-2">
                <td className="py-0.5 font-mono">{clock(e.t)}</td>
                <td className="py-0.5">{eventText(e, names)}</td>
                <td className="py-0.5 text-right">{swingText(e.d_ct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  )
}

function eventText(e: Event, names: Record<string, string>) {
  const who = (sid?: string | null) => (sid ? names[sid] || '?' : 'орчин')
  if (e.kind === 'plant') return `${who(e.sid)} бөмбөг тавив`
  if (e.kind === 'defuse') return `${who(e.sid)} defuse хийв`
  return `${who(e.sid)} → ${who(e.victim)}${e.hs ? ' (HS)' : ''}`
}

// The sample closest to `t`; on a tie (an event's before and after), the after.
function nearest(points: number[][], t: number): number[] | null {
  let best: number[] | null = null
  for (const p of points) if (!best || Math.abs(p[0] - t) <= Math.abs(best[0] - t)) best = p
  return best
}

function nearestEvent(events: Event[], t: number): Event | null {
  let best: Event | null = null
  for (const e of events) {
    if (Math.abs(e.t - t) > 1.5) continue
    if (!best || Math.abs(e.t - t) < Math.abs(best.t - t)) best = e
  }
  return best
}

function ticks(end: number): number[] {
  const step = end > 90 ? 30 : end > 40 ? 15 : 10
  const out = []
  for (let t = 0; t <= end; t += step) out.push(t)
  return out
}

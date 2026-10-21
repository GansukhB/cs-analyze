// Who played for a Team when (docs/plans/05 TM-10): one row per Player, a bar
// for each stretch of Match Maps (45 days without one ends a stretch), newest
// on top. One hue: a bar is a Player's presence, not a verdict.
import { Link } from 'react-router'
import { $api } from '../api/client'

const ROW = 22
const LABEL = 120
const W = 760
const day = (s: string) => new Date(`${s}T00:00:00Z`).getTime()

export default function RosterSection({ teamId }: { teamId: number }) {
  const q = $api.useQuery('get', '/teams/{team_id}/roster', { params: { path: { team_id: teamId } } })
  const data = q.data
  if (!data || !data.from || !data.to || data.players.length === 0) return null
  const t0 = day(data.from)
  const t1 = Math.max(day(data.to), t0 + 86_400_000)
  const x = (s: string) => LABEL + ((day(s) - t0) / (t1 - t0)) * (W - LABEL - 8)
  const H = data.players.length * ROW + 24
  // Month ticks: the first of each month inside the span, at most eight labelled.
  const months: string[] = []
  const start = new Date(t0)
  for (let d = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 1)); d.getTime() <= t1; d.setUTCMonth(d.getUTCMonth() + 1)) {
    months.push(d.toISOString().slice(0, 10))
  }
  const every = Math.max(1, Math.ceil(months.length / 8))
  return (
    <section className="space-y-2">
      <h2 className="font-medium text-ink">Бүрэлдэхүүний түүх</h2>
      <p className="max-w-2xl text-sm text-ink-3">
        Тоглогч бүрийн энэ багт тоглосон үе: 45 хоног тоглоогүй бол мөр тасарна. Баганын дээр хулганаа аваачвал map-ын
        тоо харагдана.
      </p>
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[560px]" role="img" aria-label="Бүрэлдэхүүний цагийн шугам">
          {months.map((m, i) => (
            <g key={m}>
              <line x1={x(m)} x2={x(m)} y1={0} y2={H - 18} stroke="var(--line-soft)" strokeWidth={1} />
              {i % every === 0 && (
                <text x={x(m)} y={H - 4} fontSize={10} textAnchor="middle" fill="var(--ink-3)">
                  {m.slice(0, 7)}
                </text>
              )}
            </g>
          ))}
          {data.players.map((p, i) => {
            const y = i * ROW + 4
            return (
              <g key={p.steamid}>
                <Link to={`/players/${p.steamid}`}>
                  <text x={0} y={y + 12} fontSize={12} fill="var(--ink-2)">
                    {p.name}
                    <tspan fill="var(--ink-3)" fontSize={10}>
                      {' '}
                      {p.maps}
                    </tspan>
                  </text>
                </Link>
                {p.spans.map((s) => (
                  <rect
                    key={s.from}
                    x={x(s.from)}
                    y={y + 3}
                    width={Math.max(4, x(s.to) - x(s.from))}
                    height={ROW - 10}
                    rx={4}
                    fill="var(--mark-mine)"
                  >
                    <title>{`${p.name}: ${s.from} – ${s.to}, ${s.maps} map`}</title>
                  </rect>
                ))}
              </g>
            )
          })}
        </svg>
      </div>
    </section>
  )
}

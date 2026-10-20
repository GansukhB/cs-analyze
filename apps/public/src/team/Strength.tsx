// A Team's Rating and how it did against each tier of opponent (docs/plans TM-2,
// TM-10). One series over time, so no legend; each point carries its own tooltip.
import type { components } from '../api/schema'

type Strength = components['schemas']['TeamStrength']

const W = 640
const H = 120
const PAD = { l: 44, r: 12, t: 10, b: 22 }

function Trend({ points }: { points: Strength['trend'] }) {
  if (points.length < 2) return null
  const ratings = points.map((p) => p.rating)
  const lo = Math.min(...ratings)
  const hi = Math.max(...ratings)
  const span = hi - lo || 1
  const x = (i: number) => PAD.l + (i / (points.length - 1)) * (W - PAD.l - PAD.r)
  const y = (r: number) => PAD.t + (1 - (r - lo) / span) * (H - PAD.t - PAD.b)
  const path = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.rating).toFixed(1)}`).join(' ')
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Rating over time" className="w-full max-w-2xl">
      <line x1={PAD.l} x2={W - PAD.r} y1={H - PAD.b} y2={H - PAD.b} stroke="var(--line)" />
      <text x={PAD.l - 6} y={y(hi) + 4} textAnchor="end" fontSize="10" fill="var(--ink-3)">
        {Math.round(hi)}
      </text>
      <text x={PAD.l - 6} y={y(lo) + 4} textAnchor="end" fontSize="10" fill="var(--ink-3)">
        {Math.round(lo)}
      </text>
      <text x={PAD.l} y={H - 6} fontSize="10" fill="var(--ink-3)">
        {points[0].date}
      </text>
      <text x={W - PAD.r} y={H - 6} textAnchor="end" fontSize="10" fill="var(--ink-3)">
        {points[points.length - 1].date}
      </text>
      <path d={path} fill="none" stroke="var(--ink-2)" strokeWidth={2} strokeLinejoin="round" />
      {points.map((p, i) => (
        <circle key={i} cx={x(i)} cy={y(p.rating)} r={8} fill="transparent">
          <title>
            {p.date}: {Math.round(p.rating)}
          </title>
        </circle>
      ))}
      <circle cx={x(points.length - 1)} cy={y(points[points.length - 1].rating)} r={4} fill="var(--ink)" />
    </svg>
  )
}

export default function StrengthSection({ s }: { s: Strength }) {
  return (
    <section className="space-y-3">
      <h2 className="font-medium text-ink">Rating</h2>
      <p className="text-sm text-ink-2">
        <b className="font-mono text-lg text-ink">{Math.round(s.rating)}</b>
        {s.rank ? ` · идэвхтэй ${s.ranked} багаас #${s.rank}` : ''} · {s.series} цуврал
        {s.region ? ` · ${s.region}` : ''}
        {s.last ? ` · сүүлд ${s.last}` : ''}
        {s.cold && <span className="text-warn"> · цөөн цуврал, Rating тогтоогүй</span>}
      </p>
      <Trend points={s.trend} />
      {s.tiers.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-line bg-surface">
          <table className="w-full text-sm">
            <thead className="border-b border-line text-left text-xs uppercase text-ink-3">
              <tr>
                <th className="px-4 py-2">Өрсөлдөгч</th>
                <th className="px-4 py-2 text-right">Map</th>
                <th className="px-4 py-2 text-right">Хожсон</th>
                <th className="px-4 py-2 text-right">Rating-аар хүлээгдэх</th>
                <th className="px-4 py-2 text-right">Зөрүү</th>
              </tr>
            </thead>
            <tbody>
              {s.tiers.map((t) => (
                <tr key={t.tier} className="border-b border-line-soft last:border-0">
                  <td className="px-4 py-2">{t.tier}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{t.maps}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{t.won}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{t.expected}</td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums">
                    {t.residual > 0 ? '+' : ''}
                    {t.residual}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="px-4 py-2 text-xs text-ink-3">
            Хадгалсан Match Map бүрийг тэр өдрийн хоёр багийн Rating-аар хүлээгдэх хожилтой харьцуулав. Түвшин нь
            өрсөлдөгчийн одоогийн байр.
          </p>
        </div>
      )}
    </section>
  )
}

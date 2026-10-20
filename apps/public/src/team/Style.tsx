// A Team's style on a Map, Side by Side (docs/plans/05 TM-5): each number with
// its percentile among every Team on the Map. Style is neither good nor bad, so
// the bars are a Team's colour, not a verdict; the line marks the Pool's middle.
import { useState } from 'react'
import { $api } from '../api/client'
import type { components } from '../api/schema'

type TeamStyle = components['schemas']['TeamStyle']
type Metric = components['schemas']['StyleMetric']

const value = (m: Metric) => (m.unit === 's' ? `${m.value} с` : `${Math.round(m.value)}%`)

function Bar({ pct, colour }: { pct: number | null; colour: string }) {
  return (
    <span className="relative inline-block h-2 w-24 rounded-full bg-surface-2 align-middle" title={pct == null ? '' : `${pct}-р percentile`}>
      {pct != null && <span className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${pct}%`, background: colour }} />}
      <span className="absolute inset-y-[-2px] left-1/2 w-px bg-line" aria-hidden />
    </span>
  )
}

function Cell({ m, colour }: { m?: Metric; colour: string }) {
  if (!m) return <td className="py-1 pr-4 text-ink-3">—</td>
  return (
    <td className="py-1 pr-4 whitespace-nowrap">
      <span
        className={`mr-2 inline-block w-14 text-right font-mono ${m.thin ? 'text-ink-3' : 'text-ink'}`}
        title={`${m.n} раунд`}
      >
        {value(m)}
      </span>
      <Bar pct={m.pct} colour={colour} />
      <span className="ml-1 font-mono text-xs text-ink-3">{m.pct ?? '—'}</span>
    </td>
  )
}

/** One or two Teams' style on one Map, Side by Side. */
export function StyleTable({ teams }: { teams: { name: string; style: TeamStyle; colour: string }[] }) {
  const sides = ['t', 'ct', 'both']
  const label = (side: string) => teams.flatMap((t) => t.style.sides).find((s) => s.side === side)?.label ?? side
  return (
    <div className="space-y-3">
      {sides.map((side) => {
        const keys = [
          ...new Map(
            teams.flatMap((t) => t.style.sides.find((s) => s.side === side)?.metrics ?? []).map((m) => [m.key, m]),
          ).values(),
        ]
        if (!keys.length) return null
        return (
          <table key={side} className="text-sm">
            <thead className="text-left text-xs text-ink-3">
              <tr>
                <th className="py-1 pr-4 font-normal">{label(side)}</th>
                {teams.map((t) => (
                  <th key={t.name} className="py-1 pr-4 font-normal" style={{ color: t.colour }}>
                    {t.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {keys.map((k) => (
                <tr key={k.key} className="border-t-1 border-line">
                  <td className="py-1 pr-4 text-ink-2" title={`Өндөр percentile = ${k.more}`}>
                    {k.label}
                  </td>
                  {teams.map((t) => (
                    <Cell
                      key={t.name}
                      m={t.style.sides.find((s) => s.side === side)?.metrics.find((m) => m.key === k.key)}
                      colour={t.colour}
                    />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )
      })}
    </div>
  )
}

/** The Team page's section: one Map at a time. */
export default function StyleSection({ teamId, name }: { teamId: number; name: string }) {
  const [map, setMap] = useState<string | null>(null)
  const q = $api.useQuery('get', '/teams/{team_id}/style', {
    params: { path: { team_id: teamId }, query: map ? { map } : {} },
  })
  if (!q.data || !q.data.style) return null
  const chosen = q.data.style.map
  return (
    <section className="space-y-2">
      <h2 className="font-medium text-ink">Хэв маяг</h2>
      <p className="max-w-2xl text-sm text-ink-3">
        Map бүр дээрх тоо, тухайн map-ыг тоглосон бүх багийн дунд хэдэн percentile-д байгаа нь. Бүдэг тоо нь 5-аас цөөн
        раундад суурилсан.
      </p>
      <div className="flex flex-wrap gap-2 text-sm">
        {q.data.maps.map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMap(m)}
            className={`rounded-md border px-2 py-0.5 ${m === chosen ? 'border-ink-3 bg-raised text-ink' : 'border-line text-ink-3 hover:text-ink'}`}
          >
            {m.replace(/^de_/, '')}
          </button>
        ))}
      </div>
      <StyleTable teams={[{ name, style: q.data.style, colour: 'var(--mark-mine)' }]} />
    </section>
  )
}

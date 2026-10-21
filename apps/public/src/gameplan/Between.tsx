// GP-4: the break between Maps. What the opponent did differently on a Map they
// just played (their newest reviewed by default), against their other Maps:
// how they play today carries to the next Map, where they went does not.
import { useState } from 'react'
import { Link } from 'react-router'
import { $api } from '../api/client'

const pct = (v: number) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v * 100).toFixed(1)}%`

export default function Between({ mine, theirs }: { mine: number; theirs: number }) {
  const [played, setPlayed] = useState<number | undefined>()
  const q = $api.useQuery('get', '/gameplan/{mine}/vs/{theirs}/between', {
    params: { path: { mine, theirs }, query: played ? { played } : {} },
  })
  const d = q.data
  if (!d?.played) return null
  return (
    <section className="break-inside-avoid space-y-2 rounded-md border border-line bg-surface px-3 py-2">
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-sm font-semibold text-ink">Өмнөх Map-д тэд</h2>
        <select
          value={d.played.mm}
          onChange={(e) => setPlayed(Number(e.target.value))}
          className="rounded border border-line bg-surface-2 px-1.5 py-0.5 text-xs text-ink-2 print:hidden"
          aria-label="Тоглосон Map"
        >
          {d.recent.map((m) => (
            <option key={m.mm} value={m.mm}>
              {m.label} vs {m.against}
              {m.played_at ? ` · ${m.played_at}` : ''}
            </option>
          ))}
        </select>
        <Link to={`/matches/${d.played.match}/m/${d.played.num}`} className="text-xs text-ct hover:underline">
          Review →
        </Link>
        <span className="text-xs text-ink-3">ердийнх нь: бусад {d.usual_maps} Map</span>
      </header>
      {d.lines.length === 0 && d.players.length === 0 ? (
        <p className="text-xs text-ink-3">Ердийнхөөсөө илт ялгаатай зүйл алга (90%-иас итгэлтэй нь л гарна).</p>
      ) : (
        <ul className="space-y-0.5 text-xs text-ink-2">
          {d.lines.map((l, i) => (
            <li key={i} className={l.good ? 'text-good' : undefined}>
              {l.text}
            </li>
          ))}
          {d.players.map((p) => (
            <li key={p.sid}>
              <Link to={`/players/${p.sid}`} className="text-ink hover:underline">
                {p.name}
              </Link>{' '}
              {p.hot ? 'халуун' : 'хүйтэн'}: Swing {pct(p.here)}/раунд ({p.rounds} раунд), ихэвчлэн {pct(p.usual)}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

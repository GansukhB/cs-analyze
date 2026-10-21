// The veto lab (docs/plans/06 GP-10): a Fixture's veto played step by step.
// Every choice rides in the URL; each Map's chance starts at the Forecast's and
// can be moved by hand, with each side's strength and our Scrims beside it.
import { Link, useParams, useSearchParams } from 'react-router'
import { $api } from '../api/client'

const FORMATS = ['bo1', 'bo3', 'bo5'] as const
const KIND: Record<string, string> = { ban: 'ban', pick: 'pick' }
const pct = (p: number | null | undefined) => (p == null ? '—' : `${Math.round(p * 100)}%`)
const label = (m: string) => m.replace(/^de_/, '').replace(/^\w/, (c) => c.toUpperCase())

export default function VetoLabPage() {
  const params = useParams()
  const mine = Number(params.mine)
  const theirs = Number(params.theirs)
  const [search, setSearch] = useSearchParams()
  const format = (FORMATS as readonly string[]).includes(search.get('f') ?? '') ? (search.get('f') as (typeof FORMATS)[number]) : 'bo3'
  const weStart = search.get('s') !== '0'
  const done = (search.get('done') ?? '').split(',').filter(Boolean)
  const adjust: Record<string, number> = Object.fromEntries(
    (search.get('adj') ?? '')
      .split(',')
      .filter(Boolean)
      .map((x) => x.split(':'))
      .map(([m, v]) => [m, Number(v) || 0]),
  )
  const set = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(search)
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v)
      else next.delete(k)
    }
    setSearch(next, { replace: true })
  }
  const lab = $api.useQuery('post', '/gameplan/{mine}/vs/{theirs}/veto', {
    params: { path: { mine, theirs } },
    body: { format, we_start: weStart, done, adjust },
  })
  const header = $api.useQuery('get', '/gameplan/{mine}/vs/{theirs}', { params: { path: { mine, theirs } } })
  const move = (m: string, by: number) => {
    const next = { ...adjust, [m]: Math.max(-25, Math.min(25, (adjust[m] ?? 0) + by)) }
    set({
      adj:
        Object.entries(next)
          .filter(([, v]) => v)
          .map(([k, v]) => `${k}:${v}`)
          .join(',') || null,
    })
  }
  const v = lab.data?.veto
  return (
    <div className="space-y-6">
      <p className="font-mono text-xs text-ink-3">
        <Link to={`/gameplan/${mine}/vs/${theirs}`} className="hover:underline">
          {header.data ? `${header.data.my_team.name} — ${header.data.opponent.name}` : 'Game Plan'}
        </Link>{' '}
        / Veto
      </p>
      <h1 className="text-2xl font-semibold text-ink">Veto лаборатори</h1>
      <p className="max-w-3xl text-sm text-ink-2">
        Map бүрийн магадлал Forecast-аас эхэлнэ. Forecast бүх map-ыг Rating-ийн нэг ижил магадлалаар авдаг (map бүрийн
        засвар backtest-д таамаглалыг муутгасан), тиймээс хоёр багийн map дээрх хүч, манай Scrim-ийг харж магадлалыг гараар
        хөдөлгөнө. Алхам бүрт сонголтуудын цувралын хожлын магадлал гарна.
      </p>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {FORMATS.map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => set({ f, done: null })}
            className={`rounded-md border px-3 py-1 ${f === format ? 'border-ink-3 bg-raised text-ink' : 'border-line text-ink-3'}`}
          >
            {f.toUpperCase()}
          </button>
        ))}
        <button
          type="button"
          onClick={() => set({ s: weStart ? '0' : null, done: null })}
          className="rounded-md border border-line px-3 py-1 text-ink-2"
        >
          {weStart ? 'Бид эхэлнэ' : 'Тэд эхэлнэ'}
        </button>
        {done.length > 0 && (
          <button type="button" onClick={() => set({ done: done.slice(0, -1).join(',') || null })} className="text-ct underline">
            Буцаах
          </button>
        )}
      </div>

      {lab.data && (
        <table className="text-sm">
          <thead className="text-left text-xs text-ink-3">
            <tr>
              <th className="py-1 pr-5 font-normal">Map</th>
              <th className="py-1 pr-5 text-right font-normal">Магадлал</th>
              <th className="py-1 pr-5 font-normal" />
              <th className="py-1 pr-5 text-right font-normal">Манай хүч</th>
              <th className="py-1 pr-5 text-right font-normal">Тэдний хүч</th>
              <th className="py-1 pr-5 font-normal">Манай Scrim</th>
              <th className="py-1 font-normal">Strat</th>
            </tr>
          </thead>
          <tbody className="text-ink-2">
            {lab.data.maps.map((m) => (
              <tr key={m.map} className={`border-t-1 border-line ${done.includes(m.map) ? 'opacity-40' : ''}`}>
                <td className="py-1 pr-5 text-ink">{label(m.map)}</td>
                <td className="py-1 pr-5 text-right font-mono text-ink">
                  {pct(m.p)}
                  {m.adjust !== 0 && <span className="ml-1 text-xs text-ink-3">({m.adjust > 0 ? '+' : ''}{m.adjust})</span>}
                </td>
                <td className="py-1 pr-5 whitespace-nowrap text-xs">
                  <button type="button" onClick={() => move(m.map, -5)} className="px-1 text-ink-3 hover:text-ink">
                    −5
                  </button>
                  <button type="button" onClick={() => move(m.map, 5)} className="px-1 text-ink-3 hover:text-ink">
                    +5
                  </button>
                </td>
                <td className="py-1 pr-5 text-right font-mono">
                  {m.mine?.shrunk != null ? `${m.mine.shrunk}% · ${m.mine.maps}` : '—'}
                </td>
                <td className="py-1 pr-5 text-right font-mono">
                  {m.theirs?.shrunk != null ? `${m.theirs.shrunk}% · ${m.theirs.maps}` : '—'}
                </td>
                <td className="py-1 pr-5 font-mono text-xs">
                  {m.scrims ? `${m.scrims.share}% · ${m.scrims.maps} map` : '—'}
                </td>
                <td className="py-1 font-mono text-xs" title="Идэвхтэй Strat · сүүлийн 30 хоногт тоглогдсон">
                  {m.strats ? `${m.strats.active} · ${m.strats.recent}` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {lab.data && !v && <p className="text-sm text-ink-3">Хоёр багийн Rating байхгүй тул veto тооцоолох боломжгүй.</p>}
      {v && (
        <section className="space-y-3">
          <p className="text-sm text-ink-2">
            Цуврал хожих магадлал одоо: <b className="text-ink">{pct(v.expected)}</b> (тэд хамгийн муугаар сонговол{' '}
            {pct(v.minimax)}). Тоглогдох map: <b className="text-ink">{v.maps.map(label).join(', ')}</b>.
          </p>
          <ol className="space-y-1 text-sm">
            {v.steps.map((s, i) => {
              const taken = done[i]
              const projected = !taken ? v.line[i - done.length] : undefined
              return (
                <li key={i} className={`flex flex-wrap items-baseline gap-2 ${i === done.length ? '' : 'text-ink-3'}`}>
                  <span className="w-6 font-mono">{i + 1}.</span>
                  <span className="w-24">{s.who === 'mine' ? 'Бид' : 'Тэд'} {KIND[s.kind]}</span>
                  {taken ? (
                    <b className="text-ink">{label(taken)}</b>
                  ) : i === done.length && v.next ? (
                    <span className="flex flex-wrap gap-1.5">
                      {v.next.options.map((o) => (
                        <button
                          key={o.map}
                          type="button"
                          onClick={() => set({ done: [...done, o.map].join(',') })}
                          className="rounded-md border border-line bg-raised px-2 py-0.5 text-ink hover:border-ink-3"
                          title={`Энэ сонголтын дараа цуврал: ${pct(o.expected)} (хамгийн муу ${pct(o.minimax)})`}
                        >
                          {label(o.map)} <span className="font-mono text-xs text-ink-3">{pct(o.expected)}</span>
                          {o.chance != null && <span className="ml-1 font-mono text-xs text-warn">{pct(o.chance)}</span>}
                        </button>
                      ))}
                    </span>
                  ) : projected ? (
                    <span className="italic">≈ {label(projected.map)}</span>
                  ) : null}
                </li>
              )
            })}
          </ol>
          {v.next?.who === 'theirs' && (
            <p className="text-xs text-ink-3">Шар хувь: тэдний энэ алхамд тухайн map-ыг сонгох магадлал.</p>
          )}
        </section>
      )}
    </div>
  )
}

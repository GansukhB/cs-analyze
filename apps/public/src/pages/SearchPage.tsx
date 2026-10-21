// The Round search (docs/plans/09 VIZ-7): "find me Rounds like this". Pick a
// Map and the Side the conditions are about, then Callouts with how many of
// that Side stood there and when; the matching Rounds open in ghost mode.
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { $api } from '../api/client'
import type { components } from '../api/schema'
import { drawHeatmap, type HeatData } from '../gameplan/heatmap'

type Condition = components['schemas']['SearchCondition']
const field = 'rounded-md border border-line bg-surface-2 px-2 py-1 text-sm text-ink'
const label = (m: string) => m.replace(/^de_/, '').replace(/^\w/, (c) => c.toUpperCase())

export default function SearchPage() {
  const maps = $api.useQuery('get', '/strats/maps')
  const teams = $api.useQuery('get', '/teams')
  const [map, setMap] = useState('')
  const chosen = map || maps.data?.[0] || ''
  const places = $api.useQuery('get', '/search/places/{map_name}', { params: { path: { map_name: chosen } } }, { enabled: !!chosen })
  // VIZ-7: or one of the Map's hand-drawn Spots (finer than a Callout on a site).
  const spotNames = $api.useQuery('get', '/search/spots/{map_name}', { params: { path: { map_name: chosen } } }, { enabled: !!chosen })
  const [side, setSide] = useState<'t' | 'ct'>('t')
  const [team, setTeam] = useState<number | null>(null)
  const [buy, setBuy] = useState<'' | 'full' | 'light'>('')
  const [conds, setConds] = useState<Condition[]>([{ place: '', kind: 'place', min: 2, max: null, start: 15, end: 30 }])
  // VIZ-7: where the side died or got its kills in all the matched Rounds.
  const [heat, setHeat] = useState<'' | 'deaths' | 'kills'>('deaths')
  // VIZ-5: how the Map stood for the Side's Team when the Round began.
  const [score, setScore] = useState<'' | 'ahead' | 'close' | 'behind'>('')
  const run = $api.useMutation('post', '/search/rounds')
  const set = (i: number, patch: Partial<Condition>) => setConds(conds.map((c, k) => (k === i ? { ...c, ...patch } : c)))
  const ready = conds.every((c) => c.place)
  const result = run.data
  const ghost = result?.rounds.length
    ? `/ghost?r=${result.rounds
        .slice(0, 30)
        .map((r) => `${r.match}.${r.map}.${r.round}`)
        .join(',')}&side=${side}`
    : null
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold text-ink">Раунд хайх</h1>
      <p className="max-w-3xl text-sm text-ink-2">
        Жишээ нь «15–30 секундэд B site-д 2+ T» гэх мэт нөхцлөөр раундуудыг олно. Нөхцөл бүр тухайн секундын цонхонд (±2 с)
        биелэх ёстой; бүх нөхцөл зэрэг.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <select value={chosen} onChange={(e) => setMap(e.target.value)} className={field}>
          {(maps.data ?? []).map((m) => (
            <option key={m} value={m}>
              {label(m)}
            </option>
          ))}
        </select>
        <select value={side} onChange={(e) => setSide(e.target.value as 't' | 'ct')} className={field}>
          <option value="t">T тал</option>
          <option value="ct">CT тал</option>
        </select>
        <select value={team ?? ''} onChange={(e) => setTeam(e.target.value ? Number(e.target.value) : null)} className={field}>
          <option value="">Бүх баг</option>
          {(teams.data?.teams ?? []).map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
        <select value={score} onChange={(e) => setScore(e.target.value as '' | 'ahead' | 'close' | 'behind')} className={field}>
          <option value="">Бүх оноо</option>
          <option value="ahead">Тэргүүлж (2+)</option>
          <option value="close">Ойр (±1)</option>
          <option value="behind">Хоцорч (2+)</option>
        </select>
        <select value={heat} onChange={(e) => setHeat(e.target.value as '' | 'deaths' | 'kills')} className={field}>
          <option value="deaths">Heatmap: үхсэн газар</option>
          <option value="kills">Heatmap: kill авсан газар</option>
          <option value="">Heatmap-гүй</option>
        </select>
        <select value={buy} onChange={(e) => setBuy(e.target.value as '' | 'full' | 'light')} className={field}>
          <option value="">Бүх buy</option>
          <option value="full">Full</option>
          <option value="light">Eco/force/pistol</option>
        </select>
      </div>
      <div className="space-y-2">
        {conds.map((c, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2 text-sm text-ink-2">
            <select
              value={c.place ? `${c.kind}:${c.place}` : ''}
              onChange={(e) => {
                const [kind, ...rest] = e.target.value.split(':')
                set(i, { kind: kind === 'spot' ? 'spot' : 'place', place: rest.join(':') })
              }}
              className={field}
            >
              <option value="">Callout эсвэл Spot…</option>
              <optgroup label="Callout">
                {(places.data ?? []).map((p) => (
                  <option key={p} value={`place:${p}`}>
                    {p}
                  </option>
                ))}
              </optgroup>
              {(spotNames.data ?? []).length > 0 && (
                <optgroup label="Spot">
                  {(spotNames.data ?? []).map((p) => (
                    <option key={p} value={`spot:${p}`}>
                      {p}
                    </option>
                  ))}
                </optgroup>
              )}
            </select>
            дээр
            <input type="number" min={0} max={5} value={c.min} onChange={(e) => set(i, { min: Number(e.target.value) })} className={`${field} w-16`} />
            –
            <input
              type="number"
              min={0}
              max={5}
              placeholder="5"
              value={c.max ?? ''}
              onChange={(e) => set(i, { max: e.target.value ? Number(e.target.value) : null })}
              className={`${field} w-16`}
            />
            тоглогч,
            <input type="number" min={0} max={180} value={c.start} onChange={(e) => set(i, { start: Number(e.target.value) })} className={`${field} w-16`} />
            –
            <input type="number" min={0} max={180} value={c.end} onChange={(e) => set(i, { end: Number(e.target.value) })} className={`${field} w-16`} />
            секундэд
            {conds.length > 1 && (
              <button type="button" onClick={() => setConds(conds.filter((_x, k) => k !== i))} className="text-ink-3 hover:text-crit">
                ✕
              </button>
            )}
          </div>
        ))}
        <div className="flex gap-3 text-sm">
          {conds.length < 6 && (
            <button
              type="button"
              onClick={() => setConds([...conds, { place: '', kind: 'place', min: 1, max: null, start: 0, end: 40 }])}
              className="text-ct hover:underline"
            >
              + нөхцөл
            </button>
          )}
          <button
            type="button"
            disabled={!ready || run.isPending}
            onClick={() =>
              run.mutate({
                body: { map_name: chosen, side, team_id: team, buy: buy || null, conditions: conds, heat: heat || null, score: score || null },
              })
            }
            className="rounded-md bg-ct px-4 py-1.5 font-medium text-ground disabled:opacity-50"
          >
            {run.isPending ? 'Хайж байна…' : 'Хайх'}
          </button>
        </div>
      </div>
      {result && (
        <section className="space-y-2">
          <p className="text-sm text-ink-2">
            {result.looked} раундаас <b className="text-ink">{result.found}</b> нь таарав
            {result.found > 0 && `, ${side.toUpperCase()} тал ${result.won}-д нь хожсон (${Math.round((100 * result.won) / result.found)}%)`}.
            {ghost && (
              <Link to={ghost} className="ml-2 text-ct hover:underline">
                ⧉ давхарлаж үзэх
              </Link>
            )}
          </p>
          {result.heat && <Heat data={result.heat as unknown as HeatData} caption={String(result.heat.subtitle ?? '')} />}
          <ul className="grid gap-x-6 text-sm sm:grid-cols-2">
            {result.rounds.map((r) => (
              <li key={`${r.match}-${r.map}-${r.round}`} className="flex gap-2">
                <Link to={`/matches/${r.match}/m/${r.map}?round=${r.round}`} className="font-mono text-ct">
                  R{r.round}
                </Link>
                <span className="text-ink">{r.team}</span>
                <span className="text-xs text-ink-3">
                  {r.buy} · {r.played_at ?? ''}
                </span>
                <span className={r.won ? 'text-good' : 'text-crit'}>{r.won ? 'хожсон' : 'алдсан'}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

function Heat({ data, caption }: { data: HeatData; caption: string }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    if (canvas.current) void drawHeatmap(canvas.current, data, Math.min(560, window.innerWidth - 32))
  }, [data])
  return (
    <figure className="space-y-1">
      <canvas ref={canvas} className="max-w-full rounded-lg" />
      <figcaption className="text-xs text-ink-3">{caption}</figcaption>
    </figure>
  )
}

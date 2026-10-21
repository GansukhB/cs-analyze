// PL-9: two Players side by side, a tryout against the Player whose spot they
// would take: every number over every Match Map they played, for any Team, each
// read from the same stored rows as their Player pages.
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { $api } from '../api/client'
import type { components } from '../api/schema'

type Page = components['schemas']['PlayerPage']
type Row = { label: string; get: (p: Page) => number | null | undefined; unit?: string; better?: 'higher' | 'lower' }

const pct = (v: number) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v * 100).toFixed(1)}%`
const ROWS: Row[] = [
  { label: 'Map', get: (p) => p.totals.maps },
  { label: 'Раунд', get: (p) => p.totals.rounds },
  { label: 'ADR', get: (p) => p.totals.adr, better: 'higher' },
  { label: 'KAST %', get: (p) => p.totals.kast_pct, better: 'higher' },
  { label: 'Opening хожил %', get: (p) => p.totals.opening_win_pct, better: 'higher' },
  { label: 'Trade хийгдсэн үхэл %', get: (p) => p.totals.traded_death_pct, better: 'higher' },
  { label: 'Swing/раунд', get: (p) => p.totals.swing_per_round, unit: 'swing', better: 'higher' },
  { label: 'CT ADR', get: (p) => p.sides.ct?.adr, better: 'higher' },
  { label: 'T ADR', get: (p) => p.sides.t?.adr, better: 'higher' },
  { label: 'Pistol Swing/раунд', get: (p) => p.pressure.find((r) => r.key === 'pistol')?.per_round, unit: 'swing', better: 'higher' },
  { label: 'Match point Swing/раунд', get: (p) => p.pressure.find((r) => r.key === 'match_point')?.per_round, unit: 'swing', better: 'higher' },
  { label: 'Ойр төгсгөл Swing/раунд', get: (p) => p.pressure.find((r) => r.key === 'close')?.per_round, unit: 'swing', better: 'higher' },
  { label: 'Map хоорондын хэлбэлзэл (percentile)', get: (p) => p.consistency?.pct, better: 'lower' },
  { label: 'Анхны цохилт хүртэл (ms)', get: (p) => p.aim?.ttd_ms, better: 'lower' },
]

function Picker({ value, onPick }: { value: string; onPick: (sid: string) => void }) {
  const [q, setQ] = useState('')
  const found = $api.useQuery('get', '/gameplan/players', { params: { query: { q } } }, { enabled: q.length >= 2 })
  return (
    <div className="space-y-1">
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Тоглогчийн нэр…"
        className="w-full rounded-md border border-line bg-surface-2 px-2 py-1 text-sm text-ink"
      />
      {q.length >= 2 && (
        <ul className="max-h-40 overflow-y-auto text-sm">
          {(found.data?.players ?? []).map((p) => (
            <li key={p.steamid}>
              <button
                type="button"
                onClick={() => {
                  onPick(p.steamid)
                  setQ('')
                }}
                className={`text-left hover:underline ${p.steamid === value ? 'text-ct' : 'text-ink-2'}`}
              >
                {p.name} <span className="text-xs text-ink-3">{p.team} · {p.maps} map</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function ComparePage() {
  const [search, setSearch] = useSearchParams()
  const a = search.get('a') ?? ''
  const b = search.get('b') ?? ''
  const set = (key: string, sid: string) => {
    const next = new URLSearchParams(search)
    next.set(key, sid)
    setSearch(next, { replace: true })
  }
  const pa = $api.useQuery('get', '/players/{steamid}', { params: { path: { steamid: a } } }, { enabled: !!a })
  const pb = $api.useQuery('get', '/players/{steamid}', { params: { path: { steamid: b } } }, { enabled: !!b })
  const both = [pa.data, pb.data]
  const show = (r: Row, v: number | null | undefined) => (v == null ? '—' : r.unit === 'swing' ? pct(v) : String(Math.round(v * 10) / 10))
  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold text-ink">Тоглогч харьцуулах</h1>
        <p className="max-w-3xl text-sm text-ink-2">
          Сонгон шалгаруулалтын тоглогчийг манай байрлалын тоглогчтой: бүх багт тоглосон бүх Match Map-ын тоо. Цөөн map-тай
          тоглогчийн тоо азаас их хамаарна; Swing ба Finding нь Review хийгдсэн map-аас.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Picker value={a} onPick={(sid) => set('a', sid)} />
        <Picker value={b} onPick={(sid) => set('b', sid)} />
      </div>
      {(pa.data || pb.data) && (
        <table className="text-sm">
          <thead className="text-left">
            <tr>
              <th className="py-1 pr-6 font-normal text-ink-3" />
              {both.map((p, i) => (
                <th key={i} className="py-1 pr-6 font-medium text-ink">
                  {p ? (
                    <Link to={`/players/${p.player.steamid}`} className="hover:underline">
                      {p.player.name}
                    </Link>
                  ) : (
                    '—'
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ROWS.map((r) => {
              const [x, y] = both.map((p) => (p ? r.get(p) : null))
              const lead = x == null || y == null || x === y || !r.better ? -1 : (r.better === 'higher') === x > y ? 0 : 1
              return (
                <tr key={r.label} className="border-t-1 border-line">
                  <td className="py-1 pr-6 text-ink-2">{r.label}</td>
                  {[x, y].map((v, i) => (
                    <td key={i} className={`py-1 pr-6 font-mono ${lead === i ? 'text-ink' : 'text-ink-3'}`}>
                      {show(r, v)}
                      {lead === i && ' ◂'}
                    </td>
                  ))}
                </tr>
              )
            })}
            <tr className="border-t-1 border-line align-top">
              <td className="py-1 pr-6 text-ink-2">Хамгийн их давтагдсан Finding</td>
              {both.map((p, i) => (
                <td key={i} className="py-1 pr-6 text-xs text-ink-2">
                  {(p?.findings ?? [])
                    .filter((f) => f.per24 != null && f.pool_per24 != null && f.per24 > f.pool_per24)
                    .slice(0, 4)
                    .map((f) => (
                      <div key={f.code}>
                        {f.label} {f.per24}/24 <span className="text-ink-3">(бусад {f.pool_per24})</span>
                      </div>
                    ))}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      )}
    </div>
  )
}

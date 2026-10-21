// The lineup library (docs/plans/08 SB-3): grenades thrown the same way again,
// Map by Map, with the practice-server command that puts you on the spot.
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { $api } from '../api/client'
import { useMyTeams } from '../auth/useMe'

const TYPES: [string, string][] = [
  ['', 'Бүгд'],
  ['smoke', 'Smoke'],
  ['inferno', 'Molotov'],
  ['flash', 'Flash'],
  ['he', 'HE'],
]
const label = (m: string) => m.replace(/^de_/, '').replace(/^\w/, (c) => c.toUpperCase())
const SHOWN = 60

export default function LineupsPage() {
  const [search, setSearch] = useSearchParams()
  const maps = $api.useQuery('get', '/strats/maps')
  const myTeams = useMyTeams()
  const map = search.get('map') ?? maps.data?.[0] ?? ''
  const side = search.get('side') ?? ''
  const type = search.get('type') ?? ''
  const team = search.get('team') ?? ''
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(search)
    if (v) next.set(k, v)
    else next.delete(k)
    setSearch(next, { replace: true })
  }
  const list = $api.useQuery(
    'get',
    '/lineups/{map_name}',
    { params: { path: { map_name: map }, query: { ...(side ? { side } : {}), ...(type ? { type } : {}), ...(team ? { team } : {}) } } },
    { enabled: !!map },
  )
  const [copied, setCopied] = useState('')
  const copy = (key: string, text: string) => {
    void navigator.clipboard?.writeText(text).then(() => setCopied(key))
  }
  const chip = (on: boolean) => `rounded-md border px-2 py-0.5 ${on ? 'border-ink-3 bg-raised text-ink' : 'border-line text-ink-3 hover:text-ink'}`
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold text-ink">Lineup-ийн сан</h1>
      <p className="max-w-3xl text-sm text-ink-2">
        Нэг цэгээс ижил онилгоор нэг газар руу 3+ удаа шидсэн граната. «setpos» нь practice server-т тэр байрлалд аваачих
        команд (хөлийн байрлал, pitch, yaw).
      </p>
      <div className="flex flex-wrap gap-2 text-sm">
        {(maps.data ?? []).map((m) => (
          <button key={m} type="button" onClick={() => set('map', m)} className={chip(m === map)}>
            {label(m)}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap gap-2 text-sm">
        {TYPES.map(([k, l]) => (
          <button key={k} type="button" onClick={() => set('type', k)} className={chip(type === k)}>
            {l}
          </button>
        ))}
        {(['', 't', 'ct'] as const).map((s) => (
          <button key={s} type="button" onClick={() => set('side', s)} className={chip(side === s)}>
            {s ? s.toUpperCase() : 'Хоёр тал'}
          </button>
        ))}
        <button type="button" onClick={() => set('team', '')} className={chip(!team)}>
          Бүх баг
        </button>
        {myTeams.map((t) => (
          <button key={t.id} type="button" onClick={() => set('team', t.name)} className={chip(team === t.name)}>
            {t.name}
          </button>
        ))}
      </div>
      {!list.data ? (
        <p className="text-ink-3">Уншиж байна…</p>
      ) : list.data.length === 0 ? (
        <p className="text-sm text-ink-3">Энэ шүүлтүүрт lineup алга (шидсэн агшин schema 14-өөс хойш parse хийсэн map-д л бий).</p>
      ) : (
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-ink-3">
            <tr>
              <th className="py-1 pr-3 font-normal">Граната</th>
              <th className="py-1 pr-3 font-normal">Хаанаас → хаашаа</th>
              <th className="py-1 pr-3 text-right font-normal">Удаа</th>
              <th className="py-1 pr-3 text-right font-normal">Нислэг</th>
              <th className="py-1 pr-3 font-normal">Хэн</th>
              <th className="py-1 font-normal">Practice</th>
            </tr>
          </thead>
          <tbody className="text-ink-2">
            {list.data.slice(0, SHOWN).map((lu) => (
              <tr key={lu.key} className="border-t-1 border-line align-top">
                <td className="py-1 pr-3">
                  <span className="mr-1 font-mono text-xs text-ink-3">{lu.side.toUpperCase()}</span>
                  {lu.type}
                </td>
                <td className="py-1 pr-3 text-ink">
                  {lu.from || '?'} → {lu.to || '?'}{' '}
                  {lu.refs.slice(0, 3).map((r) => (
                    <Link
                      key={`${r.match}-${r.map}-${r.round}`}
                      to={`/matches/${r.match}/m/${r.map}?round=${r.round}`}
                      className="font-mono text-xs text-ct"
                    >
                      R{r.round}{' '}
                    </Link>
                  ))}
                </td>
                <td className="py-1 pr-3 text-right font-mono">{lu.throws}</td>
                <td className="py-1 pr-3 text-right font-mono">{lu.flight == null ? '—' : `${lu.flight}с`}</td>
                <td className="py-1 pr-3 text-xs">{lu.teams.map(([t, n]) => `${t} ${n}`).join(', ')}</td>
                <td className="py-1">
                  <button type="button" onClick={() => copy(lu.key, lu.setpos)} className="font-mono text-xs text-ct hover:underline" title={lu.setpos}>
                    {copied === lu.key ? 'хуулсан ✓' : 'setpos хуулах'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

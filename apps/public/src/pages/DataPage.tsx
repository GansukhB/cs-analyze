// What the stored data covers, and what it lacks (docs/plans/02 DATA-9): each
// Team's parsed Match Maps and what they miss, each Map's Pool, and the Match
// Maps a Scout would download again.
import { Link } from 'react-router'
import { $api } from '../api/client'

// Each lack, what it costs, in the order the table shows them.
const FLAGS: [string, string, string][] = [
  ['behind', 'Хоцорсон', 'Parse-ийн schema одоогийнхоос хоцорсон'],
  ['no_loadout', 'Loadout-гүй', 'Tick Data-д economy/Loadout алга: Scout тоглолтыг дахин татна'],
  ['no_sightings', 'Sighting-гүй', 'Хэн хэнийг харсан нь алга: Review-ийн 4 Finding, vision-ий шугам үгүй'],
  ['no_events', 'Event-гүй', 'Schema 14-ийн timeout, граната шидсэн цэг, round_stats алга'],
  ['derived_stale', 'Cut хуучин', 'Replay, walks, geometry хуучин: нээхэд дахин тасална'],
  ['review_stale', 'Review хуучин', 'Review хуучин: worker шинэчилнэ'],
]
const day = (v: string | null) => (v ? v.slice(0, 10) : '—')

export default function DataPage() {
  const q = $api.useQuery('get', '/data/coverage')
  if (q.isError) return <p className="text-crit">Датаны тоймыг уншиж чадсангүй.</p>
  if (!q.data) return <p className="text-ink-3">Уншиж байна…</p>
  const { totals, teams, maps, queue, queued, schema_version } = q.data
  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold text-ink">Датаны хамрах хүрээ</h1>
        <p className="text-sm text-ink-2">
          {totals.maps ?? 0} map parse хийгдсэн (schema {schema_version}).{' '}
          {FLAGS.filter(([k]) => totals[k]).map(([k, label]) => (
            <span key={k} className="mr-3">
              {label}: <b className="font-mono text-ink">{totals[k]}</b>
            </span>
          ))}
        </p>
      </div>

      <section className="space-y-2">
        <h2 className="font-medium text-ink">Багууд</h2>
        <div className="overflow-x-auto">
          <table className="text-sm">
            <thead className="text-left text-xs text-ink-3">
              <tr>
                <th className="py-1 pr-4 font-normal">Баг</th>
                <th className="py-1 pr-4 font-normal">Map</th>
                <th className="py-1 pr-4 font-normal">Map бүрээр</th>
                {FLAGS.map(([k, label, hint]) => (
                  <th key={k} className="py-1 pr-3 font-normal" title={hint}>
                    {label}
                  </th>
                ))}
                <th className="py-1 pr-4 font-normal">Сүүлд тоглосон</th>
                <th className="py-1 pr-4 font-normal">Parse</th>
              </tr>
            </thead>
            <tbody>
              {teams.map((t) => (
                <tr key={t.id} className="border-t-1 border-line">
                  <td className="py-1 pr-4 whitespace-nowrap">
                    <Link to={`/teams/${t.id}`} className="text-ink hover:underline">
                      {t.name}
                    </Link>
                    {t.mine && <span className="ml-1 rounded border border-line px-1 text-xs text-ct">манай</span>}
                  </td>
                  <td className="py-1 pr-4 font-mono text-ink">{t.maps}</td>
                  <td className="py-1 pr-4 text-xs whitespace-nowrap text-ink-3">
                    {t.by_map.map(([m, n]) => `${String(m).replace(/^de_/, '')} ${n}`).join(' · ')}
                  </td>
                  {FLAGS.map(([k]) => (
                    <td key={k} className={`py-1 pr-3 font-mono ${t.flags[k] ? 'text-warn' : 'text-ink-3'}`}>
                      {t.flags[k] ?? '·'}
                    </td>
                  ))}
                  <td className="py-1 pr-4 font-mono text-xs whitespace-nowrap text-ink-2">{day(t.last_played)}</td>
                  <td className="py-1 pr-4 font-mono text-xs whitespace-nowrap text-ink-3">{day(t.last_parsed)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-[auto_1fr]">
        <section className="space-y-2">
          <h2 className="font-medium text-ink">Map бүрийн Pool</h2>
          <table className="text-sm">
            <thead className="text-left text-xs text-ink-3">
              <tr>
                <th className="py-1 pr-4 font-normal">Map</th>
                <th className="py-1 pr-4 font-normal">Тоглолт</th>
                <th className="py-1 pr-4 font-normal">Баг</th>
              </tr>
            </thead>
            <tbody>
              {maps.map((m) => (
                <tr key={m.map} className="border-t-1 border-line">
                  <td className="py-1 pr-4 text-ink">{m.map.replace(/^de_/, '')}</td>
                  <td className="py-1 pr-4 font-mono">{m.maps}</td>
                  <td className="py-1 pr-4 font-mono">{m.teams}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section className="space-y-2">
          <h2 className="font-medium text-ink">Дахин татах дараалал · {queued}</h2>
          <p className="max-w-2xl text-sm text-ink-3">
            Schema-аас хоцорсон, Tick Data-аасаа дахин parse хийж чадахгүй map-ууд. Тэдгээрийн тоглолтыг агуулсан Scout
            demo-г дахин татна.
          </p>
          <ul className="text-sm">
            {queue.map((r) => (
              <li key={`${r.match}-${r.map}`} className="flex gap-2 border-t-1 border-line py-1">
                <Link to={`/matches/${r.match}/m/${r.map}`} className="text-ct hover:underline">
                  {r.teams}
                </Link>
                <span className="text-ink-2">{r.map_name.replace(/^de_/, '')}</span>
                <span className="font-mono text-xs text-ink-3">{day(r.played_at)}</span>
                <span className="text-xs text-warn">{r.reason === 'no_tickdata' ? 'Tick Data алга' : 'Loadout алга'}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}

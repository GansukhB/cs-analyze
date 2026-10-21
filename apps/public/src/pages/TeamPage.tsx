import { Link, useParams } from 'react-router'
import { $api } from '../api/client'
import MapPool from '../team/MapPool'
import StrengthSection from '../team/Strength'
import StyleSection from '../team/Style'
import AfterContactSection from '../team/AfterContact'
import type { components } from '../api/schema'
import Count from '../components/Count'
import { day, PILL } from '../jobs/format'
import { LoadError } from '../ui/LoadError'
import { PageSkeleton } from '../ui/Skeleton'

type TeamResult = components['schemas']['TeamResult']

const OUTCOME: Record<string, string> = {
  win: 'text-good',
  loss: 'text-crit',
  draw: 'text-warn',
}

export default function TeamPage() {
  const { teamId = '' } = useParams()
  const team = $api.useQuery('get', '/teams/{team_id}', { params: { path: { team_id: Number(teamId) } } })
  if (team.error) return <LoadError error={team.error} what="Баг" retry={() => void team.refetch()} />
  if (!team.data) return <PageSkeleton />
  const { team: info, record, results, n_parsed_maps, map_record, players, plannable = [], strength, map_pool } =
    team.data
  const plural = (n: number, word: string, many = `${word}s`) => `${n} ${n === 1 ? word : many}`

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <p className="font-mono text-xs text-ink-3">
          <Link to="/teams" className="hover:underline">Teams</Link> /
        </p>
        <h1 className="text-2xl font-semibold text-ink">{info.name}</h1>
        <p className="max-w-2xl text-ink-2">
          {info.identified ? (
            <>
              HLTV team {info.hltv_id} —{' '}
              <a href={info.hltv_url} target="_blank" rel="noreferrer" className="text-ct hover:underline">
                their page
              </a>
              .{' '}
            </>
          ) : (
            'No HLTV id: this team has only ever been seen as the opponent named on somebody else\'s results row, so it has no results page to fetch from. '
          )}
          Everything below is read from what has been stored, not from HLTV.
        </p>
        <div className="flex flex-wrap gap-3 pt-2">
          <Count n={`${record.won}–${record.lost}${record.drawn ? `–${record.drawn}` : ''}`} label="match record" />
          <Count n={results.length} label={results.length === 1 ? 'match stored' : 'matches stored'} />
          <Count n={n_parsed_maps} label={n_parsed_maps === 1 ? 'map parsed' : 'maps parsed'} />
          <Count n={players.length} label={players.length === 1 ? 'player seen' : 'players seen'} />
        </div>
      </div>

      {strength && <StrengthSection s={strength} />}
      {map_pool && <MapPool pool={map_pool} />}
      {n_parsed_maps > 0 && <StyleSection teamId={info.id} name={info.name} />}
      {n_parsed_maps > 0 && <AfterContactSection teamId={info.id} name={info.name} />}

      {plannable.length > 0 && (
        <section className="space-y-2">
          <h2 className="font-medium text-ink">Build a plan</h2>
          <div className="flex flex-wrap gap-2">
            {plannable.map((opp) => (
              <Link
                key={opp.id}
                to={`/gameplan/${info.id}/vs/${opp.id}`}
                className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm text-ink hover:border-ct"
              >
                {info.name} vs {opp.name}
              </Link>
            ))}
          </div>
          <p className="text-xs text-ink-3">
            Only opponents this team has met that have parsed maps of their own — the plan is computed from demos
            on both sides.
          </p>
        </section>
      )}

      <section className="space-y-2">
        <h2 className="font-medium text-ink">Results</h2>
        {results.length ? (
          <div className="overflow-x-auto rounded-xl border border-line bg-surface">
            <table className="w-full text-sm">
              <thead className="border-b border-line text-left text-xs uppercase text-ink-3">
                <tr>
                  <th className="px-4 py-2">Date</th>
                  <th className="px-4 py-2">Opponent</th>
                  <th className="px-4 py-2 text-right">Score</th>
                  <th className="px-4 py-2">Maps</th>
                  <th className="px-4 py-2">Event</th>
                  <th className="px-4 py-2">Demo</th>
                </tr>
              </thead>
              <tbody>
                {results.map((row) => (
                  <ResultRow key={row.match_id} row={row} />
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-ink-3">No matches stored for this team.</p>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="font-medium text-ink">Map record</h2>
        {map_record.length ? (
          <>
            <div className="overflow-x-auto rounded-xl border border-line bg-surface">
              <table className="w-full text-sm">
                <thead className="border-b border-line text-left text-xs uppercase text-ink-3">
                  <tr>
                    <th className="px-4 py-2">Map</th>
                    <th className="px-4 py-2 text-right">Played</th>
                    <th className="px-4 py-2 text-right">Won</th>
                    <th className="px-4 py-2 text-right">Lost</th>
                    <th className="px-4 py-2 text-right">Win %</th>
                    <th className="px-4 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {map_record.map((m) => (
                    <tr key={m.map} className="border-b border-line-soft last:border-0">
                      <td className="px-4 py-2">{m.map}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{m.played}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{m.won}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{m.lost}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{m.pct !== null ? `${m.pct}%` : '—'}</td>
                      <td className="px-4 py-2">
                        <div className="h-1.5 min-w-16 overflow-hidden rounded-full bg-raised">
                          <div className="h-full bg-good" style={{ width: `${m.pct ?? 0}%` }} />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-ink-3">
              Parsed maps only, and only those the parser could attribute to this team — a map is counted
              once per match it was played in.
            </p>
          </>
        ) : (
          <p className="text-sm text-ink-3">No parsed maps yet.</p>
        )}
      </section>

      {players.length > 0 && (
        <section className="space-y-2">
          <h2 className="font-medium text-ink">Players seen</h2>
          <div className="flex flex-wrap gap-2">
            {players.map((p) => (
              <Link
                key={p.steamid}
                to={`/players/${p.steamid}`}
                className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm text-ink hover:border-ct"
              >
                {p.name}
                <span className="ml-2 font-mono text-xs text-ink-3">
                  {plural(p.maps, 'map')} · {p.rounds} rd
                </span>
              </Link>
            ))}
          </div>
          <p className="text-xs text-ink-3">
            Whoever appeared on a parsed map under this team, most recently seen first — stand-ins included,
            which the map count is what distinguishes.
          </p>
        </section>
      )}
    </div>
  )
}

function ResultRow({ row }: { row: TeamResult }) {
  return (
    <tr className="border-b border-line-soft last:border-0">
      <td className="px-4 py-2 whitespace-nowrap">
        {row.n_parsed ? (
          <Link to={`/matches/${row.match_id}`} title="Round-by-round replay" className="text-ct hover:underline">
            {day(row.played_at)}
          </Link>
        ) : (
          <span className="text-ink-3">{day(row.played_at)}</span>
        )}
      </td>
      <td className="px-4 py-2">
        {row.opponent ? (
          <Link to={`/teams/${row.opponent.id}`} className="font-medium text-ct hover:underline">
            {row.opponent.name}
          </Link>
        ) : (
          <span className="text-ink-3">unknown</span>
        )}
      </td>
      <td className="px-4 py-2 text-right font-semibold tabular-nums">
        {row.outcome ? (
          <span className={OUTCOME[row.outcome]}>{row.ours}–{row.theirs}</span>
        ) : (
          <span className="text-ink-3">{row.score || '—'}</span>
        )}
      </td>
      <td className="px-4 py-2">
        {row.maps.length ? (
          <div className="flex flex-wrap gap-1">
            {row.maps.map((m) => {
              const tone = m.won ? 'border-good/50 text-good' : m.won === false ? 'border-crit/50 text-crit' : 'border-line text-ink-2'
              const label = `${m.name} ${m.score}`
              return m.parsed ? (
                <Link
                  key={m.number}
                  to={`/matches/${row.match_id}/m/${m.number}`}
                  title={`Replay this map round by round${m.attributed ? '' : ' — teams unresolved, raw scoreline'}`}
                  className={`rounded border px-1.5 font-mono text-[11px] whitespace-nowrap hover:bg-surface-2 ${tone}`}
                >
                  {label}
                </Link>
              ) : (
                <span key={m.number} title="not parsed" className="rounded border border-dashed border-line px-1.5 font-mono text-[11px] whitespace-nowrap text-ink-3">
                  {label}
                </span>
              )
            })}
          </div>
        ) : (
          <span className="text-ink-3">—</span>
        )}
      </td>
      <td className="px-4 py-2 text-ink-2">{row.tournament || '—'}</td>
      <td className="px-4 py-2">
        <span title={row.demo.why} className={`rounded-full border px-2 py-0.5 text-xs font-medium ${PILL[row.demo.cls] ?? PILL.queued}`}>
          {row.demo.word}
        </span>
      </td>
    </tr>
  )
}

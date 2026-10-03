import { Link, Navigate, NavLink, useParams, useSearchParams } from 'react-router'
import { $api } from '../api/client'
import type { components } from '../api/schema'
import Replay from '../replay/Replay'

type MatchInfo = components['schemas']['MatchInfo']

/** `/matches/:id` lands on the first replayable map; `/matches/:id/m/:n` is that map. */
export default function MatchPage() {
  const { matchId = '', mapNumber } = useParams()
  const id = Number(matchId)
  const match = $api.useQuery('get', '/matches/{match_id}', { params: { path: { match_id: id } } })

  if (match.error) return <p className="text-crit">Тоглолт олдсонгүй.</p>
  if (!match.data) return <p className="text-ink-3">Уншиж байна…</p>
  const info = match.data
  if (mapNumber === undefined && info.default_map !== null) {
    return <Navigate to={`/matches/${id}/m/${info.default_map}`} replace />
  }

  return (
    <div className="space-y-6">
      <Header info={info} />
      <MapTabs info={info} />
      {mapNumber === undefined ? (
        <p className="rounded-xl border border-line bg-surface p-6 text-ink-2">
          None of this match's maps has been parsed, so there is nothing to replay. Run an analysis that
          includes match {info.hltv_id} first.
        </p>
      ) : (
        <MapSection matchId={id} mapNumber={Number(mapNumber)} />
      )}
    </div>
  )
}

function Header({ info }: { info: MatchInfo }) {
  return (
    <div className="space-y-1">
      <p className="font-mono text-xs text-ink-3">
        {info.team1 && <Link to={`/teams/${info.team1.id}`} className="hover:underline">{info.team1.name}</Link>}
        {info.team1 && info.team2 && ' / '}
        {info.team2 && <Link to={`/teams/${info.team2.id}`} className="hover:underline">{info.team2.name}</Link>}
      </p>
      <h1 className="text-2xl font-semibold text-ink">
        {info.team1?.name ?? '?'} <span className="font-mono">{info.score || '–'}</span> {info.team2?.name ?? '?'}
      </h1>
      <p className="font-mono text-xs text-ink-3">
        {info.tournament || 'unknown event'} ·{' '}
        {info.played_at
          ? new Date(info.played_at).toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
          : 'date unknown'}{' '}
        ·{' '}
        <a href={info.hltv_url} target="_blank" rel="noreferrer" className="text-ct hover:underline">HLTV</a>
      </p>
    </div>
  )
}

function MapTabs({ info }: { info: MatchInfo }) {
  return (
    <div className="flex flex-wrap gap-1 border-b border-line">
      {info.maps.map((m) => {
        const inner = (
          <>
            {m.label}
            <span className="ml-2 font-mono text-xs text-ink-3">{m.scoreline}</span>
          </>
        )
        return m.playable ? (
          <NavLink
            key={m.map_number}
            to={`/matches/${info.id}/m/${m.map_number}`}
            className={({ isActive }) =>
              `rounded-t-md border border-b-0 px-4 py-2 text-sm ${isActive ? 'border-line bg-surface text-ink' : 'border-transparent text-ink-2 hover:bg-surface'}`
            }
          >
            {inner}
          </NavLink>
        ) : (
          <span key={m.map_number} title="Not parsed — nothing to replay" className="px-4 py-2 text-sm text-ink-3">
            {inner}
          </span>
        )
      })}
    </div>
  )
}

function MapSection({ matchId, mapNumber }: { matchId: number; mapNumber: number }) {
  const detail = $api.useQuery('get', '/matches/{match_id}/maps/{map_number}', {
    params: { path: { match_id: matchId, map_number: mapNumber } },
  })
  const startRound = Number(useSearchParams()[0].get('round')) || undefined
  if (detail.error) return <p className="text-crit">Энэ тоглолтод {mapNumber}-р мап байхгүй.</p>
  if (!detail.data) return <p className="text-ink-3">Replay бэлтгэж байна…</p>
  const { label, scene, rounds, scoreboard, parsed } = detail.data

  return (
    <div className="space-y-8">
      {scene ? (
        <section className="space-y-2">
          <h2 className="font-medium text-ink">Round replay — {label}</h2>
          <Replay
            key={`${matchId}-${mapNumber}`}
            matchId={matchId}
            mapNumber={mapNumber}
            scene={scene}
            rounds={rounds}
            startRound={startRound}
          />
        </section>
      ) : (
        <p className="rounded-xl border border-line bg-surface p-6 text-ink-2">
          {parsed
            ? <>{label} is parsed, but has no stored tick data to replay — run a scout that includes this match to parse it again.</>
            : <>{label} has not been parsed, so there is nothing to replay.</>}
        </p>
      )}

      {scoreboard.length > 0 && (
        <section className="space-y-2">
          <h2 className="font-medium text-ink">Scoreboard — {label}</h2>
          <div className="grid gap-4 lg:grid-cols-2">
            {scoreboard.map((side) => (
              <div key={side.team.id} className="rounded-xl border border-line bg-surface p-4">
                <h3 className="mb-2 flex items-baseline gap-3">
                  <Link to={`/teams/${side.team.id}`} className="font-medium text-ct hover:underline">{side.team.name}</Link>
                  <span className={`font-mono text-xl ${side.won ? 'text-good' : 'text-ink-2'}`}>{side.score ?? '–'}</span>
                </h3>
                <table className="w-full text-sm">
                  <thead className="text-left text-xs uppercase text-ink-3">
                    <tr>
                      <th className="py-1">Player</th>
                      <th className="py-1 text-right">K</th>
                      <th className="py-1 text-right">D</th>
                      <th className="py-1 text-right">+/–</th>
                      <th className="py-1 text-right">ADR</th>
                      <th className="py-1 text-right">KAST</th>
                      <th className="py-1 text-right">HS%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {side.players.length === 0 && (
                      <tr><td colSpan={7} className="py-1 text-ink-3">No stat rows for this side.</td></tr>
                    )}
                    {side.players.map((p) => (
                      <tr key={p.name} className="border-t border-line-soft tabular-nums">
                        <td className="py-1">{p.name}</td>
                        <td className="py-1 text-right">{p.kills}</td>
                        <td className="py-1 text-right">{p.deaths}</td>
                        <td className="py-1 text-right">{p.kd_diff > 0 ? `+${p.kd_diff}` : p.kd_diff}</td>
                        <td className="py-1 text-right">{p.adr !== null ? p.adr.toFixed(1) : '—'}</td>
                        <td className="py-1 text-right">{p.kast_pct ? `${Math.round(p.kast_pct)}%` : '—'}</td>
                        <td className="py-1 text-right">{p.hs_pct ? `${Math.round(p.hs_pct)}%` : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        </section>
      )}

      {rounds.length > 0 && (
        <section className="space-y-2">
          <h2 className="font-medium text-ink">Rounds</h2>
          <div className="overflow-x-auto rounded-xl border border-line bg-surface">
            <table className="w-full text-sm">
              <thead className="border-b border-line text-left text-xs uppercase text-ink-3">
                <tr>
                  <th className="px-4 py-2 text-right">#</th>
                  <th className="px-4 py-2">Won by</th>
                  <th className="px-4 py-2">Side</th>
                  <th className="px-4 py-2">How</th>
                  <th className="px-4 py-2">Bomb</th>
                  <th className="px-4 py-2 text-right">Score</th>
                </tr>
              </thead>
              <tbody>
                {rounds.map((r) => (
                  <tr key={r.number} className={`border-b border-line-soft last:border-0 ${r.half_break ? 'border-t-2 border-t-line' : ''}`}>
                    <td className="px-4 py-1.5 text-right tabular-nums">{r.number}</td>
                    <td className="px-4 py-1.5">{r.winner || '—'}</td>
                    <td className="px-4 py-1.5">{r.winner_side.toUpperCase() || '—'}</td>
                    <td className="px-4 py-1.5">{r.reason || '—'}</td>
                    <td className="px-4 py-1.5">{r.planted ? `planted ${r.site || '?'}` : '—'}</td>
                    <td className="px-4 py-1.5 text-right tabular-nums">{r.score}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  )
}

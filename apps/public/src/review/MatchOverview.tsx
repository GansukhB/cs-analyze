import { Link, useNavigate } from 'react-router'
import { $api } from '../api/client'
import type { components } from '../api/schema'
import { KIND_ORDER, KIND_TONE, swingText, TEAM_DOT } from './format'
import { TeamSummaryCard } from './Summary'

type MatchSummary = components['schemas']['MatchReviewSummary']
type MatchPlayer = components['schemas']['MatchReviewSummaryPlayer']

/**
 * The Match's «Тойм» tab: a card per Map (score, and each Team's main strength
 * and problem there), then both Teams' Summaries of the whole Match side by
 * side: Focus points, what repeated across Maps, and the Players' Swing.
 */
export default function MatchOverview({ matchId }: { matchId: number }) {
  const query = $api.useQuery('get', '/matches/{match_id}/summary', { params: { path: { match_id: matchId } } }, {
    staleTime: 5 * 60_000,
    retry: false,
  })
  if (query.isError) {
    return <p className="rounded-xl border border-line bg-surface p-4 text-sm text-ink-3">Тоглолтын тоймыг гаргаж чадсангүй.</p>
  }
  if (!query.data) return <p className="text-sm text-ink-3">Тойм бэлтгэж байна… (map бүрийн дүн шинжилгээг уншиж байна)</p>
  return <Body matchId={matchId} data={query.data} />
}

function Body({ matchId, data }: { matchId: number; data: MatchSummary }) {
  const navigate = useNavigate()
  const labels = Object.fromEntries(data.maps.map((m) => [m.map_number, m.label]))
  const index = (id: number | null | undefined) => Math.max(0, data.teams.findIndex((t) => t.id === id))
  const name = (id: number | null | undefined) => data.teams.find((t) => t.id === id)?.name ?? '?'
  const mapsWon = (id: number | null) => data.maps.filter((m) => m.winner_team_id === id).length
  const reviewed = data.maps.some((m) => m.reviewed)

  return (
    <div className="space-y-6">
      <section className="space-y-2">
        <h2 className="font-medium text-ink">Map-ууд</h2>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {data.maps.map((m) => (
            <Link
              key={m.map_number}
              to={`/matches/${matchId}/m/${m.map_number}`}
              className="group flex flex-col gap-2 rounded-xl border border-line bg-surface p-3 hover:border-ink-3"
            >
              <div className="flex items-baseline gap-2">
                <span className="font-mono text-xs text-ink-3">#{m.map_number}</span>
                <span className="font-medium text-ink">{m.label}</span>
                <span className="ml-auto font-mono text-lg tabular-nums text-ink">{m.scoreline}</span>
              </div>
              {m.winner_team_id !== null && (
                <p className="flex items-center gap-1.5 text-sm text-ink-2">
                  <span className={`size-2 rounded-full ${TEAM_DOT[index(m.winner_team_id)]}`} />
                  {name(m.winner_team_id)} авсан
                </p>
              )}
              {m.reviewed ? (
                <ul className="space-y-1 text-xs">
                  {m.teams.map((t) => (
                    <li key={t.team_id ?? 'x'} className="flex flex-col gap-0.5">
                      <span className="flex items-center gap-1.5 text-ink-3">
                        <span className={`size-1.5 rounded-full ${TEAM_DOT[index(t.team_id)]}`} />
                        {name(t.team_id)}
                      </span>
                      {t.strength && <span className="truncate pl-3 text-good" title={t.strength.text}>+ {t.strength.label}</span>}
                      {t.problem && <span className="truncate pl-3 text-crit" title={t.problem.text}>− {t.problem.label}</span>}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-ink-3">Tick дата байхгүй — зөвхөн оноо.</p>
              )}
              <span className="mt-auto text-xs text-ink-3 group-hover:text-ink">Map-ийн тойм, Replay →</span>
            </Link>
          ))}
        </div>
      </section>

      {reviewed ? (
        <section className="space-y-2">
          <h2 className="font-medium text-ink">Багуудын тойм</h2>
          <div className={`grid gap-4 ${data.summaries.length > 1 ? 'lg:grid-cols-2' : ''}`}>
            {data.summaries.map((s) => (
              <div key={s.team_id ?? 'x'} className="flex min-w-0 flex-col gap-4">
                <TeamSummaryCard
                  name={name(s.team_id)}
                  teamIndex={index(s.team_id)}
                  score={`${mapsWon(s.team_id)} map`}
                  numbers={[
                    { key: 'maps', label: 'Map (дүн шинжилсэн)', value: String(s.maps_played), tone: '' },
                    { key: 'won', label: 'Раунд', value: `${s.won}–${s.rounds - s.won}`, tone: '' },
                  ]}
                  focus={s.focus}
                  strengths={s.strengths}
                  problems={s.problems}
                  mapLabels={labels}
                  onRef={(r) => navigate(`/matches/${matchId}/m/${r.map_number}?round=${r.round}`)}
                  empty={s.maps_played < 2 ? 'Нэг л map-д дүн шинжилгээ байгаа тул map дамнасан давтамж алга; map-ийн табаас дэлгэрэнгүйг харна уу.' : undefined}
                />
                <Players rows={s.players} />
              </div>
            ))}
          </div>
        </section>
      ) : (
        <p className="rounded-xl border border-line bg-surface p-4 text-sm text-ink-2">
          Энэ тоглолтын нэг ч map tick датагүй тул тойм гаргах боломжгүй. Тоглолтыг агуулсан scout ажиллуулбал map-ууд дахин parse хийгдэнэ.
        </p>
      )}
    </div>
  )
}

function Players({ rows }: { rows: MatchPlayer[] }) {
  if (!rows.length) return null
  const scale = Math.max(0.5, ...rows.map((p) => Math.abs(p.swing)))
  return (
    <div className="rounded-xl border border-line bg-surface p-3">
      <h4 className="mb-1.5 text-xs text-ink-3 uppercase">Тоглогчид · match-ийн Swing</h4>
      <table className="w-full text-sm">
        <tbody>
          {rows.map((p) => {
            const share = Math.min(1, Math.abs(p.swing) / scale) * 50
            return (
              <tr key={p.sid} className="border-t-1 border-line-soft first:border-t-0">
                <td className="max-w-32 truncate py-1 pr-2 text-ink">{p.name}</td>
                <td className="w-full py-1">
                  <div className="relative h-1.5 rounded-full bg-line-soft">
                    <span className="absolute inset-y-0 left-1/2 w-px bg-line" />
                    <span
                      className={`absolute inset-y-0 rounded-full ${p.swing >= 0 ? 'bg-good' : 'bg-crit'}`}
                      style={p.swing >= 0 ? { left: '50%', width: `${share}%` } : { right: '50%', width: `${share}%` }}
                    />
                  </div>
                </td>
                <td className="py-1 pl-2 text-right font-mono text-xs whitespace-nowrap text-ink">
                  {p.swing > 0 ? '+' : p.swing < 0 ? '−' : ''}
                  {Math.abs(p.swing).toFixed(2)}
                </td>
                <td className="py-1 pl-2 text-right font-mono text-xs whitespace-nowrap text-ink-3">{swingText(p.swing_per_round)}/р</td>
                <td className="py-1 pl-3">
                  <span className="flex gap-2 text-[11px] text-ink-3">
                    {KIND_ORDER.map((k) =>
                      p.counts[k] ? (
                        <span key={k} className="flex items-center gap-1">
                          <span className={`size-1.5 rounded-full ${KIND_TONE[k].bar}`} />
                          {p.counts[k]}
                        </span>
                      ) : null,
                    )}
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

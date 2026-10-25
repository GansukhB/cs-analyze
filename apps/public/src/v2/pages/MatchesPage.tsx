// The my team's Matches, newest first: each Map opens its report (v2 screen 03).
import { Link, useSearchParams } from 'react-router'
import { $api } from '../../api/client'
import { LoadError } from '../../ui/LoadError'
import { PageSkeleton } from '../../ui/Skeleton'
import { CRIT, GOOD, MUTED, shortDate } from '../format'
import { at, useTeam } from '../team'
import { Empty, PageHead, Panel, Toggle } from '../ui'

export default function MatchesPage() {
  const team = useTeam()
  const [params, setParams] = useSearchParams()
  const scrims = params.get('scrims') === '1'
  const q = $api.useQuery('get', '/v2/teams/{team_id}/matches', {
    params: { path: { team_id: team.id }, query: { scrims } },
  })
  if (q.error) return <LoadError error={q.error} what="Тоглолтууд" retry={() => void q.refetch()} />
  if (!q.data) return <PageSkeleton />
  return (
    <>
      <PageHead
        label="Тоглолтын тайлан"
        title={`${team.name} · тоглолтууд`}
        sub="Газрын зургаа сонгоход тайлан нь нээгдэнэ"
        actions={
          <Toggle
            label="Тоглолтын төрөл"
            options={[
              ['official', 'Албан'],
              ['all', 'Албан + Scrim'],
            ]}
            value={scrims ? 'all' : 'official'}
            onChange={(k) => setParams(k === 'all' ? { scrims: '1' } : {}, { replace: true })}
          />
        }
      />
      <Panel>
        {q.data.matches.length === 0 ? (
          <Empty>Тоглолт алга.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="grid-table">
              <thead>
                <tr>
                  <th>Огноо</th>
                  <th>Өрсөлдөгч</th>
                  <th>Оноо</th>
                  <th>Төрөл</th>
                  <th>Тэмцээн</th>
                  <th>Газрын зураг</th>
                </tr>
              </thead>
              <tbody>
                {q.data.matches.map((m) => {
                  const won = m.ours != null && m.theirs != null ? m.ours > m.theirs : null
                  return (
                    <tr key={m.match_id}>
                      <td className="num text-ink-3">{shortDate(m.played_at)}</td>
                      <td className="font-semibold">{m.opponent}</td>
                      <td className="num font-semibold" style={{ color: won == null ? MUTED : won ? GOOD : CRIT }}>
                        {m.ours != null ? `${m.ours}–${m.theirs}` : '—'}
                      </td>
                      <td className="text-ink-3">{m.kind === 'scrim' ? 'Scrim' : 'Албан'}</td>
                      <td className="max-w-64 truncate text-ink-3">{m.tournament}</td>
                      <td>
                        <div className="flex flex-wrap gap-2">
                          {m.maps.map((mm) =>
                            mm.parsed ? (
                              <Link
                                key={mm.map_number}
                                to={at(team.id, 'matches', m.match_id, 'm', mm.map_number)}
                                className="plain rounded border border-line-strong px-2 py-1 text-[13px] !text-ink hover:border-accent"
                              >
                                {mm.label} <span className="num text-ink-3">{mm.score}</span>
                              </Link>
                            ) : (
                              <span key={mm.map_number} className="px-2 py-1 text-[13px] text-ink-3">
                                {mm.label} {mm.score}
                              </span>
                            ),
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  )
}

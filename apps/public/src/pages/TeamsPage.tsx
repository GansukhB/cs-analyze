import { Link } from 'react-router'
import { $api } from '../api/client'
import Count from '../components/Count'
import { day } from '../jobs/format'

export default function TeamsPage() {
  const list = $api.useQuery('get', '/teams')
  if (!list.data) return <p className="text-ink-3">Уншиж байна…</p>
  const { teams, parsed_teams, total_matches } = list.data

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold text-ink">Teams</h1>
        <p className="max-w-2xl text-ink-2">
          Every team the database has seen — as a fetched side, or as the opponent named on somebody
          else's results row. Parsed maps are what the rest of the app reads, so a team with none has a
          results table and nothing more.
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <Count n={teams.length} label="teams" />
        <Count n={parsed_teams} label="with parsed maps" />
        <Count n={total_matches} label="matches stored" />
      </div>

      {teams.length === 0 ? (
        <p className="text-sm text-ink-3">No teams yet. Run an analysis first.</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-line bg-surface">
          <table className="w-full text-sm">
            <thead className="border-b border-line text-left text-xs uppercase text-ink-3">
              <tr>
                <th className="px-4 py-2">Team</th>
                <th className="px-4 py-2 text-right">Matches</th>
                <th className="px-4 py-2 text-right">Parsed maps</th>
                <th className="px-4 py-2">Last match</th>
                <th className="px-4 py-2">HLTV</th>
              </tr>
            </thead>
            <tbody>
              {teams.map((team) => (
                <tr key={team.id} className="border-b border-line-soft last:border-0">
                  <td className="px-4 py-2">
                    <Link to={`/teams/${team.id}`} className="font-medium text-ct hover:underline">
                      {team.name}
                    </Link>
                    {!team.identified && (
                      <span
                        title="No HLTV id: seen only as an opponent's name"
                        className="ml-2 rounded border border-line px-1.5 font-mono text-[10px] uppercase tracking-wide text-ink-3"
                      >
                        name only
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">{team.matches}</td>
                  <td className={`px-4 py-2 text-right tabular-nums ${team.maps ? '' : 'text-ink-3'}`}>
                    {team.maps}
                  </td>
                  <td className="px-4 py-2 text-ink-2">{day(team.last)}</td>
                  <td className="px-4 py-2">
                    {team.hltv_url ? (
                      <a href={team.hltv_url} target="_blank" rel="noreferrer" className="text-ct hover:underline">
                        {team.hltv_id}
                      </a>
                    ) : (
                      <span className="text-ink-3">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

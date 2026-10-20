// A my team's Scrim log (docs/plans/07 RV-6): every Scrim it uploaded, newest
// first, its Maps, and the Focus points its Summary names. Scrims are our own
// development only: no Pool, habit or Rating reads them (docs/adr/0010).
import { useState } from 'react'
import { Link } from 'react-router'
import { $api } from '../api/client'
import { useMyTeams } from '../auth/useMe'
import { day } from '../jobs/format'

export default function ScrimsPage() {
  const myTeams = useMyTeams()
  const [teamId, setTeamId] = useState<number | null>(null)
  const chosen = teamId ?? myTeams[0]?.id ?? null
  const log = $api.useQuery(
    'get',
    '/scrims',
    { params: { query: { team_id: chosen ?? undefined } } },
    { enabled: chosen !== null },
  )
  if (!myTeams.length) return <p className="text-ink-3">Энэ Workspace-д my team алга.</p>
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-4">
        <h1 className="text-2xl font-semibold text-ink">Scrim</h1>
        {myTeams.length > 1 && (
          <select
            value={chosen ?? ''}
            onChange={(e) => setTeamId(Number(e.target.value))}
            className="rounded-md border border-line bg-surface-2 px-2 py-1 text-sm text-ink"
          >
            {myTeams.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        )}
        <Link to="/uploads" className="ml-auto text-sm text-ct hover:underline">
          Scrim upload хийх →
        </Link>
      </div>
      {!log.data ? (
        <p className="text-ink-3">{log.isError ? 'Уншиж чадсангүй.' : 'Уншиж байна…'}</p>
      ) : log.data.scrims.length === 0 ? (
        <p className="text-sm text-ink-3">Scrim алга.</p>
      ) : (
        <ul className="space-y-3">
          {log.data.scrims.map((s) => (
            <li key={s.match_id} className="space-y-2 rounded-xl border border-line bg-surface p-4 text-sm">
              <div className="flex flex-wrap items-baseline gap-x-4">
                <Link to={`/matches/${s.match_id}`} className="font-medium text-ct hover:underline">
                  {log.data.team.name} vs {s.partner || '?'}
                </Link>
                <span className="text-ink-3">{day(s.played_at)}</span>
                <span className="flex gap-2">
                  {s.maps.map((m) => (
                    <span key={m.map_number} className={m.won === true ? 'text-good' : m.won === false ? 'text-crit' : 'text-ink-3'}>
                      {m.label} {m.scoreline}
                    </span>
                  ))}
                </span>
              </div>
              {s.focus.length > 0 && (
                <div>
                  <p className="text-xs uppercase tracking-wide text-ink-3">Засах</p>
                  <ul className="list-disc pl-5 text-ink-2">
                    {s.focus.map((f, i) => (
                      <li key={i}>
                        {f.text}
                        {f.advice && <span className="text-ink-3"> → {f.advice}</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {s.strengths.length > 0 && (
                <div>
                  <p className="text-xs uppercase tracking-wide text-ink-3">Сайн</p>
                  <ul className="list-disc pl-5 text-ink-2">
                    {s.strengths.map((f, i) => (
                      <li key={i}>{f.text}</li>
                    ))}
                  </ul>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

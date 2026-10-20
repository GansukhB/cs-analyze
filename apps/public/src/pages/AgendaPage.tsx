// A Review meeting's agenda (docs/plans/07 RV-10): the Match's Summary in the
// order a 45-60 minute session runs, every claim with the Rounds to show. Prints.
import { Link, useParams, useSearchParams } from 'react-router'
import { $api } from '../api/client'

export default function AgendaPage() {
  const { matchId = '' } = useParams()
  const [params] = useSearchParams()
  const id = Number(matchId)
  const team = params.get('team')
  const agenda = $api.useQuery('get', '/matches/{match_id}/agenda', {
    params: { path: { match_id: id }, query: team ? { team_id: Number(team) } : {} },
  })
  if (agenda.isError) return <p className="text-ink-2">Agenda гаргаж чадсангүй.</p>
  if (!agenda.data) return <p className="text-ink-3">Уншиж байна…</p>
  const a = agenda.data
  const ref = (r: { map_number: number; round?: number | null }) =>
    `/matches/${id}/m/${r.map_number}${r.round ? `?round=${r.round}` : ''}`
  // With several Maps a Round needs its Map's number to be found.
  const maps = new Set(a.sections.flatMap((s) => s.items.flatMap((i) => i.refs.map((r) => r.map_number))))
  const label = (r: { map_number: number; round?: number | null }) =>
    `${maps.size > 1 ? `M${r.map_number} ` : ''}R${r.round}`
  return (
    <article className="space-y-6">
      <header className="space-y-1">
        <p className="font-mono text-xs text-ink-3">
          <Link to={`/matches/${id}`} className="hover:underline">
            {a.team} vs {a.opponent}
          </Link>{' '}
          / Agenda
        </p>
        <h1 className="text-2xl font-semibold text-ink">Review хуралдаан · ~{a.minutes} минут</h1>
        <button type="button" onClick={() => window.print()} className="text-sm text-ct underline print:hidden">
          Хэвлэх
        </button>
      </header>
      {a.sections.map((s, n) => (
        <section key={s.key} className="space-y-2 break-inside-avoid">
          <h2 className="flex items-baseline gap-3 border-b border-line pb-1 font-medium text-ink">
            <span className="font-mono text-ink-3">{n + 1}.</span> {s.title}
            <span className="ml-auto font-mono text-xs text-ink-3">{s.minutes} мин</span>
          </h2>
          {s.key === 'players' ? (
            <ul className="space-y-2 text-sm">
              {a.players.map((p) => (
                <li key={p.player}>
                  <b className="text-ink">{p.player}</b>{' '}
                  <span className="font-mono text-xs text-ink-3">Swing {p.swing > 0 ? '+' : ''}{p.swing.toFixed(2)}</span>
                  <ul className="list-disc pl-5 text-ink-2">
                    {p.lines.map((l, i) => (
                      <li key={i}>
                        {l.text}{' '}
                        {l.refs.map((r, j) => (
                          <Link key={j} to={ref(r)} className="font-mono text-xs text-ct print:hidden">
                            {label(r)}
                          </Link>
                        ))}
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          ) : s.items.length ? (
            <ul className="list-disc space-y-1 pl-5 text-sm text-ink-2">
              {s.items.map((i, k) => (
                <li key={k}>
                  {i.text}
                  {i.advice && <span className="text-ink"> → {i.advice}</span>}{' '}
                  {i.refs.map((r, j) => (
                    <Link key={j} to={ref(r)} className="font-mono text-xs text-ct print:hidden">
                      {' '}
                      {label(r)}
                    </Link>
                  ))}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-ink-3">Хэлэх зүйл алга.</p>
          )}
        </section>
      ))}
    </article>
  )
}

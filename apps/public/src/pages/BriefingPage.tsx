// One Briefing as the Players read it (docs/plans/01 WS-5): Staff's notes, the
// Forecast if Staff put it in, and each Map's lines as frozen, with Replay links.
// Prints cleanly (the nav, footer and Assistant hide under print).
import { Link, useNavigate, useParams } from 'react-router'
import { $api } from '../api/client'
import Check from '../briefing/Check'
import { useMe } from '../auth/useMe'
import { day } from '../jobs/format'

interface Ref {
  match: number
  map: number
  round: number
}
interface Item {
  kind: string
  section: string
  title: string
  lines: string[]
  counter: string
  refs: Ref[]
}
interface MapPart {
  map: string
  label: string
  note: string
  items: Item[]
  // SB-6: the my team's Strats for this Map (since Briefings made after it).
  strats?: { id: number; name: string; side: string; kind: string }[]
}
interface Series {
  format: string
  pct: number
  word: string
  often: string
  trust: string
}
interface Content {
  note: string
  lineups: { mine: string[]; theirs: string[] }
  maps: MapPart[]
  forecast?: { series: Series[]; limits: string[] }
}

const KIND: Record<string, { label: string; tone: string }> = {
  lever: { label: 'Ашиглах', tone: 'text-good' },
  caution: { label: 'Анхаарах', tone: 'text-warn' },
  plan: { label: 'Төлөвлөгөө', tone: 'text-ct' },
  habit: { label: 'Тэдний зуршил', tone: 'text-ink-2' },
  pistol: { label: 'Pistol', tone: 'text-ink-2' },
  player: { label: 'Тоглогч', tone: 'text-ink-2' },
}

export default function BriefingPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const staff = useMe().data?.role === 'staff'
  const b = $api.useQuery('get', '/briefings/{public_id}', { params: { path: { public_id: id } } })
  const share = $api.useMutation('post', '/briefings/{public_id}/share', { onSuccess: () => b.refetch() })
  const remove = $api.useMutation('delete', '/briefings/{public_id}', { onSuccess: () => navigate('/briefings') })
  if (b.isError) return <p className="text-ink-2">Ийм Briefing алга.</p>
  if (!b.data) return <p className="text-ink-3">Уншиж байна…</p>
  const c = b.data.content as unknown as Content

  return (
    <article className="space-y-6">
      <header className="space-y-1">
        <p className="font-mono text-xs text-ink-3">
          {b.data.my_team.name} vs {b.data.opponent.name} · {day(b.data.created_at)}
          {b.data.created_by ? ` · ${b.data.created_by}` : ''}
          {b.data.shared_at ? ' · хуваалцсан' : ' · ноорог'}
        </p>
        <h1 className="text-2xl font-semibold text-ink">{b.data.title}</h1>
        <p className="text-sm text-ink-3">
          Манай 5: {c.lineups.mine.join(', ') || '—'} · Тэдний 5: {c.lineups.theirs.join(', ') || '—'}
        </p>
      </header>
      {staff && (
        <div className="flex gap-3 text-sm print:hidden">
          {!b.data.shared_at && (
            <button
              type="button"
              onClick={() => share.mutate({ params: { path: { public_id: id } } })}
              className="rounded-md bg-ct px-3 py-1.5 font-medium text-ground hover:brightness-110"
            >
              Тоглогчдод хуваалцах
            </button>
          )}
          <button type="button" onClick={() => window.print()} className="rounded-md border border-line px-3 py-1.5 text-ink">
            Хэвлэх
          </button>
          <button
            type="button"
            onClick={() => remove.mutate({ params: { path: { public_id: id } } })}
            className="ml-auto text-ink-3 underline hover:text-ink"
          >
            Устгах
          </button>
        </div>
      )}
      {c.note && <p className="whitespace-pre-line rounded-md border-l-2 border-ct bg-surface px-4 py-3 text-ink">{c.note}</p>}
      {c.forecast && c.forecast.series.length > 0 && (
        <section className="space-y-2">
          <h2 className="font-medium text-ink">Forecast</h2>
          <div className="flex flex-wrap gap-3">
            {c.forecast.series.map((s) => (
              <div key={s.format} className="rounded-md border border-line bg-surface px-4 py-2">
                <b className="block font-mono text-xl text-ink">~{s.pct}%</b>
                <span className="text-xs text-ink-2">
                  {s.format} · {s.word}
                </span>
              </div>
            ))}
          </div>
          {c.forecast.series[1]?.trust && <p className="text-xs text-ink-3">{c.forecast.series[1].trust}</p>}
        </section>
      )}
      {c.maps.map((m) => (
        <section key={m.map} className="space-y-3 break-inside-avoid">
          <h2 className="border-b border-line pb-1 text-lg font-semibold text-ink">{m.label}</h2>
          {m.note && <p className="whitespace-pre-line text-ink">{m.note}</p>}
          {m.strats && m.strats.length > 0 && (
            <p className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
              <span className="text-ink-3">Stratbook:</span>
              {m.strats.map((s) => (
                <Link key={s.id} to={`/stratbook/${s.id}`} className="text-ct hover:underline">
                  {s.name} <span className="text-xs text-ink-3">{s.side.toUpperCase()}</span>
                </Link>
              ))}
            </p>
          )}
          <ul className="space-y-2">
            {m.items.map((item, i) => {
              const k = KIND[item.kind] ?? { label: item.kind, tone: 'text-ink-2' }
              return (
                <li key={i} className="rounded-md border border-line bg-surface px-4 py-3 text-sm">
                  <p className="text-xs">
                    <span className={k.tone}>{k.label}</span>
                    {item.section && <span className="text-ink-3"> · {item.section}</span>}
                  </p>
                  <p className="mt-0.5 font-medium text-ink">{item.title}</p>
                  {item.lines.map((l, j) => (
                    <p key={j} className="text-ink-2">
                      {l}
                    </p>
                  ))}
                  {item.counter && <p className="mt-1 text-ink">→ {item.counter}</p>}
                  {item.refs.length > 0 && (
                    <p className="mt-1 flex flex-wrap gap-2 text-xs print:hidden">
                      {item.refs.map((r, j) => (
                        <Link
                          key={j}
                          to={`/matches/${r.match}/m/${r.map}?round=${r.round}`}
                          className="text-ct hover:underline"
                        >
                          R{r.round}
                        </Link>
                      ))}
                    </p>
                  )}
                </li>
              )
            })}
          </ul>
        </section>
      ))}
      {staff && <Check id={id} />}
    </article>
  )
}

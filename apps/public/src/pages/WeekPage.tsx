// The week's practice (docs/plans/07 RV-11): the research's tier-2 week, each
// day filled from what the Workspace already has. Nothing here is stored.
import { Link } from 'react-router'
import { $api } from '../api/client'
import { day } from '../jobs/format'
import { PageSkeleton } from '../ui/Skeleton'
import { LoadError } from '../ui/LoadError'

const VERDICT: Record<string, [string, string]> = {
  reached: ['хүрсэн', 'text-good'],
  close: ['ойрхон', 'text-warn'],
  not_yet: ['хараахан', 'text-crit'],
  no_data: ['дата алга', 'text-ink-3'],
}

export default function WeekPage() {
  const q = $api.useQuery('get', '/workspace/week')
  if (q.isError) return <LoadError error={q.error} what="Долоо хоног" retry={() => void q.refetch()} />
  if (!q.data) return <PageSkeleton />
  const w = q.data
  if (!w.team) return <p className="text-ink-3">Workspace-д манай баг тохируулаагүй байна.</p>
  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold text-ink">{w.team.name}: долоо хоногийн бэлтгэл</h1>
        <p className="max-w-3xl text-sm text-ink-2">
          Tier-2 багийн долоо хоногийн загвар, байгаа датаар дүүргэсэн: Review хийх тоглолт, Development зорилго, сүүлийн
          Scrim-үүдийн Focus point (энэ долоо хоногийн Scrim-ийн зорилго), дараагийн өрсөлдөгчийн бэлтгэл.
        </p>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {w.days.map((d) => (
          <section key={d.day} className="space-y-2 rounded-xl border border-line bg-surface p-3">
            <h2 className="font-medium text-ink">
              {d.day} <span className="text-xs font-normal text-ink-3">· {d.theme}</span>
            </h2>
            {d.blocks.includes('review') && (
              <Block title="Review">
                {w.review.map((r) => (
                  <li key={r.match_id}>
                    <Link to={`/matches/${r.match_id}/agenda`} className="text-ct hover:underline">
                      {r.opponent} {r.score}
                    </Link>{' '}
                    <span className="text-xs text-ink-3">{day(r.played_at)}</span>
                  </li>
                ))}
              </Block>
            )}
            {d.blocks.includes('goals') && (
              <Block title="Development зорилго">
                {w.goals.map((g, i) => {
                  const [word, tone] = VERDICT[g.verdict] ?? [g.verdict, 'text-ink-3']
                  return (
                    <li key={i}>
                      <Link to={`/players/${g.steamid}`} className="text-ink hover:underline">
                        {g.player}
                      </Link>{' '}
                      {g.kpi} → {g.target} <span className={`text-xs ${tone}`}>{word}</span>{' '}
                      <span className="text-xs text-ink-3">{g.due_on}</span>
                    </li>
                  )
                })}
              </Block>
            )}
            {d.blocks.includes('scrims') && (
              <Block title="Scrim-ийн зорилго">
                {w.scrims.flatMap((s) =>
                  s.focus.map((f, i) => (
                    <li key={`${s.match_id}-${i}`}>
                      {f}{' '}
                      <Link to={`/matches/${s.match_id}`} className="text-xs text-ct hover:underline">
                        {s.partner}
                      </Link>
                    </li>
                  )),
                )}
              </Block>
            )}
            {d.blocks.includes('prep') && (
              <Block title="Өрсөлдөгчийн бэлтгэл">
                {w.prep.map((p) => (
                  <li key={p.briefing}>
                    {p.opponent}:{' '}
                    <Link to={`/gameplan/${p.mine}/vs/${p.theirs}`} className="text-ct hover:underline">
                      Game Plan
                    </Link>{' '}
                    ·{' '}
                    <Link to={`/gameplan/${p.mine}/vs/${p.theirs}/veto`} className="text-ct hover:underline">
                      veto
                    </Link>{' '}
                    ·{' '}
                    <Link to={`/briefings/${p.briefing}`} className="text-ct hover:underline">
                      Briefing
                    </Link>
                  </li>
                ))}
              </Block>
            )}
            {d.blocks.length === 0 && <p className="text-sm text-ink-3">—</p>}
          </section>
        ))}
      </div>
    </div>
  )
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  const items = Array.isArray(children) ? children.flat() : [children]
  return (
    <div className="space-y-1">
      <p className="text-xs tracking-wide text-ink-3 uppercase">{title}</p>
      {items.filter(Boolean).length ? (
        <ul className="space-y-1 text-sm text-ink-2">{children}</ul>
      ) : (
        <p className="text-xs text-ink-3">Одоогоор алга.</p>
      )}
    </div>
  )
}

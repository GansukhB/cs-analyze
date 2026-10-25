// After the Match (docs/plans/06 GP-8): each habit the Briefing named against
// the opponent's Rounds, the Maps played against the Maps briefed, and the
// Forecast against the result. Staff only.
import { Link } from 'react-router'
import { $api } from '../api/client'
import { usePaths } from '../paths'

const pct = (v: number | null | undefined) => (v == null ? '—' : `${v}%`)

export default function Check({ id }: { id: string }) {
  const paths = usePaths()
  const check = $api.useQuery('get', '/briefings/{public_id}/check', { params: { path: { public_id: id } } })
  if (!check.data) return null
  const c = check.data
  if (c.match_id == null) {
    return (
      <section className="rounded-xl border border-line bg-surface p-4 text-sm text-ink-3">
        Тоглолтын дараах шалгалт: энэ Briefing-ээс хойш хоёр багийн тоглолт parse хийгдээгүй байна.
      </section>
    )
  }
  const t = c.totals
  const judged = t.judged ?? 0
  return (
    <section className="space-y-3 rounded-xl border border-line bg-surface p-4 text-sm">
      <h2 className="font-medium text-ink">
        Тоглолтын дараах шалгалт ·{' '}
        <Link to={paths.match(c.match_id)} className="text-ct hover:underline">
          тоглолт
        </Link>
      </h2>
      <ul className="space-y-1 text-ink-2">
        <li>
          Таамагласан habit: <b className="text-ink">{t.showed ?? 0}</b>/{judged} гарсан
          {(t.unchecked ?? 0) > 0 && <span className="text-ink-3"> ({t.unchecked} мөрийг шалгах боломжгүй)</span>}
          {(t.hit_rounds ?? 0) > 0 && (
            <>
              ; гарсан раундуудын <b className="text-ink">{t.won_rounds ?? 0}</b>/{t.hit_rounds}-д манай баг хожсон
            </>
          )}
          .
        </li>
        {c.veto && (
          <li>
            Map: бэлтгэсэн {c.veto.briefed.length}-ээс {c.veto.hit} нь тоглогдсон (тоглогдсон {c.veto.played.length}).
          </li>
        )}
        {c.forecast && c.forecast.p != null && (
          <li>
            Forecast: {c.forecast.format} {Math.round(c.forecast.p * 100)}% байсан;{' '}
            {c.forecast.won ? 'хожсон' : 'хожигдсон'} (Brier {c.forecast.brier}).
          </li>
        )}
      </ul>
      {c.maps.map((m) => (
        <div key={m.map} className="space-y-1">
          <p className="text-xs uppercase tracking-wide text-ink-3">
            {m.label}
            {!m.played && ' · тоглогдоогүй'}
          </p>
          <ul className="space-y-1">
            {m.lines.map((l, i) => {
              const r = l.result
              const tone = !r || !r.judged ? 'text-ink-3' : r.showed ? 'text-good' : 'text-crit'
              return (
                <li key={i} className="flex flex-wrap items-baseline gap-x-2">
                  <span className={`font-mono text-xs ${tone}`}>
                    {!r || !r.judged ? '—' : r.showed ? '✓ гарсан' : '✗ гараагүй'}
                  </span>
                  <span className="text-ink">{l.title}</span>
                  {r && r.judged && (
                    <span className="text-xs text-ink-3">
                      {r.hits}/{r.chances} раунд ({pct(r.rate)}, өмнө {pct(r.rate_before)})
                      {r.median != null && ` · дундаж ${r.median}с`}
                      {r.hits > 0 && ` · манай хожил ${r.won}/${r.hits}`}
                    </span>
                  )}
                  {r?.refs.slice(0, 4).map((ref) => (
                    <Link
                      key={`${ref.map}-${ref.round}`}
                      to={paths.match(ref.match, ref.map, ref.round)}
                      className="font-mono text-xs text-ct"
                    >
                      R{ref.round}
                    </Link>
                  ))}
                </li>
              )
            })}
          </ul>
        </div>
      ))}
    </section>
  )
}

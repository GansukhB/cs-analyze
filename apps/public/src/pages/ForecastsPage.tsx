// Every Forecast the Workspace kept, graded once its series was played, and how
// they did against a coin (docs/plans/03 FC-4): the reason to trust the next one,
// or not.
import { Link } from 'react-router'
import { $api } from '../api/client'
import Count from '../components/Count'
import { day } from '../jobs/format'

const pct5 = (p: number) => `~${Math.round(p * 20) * 5}%`
const fixed = (v: number | null | undefined, n = 3) => (v === null || v === undefined ? '—' : v.toFixed(n))

export default function ForecastsPage() {
  const list = $api.useQuery('get', '/forecasts')
  if (list.isError) return <p className="text-crit">Forecast-уудыг уншиж чадсангүй.</p>
  if (!list.data) return <p className="text-ink-3">Уншиж байна…</p>
  const { items, summary } = list.data
  const better = summary.log_loss !== null && summary.log_loss < summary.coin_log_loss

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold text-ink">Forecast</h1>
        <p className="max-w-2xl text-ink-2">
          Game plan-аас хадгалсан Forecast бүр өөрчлөгдөхгүй. Цуврал тоглогдсоны дараа үр дүнтэйгээ тулгагдана.
          Log loss бага байх тусам сайн: зоос (50/50) {summary.coin_log_loss.toFixed(3)} авна.
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <Count n={summary.made} label="хадгалсан" />
        <Count n={summary.graded} label="дүгнэгдсэн" />
        <Count n={fixed(summary.log_loss)} label={better ? 'log loss · зооснаас сайн' : 'log loss'} />
        <Count n={fixed(summary.brier)} label="Brier" />
        {summary.favourites_won !== null && (
          <Count n={`${summary.favourites_won}/${summary.graded}`} label="favourite хожсон" />
        )}
        {summary.maps > 0 && <Count n={fixed(summary.map_log_loss)} label={`Map-ын log loss · ${summary.maps}`} />}
      </div>
      {summary.graded > 0 && summary.graded < 30 && (
        <p className="max-w-2xl text-sm text-ink-3">
          {summary.graded} дүгнэгдсэн Forecast цөөхөн: эдгээр тоо азаас их хамаарна. Model-ийн шалгалт (2026 оны 12,644
          цуврал) rating_params.json-д байна.
        </p>
      )}

      {items.length === 0 ? (
        <p className="text-sm text-ink-3">
          Forecast алга. <Link to="/gameplan" className="text-ct hover:underline">Game plan</Link>-ийн «Шийдвэр» tab-аас
          хадгална.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-line bg-surface">
          <table className="w-full text-sm">
            <thead className="border-b border-line text-left text-xs uppercase text-ink-3">
              <tr>
                <th className="px-4 py-2">Хадгалсан</th>
                <th className="px-4 py-2">Тоглолт</th>
                <th className="px-4 py-2">Формат</th>
                <th className="px-4 py-2 text-right">Бидний хожих</th>
                <th className="px-4 py-2">Үр дүн</th>
                <th className="px-4 py-2 text-right">Log loss</th>
              </tr>
            </thead>
            <tbody>
              {items.map((f) => {
                const result = f.result as { won?: boolean; score?: string; expired?: boolean } | null
                return (
                  <tr key={f.id} className="border-b border-line-soft last:border-0">
                    <td className="px-4 py-2 whitespace-nowrap text-ink-3">{day(f.created_at)}</td>
                    <td className="px-4 py-2">
                      <Link
                        to={`/gameplan/${f.my_team.id}/vs/${f.opponent.id}`}
                        className="font-medium text-ct hover:underline"
                      >
                        {f.my_team.name} vs {f.opponent.name}
                      </Link>
                    </td>
                    <td className="px-4 py-2 uppercase">{f.format}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{pct5(f.p_series)}</td>
                    <td className="px-4 py-2">
                      {result?.expired ? (
                        <span className="text-ink-3">тоглогдсонгүй</span>
                      ) : result ? (
                        <span className={result.won ? 'text-good' : 'text-crit'}>
                          {result.won ? 'хожсон' : 'ялагдсан'}
                          {result.score ? ` ${result.score}` : ''}
                        </span>
                      ) : (
                        <span className="text-ink-3">хүлээгдэж байна</span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-right font-mono tabular-nums">{fixed(f.log_loss)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// A Match Map's timeout audit and opening duels (docs/plans/07 RV-8): each
// timeout with the run it broke and the Round after against what the buys gave,
// the runs of three that went without one, and every Player's first duels.
import { $api } from '../api/client'
import type { Goto } from './MapReview'

const pct = (v: number | null | undefined) => (v == null ? '—' : `${Math.round(v)}%`)

export default function Audit({ matchId, mapNumber, onGoto }: { matchId: number; mapNumber: number; onGoto: Goto }) {
  const audit = $api.useQuery('get', '/matches/{match_id}/maps/{map_number}/audit', {
    params: { path: { match_id: matchId, map_number: mapNumber } },
  })
  if (!audit.data) return null
  const { known, timeouts, missed, openings, pool } = audit.data
  const round = (n: number) => (
    <button type="button" onClick={() => onGoto(n, 0, null)} className="font-mono text-ct hover:underline">
      R{n}
    </button>
  )
  return (
    <section className="grid gap-6 min-[1100px]:grid-cols-2">
      <div className="space-y-2">
        <h2 className="font-medium text-ink">Timeout</h2>
        {!known ? (
          <p className="text-sm text-ink-3">Энэ map-ийн tick дата timeout-ыг агуулаагүй (schema 14-өөс өмнө parse хийгдсэн).</p>
        ) : (
          <>
            {timeouts.length === 0 && missed.length === 0 && <p className="text-sm text-ink-3">Timeout аваагүй.</p>}
            <ul className="flex flex-col space-y-1 text-sm text-ink-2">
              {timeouts.map((t) => (
                <li key={`${t.round}-${t.team_id}`} style={{ order: t.round }}>
                  {round(t.round)} <b className="text-ink">{t.team}</b> ({t.side.toUpperCase()}) timeout —{' '}
                  {t.lost_before ? `${t.lost_before} раунд дараалан алдсаны дараа` : 'дараалсан алдагдалгүй үед'}; дараагийн раунд{' '}
                  <span className={t.won_next ? 'text-good' : 'text-crit'}>{t.won_next ? 'хожсон' : 'алдсан'}</span>
                  {t.expected != null && <span className="text-ink-3"> (buy-аар {pct(t.expected * 100)} байсан)</span>}
                </li>
              ))}
              {missed.map((m) => (
                <li key={`m-${m.round}-${m.team_id}`} className="text-ink-2" style={{ order: m.round }}>
                  {round(m.round)} <span className="text-warn">!</span> <b className="text-ink">{m.team}</b> {m.lost_before} раунд дараалан
                  алдсан ч timeout аваагүй ({m.left} үлдсэн); дараагийн раунд{' '}
                  <span className={m.won_next ? 'text-good' : 'text-crit'}>{m.won_next ? 'хожсон' : 'алдсан'}</span>
                </li>
              ))}
            </ul>
          </>
        )}
        {pool.maps > 0 && (
          <p className="text-xs text-ink-3">
            {pool.maps} map-д: 3+ дараалан алдсаны дараах раундыг timeout авсан баг {pct(pool.after_timeout.pct)} ({pool.after_timeout.won}/
            {pool.after_timeout.rounds}), аваагүй баг {pct(pool.without.pct)} ({pool.without.won}/{pool.without.rounds}) хожсон.
            Судалгаагаар завсарлага дараагийн раундыг 11.7–13 нэгжээр өсгөдөг (Gómez Seeber 2024).
          </p>
        )}
      </div>
      <div className="space-y-2">
        <h2 className="font-medium text-ink">Opening duel</h2>
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-ink-3">
            <tr>
              <th className="py-1 font-normal">Тоглогч</th>
              <th className="py-1 text-right font-normal">Оролдлого</th>
              <th className="py-1 text-right font-normal">Хожсон</th>
              <th className="py-1 text-right font-normal" title="Эхний үхлийнх нь trade хийгдсэн хувь">Trade</th>
              <th className="py-1 text-right font-normal" title="Эхний kill-ийн дараа баг раундыг хожсон (5v4)">5v4 хожил</th>
              <th className="py-1 text-right font-normal" title="Эхний үхлийн дараа баг раундыг хожсон (4v5)">4v5 хожил</th>
            </tr>
          </thead>
          <tbody className="text-ink-2">
            {openings.map((o) => (
              <tr key={o.sid} className="border-t-1 border-line">
                <td className="py-1 text-ink">
                  {o.name} <span className="text-xs text-ink-3">{o.team}</span>
                </td>
                <td className="py-1 text-right font-mono">{o.attempts}</td>
                <td className="py-1 text-right font-mono">
                  {o.won} · {pct(o.won_pct)}
                </td>
                <td className="py-1 text-right font-mono">{pct(o.traded_pct)}</td>
                <td className="py-1 text-right font-mono">{pct(o.after_kill_won_pct)}</td>
                <td className="py-1 text-right font-mono">{pct(o.after_death_won_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

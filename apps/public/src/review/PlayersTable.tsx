import { Link } from 'react-router'
import type { components } from '../api/schema'
import { KIND_ORDER, KIND_TONE, swingText, TEAM_DOT } from './format'
import type { Goto } from './MapReview'

type Review = components['schemas']['Review']
type Player = components['schemas']['ReviewPlayer']
type ScoreboardSide = components['schemas']['ScoreboardSide']

/**
 * Each Team's Players in one table: the scoreboard's numbers next to their
 * Swing over the Map and the Findings about them. A row picks the Player as the
 * page's filter.
 */
export default function PlayersTable(props: {
  scoreboard: ScoreboardSide[]
  review: Review | null
  team: number | null
  player: string | null
  onPlayer: (sid: string | null) => void
}) {
  const { scoreboard, review, team, player, onPlayer } = props
  const players = review?.players ?? []
  const byName = new Map(players.map((p) => [p.name.toLowerCase(), p]))
  const scale = Math.max(0.5, ...players.map((p) => Math.abs(p.swing)))
  const sides = scoreboard.filter((s) => team === null || s.team.id === team)
  const dot = (id: number) => TEAM_DOT[review?.teams.findIndex((t) => t.id === id) ?? 0] ?? 'bg-ink-3'

  return (
    <div className={`grid gap-4 ${sides.length > 1 ? '2xl:grid-cols-2' : ''}`}>
      {sides.map((side) => {
        // Review rows nobody on the scoreboard matched still get a row.
        const named = new Set(side.players.map((p) => p.name.toLowerCase()))
        const extra = players.filter((p) => p.team_id === side.team.id && !named.has(p.name.toLowerCase()))
        return (
          <div key={side.team.id} className="overflow-x-auto rounded-xl border border-line bg-surface p-3">
            <h3 className="mb-2 flex items-baseline gap-2">
              <span className={`size-2 self-center rounded-full ${dot(side.team.id)}`} />
              <Link to={`/teams/${side.team.id}`} className="font-medium text-ink hover:underline">
                {side.team.name}
              </Link>
              <span className={`font-mono text-lg ${side.won ? 'text-good' : 'text-ink-2'}`}>{side.score ?? '–'}</span>
            </h3>
            <table className="w-full min-w-[560px] text-sm">
              <thead className="text-left text-[11px] text-ink-3 uppercase">
                <tr>
                  <th className="py-1 font-normal">Тоглогч</th>
                  <th className="py-1 text-right font-normal">K</th>
                  <th className="py-1 text-right font-normal">D</th>
                  <th className="py-1 text-right font-normal">±</th>
                  <th className="py-1 text-right font-normal">ADR</th>
                  <th className="py-1 text-right font-normal">KAST</th>
                  <th className="py-1 text-right font-normal">HS%</th>
                  {review && <th className="w-36 py-1 pl-4 font-normal" title="Map дээрх нийт Swing, раундаар">Swing</th>}
                  {review && <th className="py-1 text-right font-normal">/раунд</th>}
                  {review && <th className="py-1 pl-3 font-normal">Дүгнэлт</th>}
                </tr>
              </thead>
              <tbody>
                {side.players.map((s) => {
                  const p = byName.get(s.name.toLowerCase()) ?? null
                  return (
                    <Row key={s.name} name={s.name} p={p} scale={scale} active={!!p && player === p.sid} onPick={onPlayer} review={!!review}>
                      <td className="py-1 text-right">{s.kills}</td>
                      <td className="py-1 text-right">{s.deaths}</td>
                      <td className={`py-1 text-right ${s.kd_diff > 0 ? 'text-good' : s.kd_diff < 0 ? 'text-crit' : ''}`}>
                        {s.kd_diff > 0 ? `+${s.kd_diff}` : s.kd_diff}
                      </td>
                      <td className="py-1 text-right">{s.adr !== null ? s.adr.toFixed(1) : '—'}</td>
                      <td className="py-1 text-right">{s.kast_pct ? `${Math.round(s.kast_pct)}%` : '—'}</td>
                      <td className="py-1 text-right">{s.hs_pct ? `${Math.round(s.hs_pct)}%` : '—'}</td>
                    </Row>
                  )
                })}
                {extra.map((p) => (
                  <Row key={p.sid} name={p.name} p={p} scale={scale} active={player === p.sid} onPick={onPlayer} review>
                    <td colSpan={6} className="py-1 text-right text-ink-3">—</td>
                  </Row>
                ))}
              </tbody>
            </table>
          </div>
        )
      })}
    </div>
  )
}

function Row(props: {
  name: string
  p: Player | null
  scale: number
  active: boolean
  onPick: (sid: string | null) => void
  review: boolean
  children: React.ReactNode
}) {
  const { name, p, scale, active, onPick, review, children } = props
  const share = p ? Math.min(1, Math.abs(p.swing) / scale) * 50 : 0
  return (
    <tr
      onClick={p ? () => onPick(active ? null : p.sid) : undefined}
      className={`border-t-1 border-line-soft tabular-nums ${p ? 'cursor-pointer hover:bg-surface-2' : ''} ${active ? 'bg-raised' : ''}`}
    >
      <td className="max-w-36 truncate py-1 pr-2 text-ink">{name}</td>
      {children}
      {review && (
        <td className="py-1 pl-4">
          {p && (
            <div className="flex items-center gap-2">
              {/* Diverging from zero: right is Rounds won for the team, left is Rounds cost. */}
              <div className="relative h-1.5 flex-1 rounded-full bg-line-soft">
                <span className="absolute inset-y-0 left-1/2 w-px bg-line" />
                <span
                  className={`absolute inset-y-0 rounded-full ${p.swing >= 0 ? 'bg-good' : 'bg-crit'}`}
                  style={p.swing >= 0 ? { left: '50%', width: `${share}%` } : { right: '50%', width: `${share}%` }}
                />
              </div>
              <span className="w-11 text-right font-mono text-xs text-ink">
                {p.swing > 0 ? '+' : p.swing < 0 ? '−' : ''}
                {Math.abs(p.swing).toFixed(2)}
              </span>
            </div>
          )}
        </td>
      )}
      {review && <td className="py-1 text-right font-mono text-xs text-ink-2">{p ? swingText(p.swing_per_round) : ''}</td>}
      {review && (
        <td className="py-1 pl-3">
          {p && (
            <span className="flex gap-2 text-[11px] text-ink-3">
              {KIND_ORDER.map((k) =>
                p.counts[k] ? (
                  <span key={k} className="flex items-center gap-1" title={k}>
                    <span className={`size-1.5 rounded-full ${KIND_TONE[k].bar}`} />
                    {p.counts[k]}
                  </span>
                ) : null,
              )}
            </span>
          )}
        </td>
      )}
    </tr>
  )
}

const UTILITY_LABEL: [string, string, (v: number) => string][] = [
  ['flashes', 'flash шидсэн', (v) => String(v)],
  ['enemies_blinded', 'дайсан цайруулсан (≥1с)', (v) => String(v)],
  ['blind_seconds', 'дайсны цайрсан секунд', (v) => v.toFixed(1)],
  ['flash_kills', 'flash → kill', (v) => String(v)],
  ['team_flashes', 'багаа цайруулсан', (v) => String(v)],
  ['he_damage', 'HE damage', (v) => String(Math.round(v))],
  ['fire_damage', 'молотовын damage', (v) => String(Math.round(v))],
]

/** The picked Player: their Swing, best and worst Round, and utility. */
export function PlayerFocus(props: {
  player: Player
  dot: string
  involved: boolean
  setInvolved: (v: boolean) => void
  onGoto: Goto
  onClose: () => void
}) {
  const { player: p, dot, involved, setInvolved, onGoto, onClose } = props
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-xl border border-line bg-surface px-4 py-3">
      <div className="flex items-baseline gap-2">
        <span className={`size-2.5 self-center rounded-full ${dot}`} />
        <h3 className="text-lg font-medium text-ink">{p.name}</h3>
        <span className="text-sm text-ink-3">{p.team}</span>
      </div>
      <dl className="flex flex-wrap gap-2 text-sm">
        <Stat label="Нийт Swing" value={`${p.swing >= 0 ? '+' : '−'}${Math.abs(p.swing).toFixed(2)} раунд`} />
        <Stat label="Раунд бүрт" value={swingText(p.swing_per_round)} />
        <button type="button" className="text-left" onClick={() => onGoto(p.best_round.n, 0, null, false)}>
          <Stat label="Хамгийн сайн" value={`R${p.best_round.n} · ${swingText(p.best_round.swing)}`} />
        </button>
        <button type="button" className="text-left" onClick={() => onGoto(p.worst_round.n, 0, null, false)}>
          <Stat label="Хамгийн муу" value={`R${p.worst_round.n} · ${swingText(p.worst_round.swing)}`} />
        </button>
      </dl>
      {Object.keys(p.utility).length > 0 && (
        <p className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-2">
          {UTILITY_LABEL.filter(([k]) => p.utility[k]).map(([k, label, fmt]) => (
            <span key={k}>
              <b className="font-mono text-ink">{fmt(p.utility[k])}</b> {label}
            </span>
          ))}
        </p>
      )}
      <div className="ml-auto flex items-center gap-1 text-xs" role="group" aria-label="Аль дүгнэлтүүд">
        {(
          [
            [false, 'Өөрийнх нь'],
            [true, 'Оролцсон бүгд'],
          ] as const
        ).map(([value, text]) => (
          <button
            key={String(value)}
            type="button"
            aria-pressed={involved === value}
            onClick={() => setInvolved(value)}
            className={`rounded-full border px-2.5 py-0.5 ${involved === value ? 'border-ink-3 bg-raised text-ink' : 'border-line-soft text-ink-3 hover:text-ink'}`}
          >
            {text}
          </button>
        ))}
        <button type="button" onClick={onClose} className="ml-2 text-sm text-ink-3 hover:text-ink">
          ✕
        </button>
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-surface-2 px-2 py-1">
      <dt className="text-[11px] text-ink-3">{label}</dt>
      <dd className="text-ink">{value}</dd>
    </div>
  )
}

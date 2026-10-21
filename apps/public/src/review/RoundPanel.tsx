import { useState } from 'react'
import type { components } from '../api/schema'
import type { Filters } from './filters'
import { BUY, clock, KIND_TONE, swingText, TEAM_DOT } from './format'
import type { Goto } from './MapReview'
import { FindingActions } from './Notes'
import WinChart from './WinChart'

type Review = components['schemas']['Review']
type Finding = components['schemas']['ReviewFinding']
type Round = components['schemas']['ReviewRound']
type RoundTeam = components['schemas']['RoundTeamSummary']
type Bullet = components['schemas']['RoundBullet']

/**
 * The Round beside the Replay: its Win probability, each Team's Summary of it,
 * then its Findings (or, switched, every Finding the filters leave). It follows
 * the Round on the Replay's canvas; the arrows step through the Rounds the
 * filters leave.
 */
export default function RoundPanel(props: {
  review: Review
  round: Round | null
  matching: Set<number>
  filters: Filters
  findings: Finding[]
  names: Record<string, string>
  teamIndex: Map<number | null, number>
  onGoto: Goto
  onPlayer: (sid: string) => void
  // The Replay's clock, for the Win probability's cursor (VIZ-6).
  now?: { round: number; t: number } | null
}) {
  const { review, round, matching, filters, findings, names, teamIndex, onGoto, onPlayer } = props
  const [scope, setScope] = useState<'round' | 'all'>('round')
  const teamName = (id: number | null | undefined) => review.teams.find((t) => t.id === id)?.name ?? ''
  const order = review.rounds.map((r) => r.n).filter((n) => matching.has(n))
  const step = (dir: 1 | -1) => {
    if (!round) return
    const next = dir > 0 ? order.find((n) => n > round.n) : [...order].reverse().find((n) => n < round.n)
    if (next !== undefined) onGoto(next, 0, null, false)
  }
  const here = round ? findings.filter((f) => f.round === round.n) : []
  const listed = scope === 'round' ? here : findings
  const teams = round
    ? round.teams.filter((t) => (filters.team === null || t.team_id === filters.team) && (filters.side === null || t.side === filters.side))
    : []

  return (
    <aside className="@container flex min-w-0 flex-col gap-3">
      {round ? (
        <div className="space-y-2 rounded-xl border border-line bg-surface p-3">
          <div className="flex items-center gap-2">
            <button type="button" onClick={() => step(-1)} aria-label="Өмнөх раунд" className="rounded-md border border-line px-2 py-0.5 text-ink-2 hover:text-ink">
              ◀
            </button>
            <h3 className="font-medium text-ink">Раунд {round.n}</h3>
            <button type="button" onClick={() => step(1)} aria-label="Дараагийн раунд" className="rounded-md border border-line px-2 py-0.5 text-ink-2 hover:text-ink">
              ▶
            </button>
            <span className="ml-auto font-mono text-xs text-ink-3">
              <span className="text-ct">CT</span> {BUY[round.ct_buy] || round.ct_buy || '—'} · <span className="text-t">T</span>{' '}
              {BUY[round.t_buy] || round.t_buy || '—'} · {clock(round.seconds)}
            </span>
          </div>
          {!matching.has(round.n) && <p className="text-xs text-warn">Энэ раунд шүүлтүүрт тохирохгүй — ◀ ▶ тохирох раундуудаар алхана.</p>}
          <p className="text-sm text-ink-2">{round.summary}</p>
          <WinChart
            round={round}
            names={names}
            ctTeam={teamName(round.ct_team_id)}
            tTeam={teamName(round.t_team_id)}
            onGoto={(t, sid) => onGoto(round.n, t, sid)}
            now={props.now?.round === round.n ? props.now.t : null}
          />
          <div className={`grid gap-2 ${teams.length > 1 ? '@xl:grid-cols-2' : ''}`}>
            {teams.map((t) => (
              <RoundTeamCard key={t.side} t={t} name={teamName(t.team_id)} dot={TEAM_DOT[teamIndex.get(t.team_id) ?? 0]} onGoto={onGoto} />
            ))}
          </div>
        </div>
      ) : (
        <p className="rounded-xl border border-line bg-surface p-3 text-sm text-ink-3">Раунд сонгоогүй байна.</p>
      )}

      <div className="space-y-2">
        <div className="flex items-center gap-1 text-xs" role="group" aria-label="Аль дүгнэлтүүд">
          {(
            [
              ['round', `Энэ раунд (${here.length})`],
              ['all', `Бүх раунд (${findings.length})`],
            ] as const
          ).map(([value, text]) => (
            <button
              key={value}
              type="button"
              aria-pressed={scope === value}
              onClick={() => setScope(value)}
              className={`rounded-full border px-2.5 py-0.5 ${scope === value ? 'border-ink-3 bg-raised text-ink' : 'border-line-soft text-ink-3 hover:text-ink'}`}
            >
              {text}
            </button>
          ))}
        </div>
        {scope === 'all'
          ? groupByRound(listed).map(([n, items]) => (
              <div key={n ?? 'map'} className="space-y-2">
                <h4 className="pt-1 font-mono text-xs text-ink-3 uppercase">{n === null ? 'Бүх map' : `Раунд ${n}`}</h4>
                {items.map((f) => (
                  <FindingCard key={f.id} f={f} names={names} onGoto={onGoto} onPlayer={onPlayer} active={filters.player} />
                ))}
              </div>
            ))
          : listed.map((f) => <FindingCard key={f.id} f={f} names={names} onGoto={onGoto} onPlayer={onPlayer} active={filters.player} />)}
        {listed.length === 0 && <p className="text-sm text-ink-3">Энэ шүүлтүүрт тохирох дүгнэлт алга.</p>}
      </div>
    </aside>
  )
}

/** A Team's Summary of one Round: one line, what went well and wrong, and a Focus point. */
function RoundTeamCard({ t, name, dot, onGoto }: { t: RoundTeam; name: string; dot: string; onGoto: Goto }) {
  const line = (b: Bullet, good: boolean) => (
    <li key={`${b.finding ?? 'fact'}-${b.t}`}>
      <button type="button" onClick={() => onGoto(b.round, b.t, b.sid)} className="flex w-full items-start gap-1.5 text-left hover:text-ink">
        <span className={`mt-[3px] font-mono text-xs ${good ? 'text-good' : 'text-crit'}`}>{good ? '+' : '−'}</span>
        <span className="min-w-0 flex-1">{b.text}</span>
        {Math.abs(b.swing) >= 0.005 && (
          <span className={`shrink-0 font-mono text-[11px] ${b.swing > 0 ? 'text-good' : 'text-crit'}`}>{swingText(b.swing)}</span>
        )}
      </button>
    </li>
  )
  return (
    <div className={`space-y-1.5 rounded-lg border bg-surface-2 p-2.5 ${t.won ? 'border-good/30' : 'border-line'}`}>
      <div className="flex items-center gap-1.5 text-sm">
        <span className={`size-2 rounded-full ${dot}`} />
        <span className="truncate font-medium text-ink">{name || t.side.toUpperCase()}</span>
        <span className={`ml-auto rounded px-1.5 text-[11px] ${t.won ? 'bg-good/15 text-good' : 'bg-crit/10 text-crit'}`}>{t.won ? 'хожсон' : 'алдсан'}</span>
      </div>
      <p className="text-xs text-ink-2">{t.line}</p>
      {(t.good.length > 0 || t.bad.length > 0) && (
        <ul className="space-y-0.5 text-xs text-ink-2">
          {t.good.map((b) => line(b, true))}
          {t.bad.map((b) => line(b, false))}
        </ul>
      )}
      {t.focus && (
        <button
          type="button"
          onClick={() => onGoto(t.focus!.round, t.focus!.t, t.focus!.sid)}
          className="block w-full rounded-md border border-warn/30 px-2 py-1 text-left text-xs text-ink"
        >
          <span className="text-warn">Анхаарах:</span> {t.focus.advice}
        </button>
      )}
    </div>
  )
}

function groupByRound(items: Finding[]): [number | null, Finding[]][] {
  const out = new Map<number | null, Finding[]>()
  for (const f of items) {
    const key = f.round ?? null
    if (!out.has(key)) out.set(key, [])
    out.get(key)!.push(f)
  }
  return [...out.entries()]
}

export function FindingCard(props: {
  f: Finding
  names: Record<string, string>
  onGoto: Goto
  onPlayer: (sid: string) => void
  active: string | null
}) {
  const { f, names, onGoto, onPlayer, active } = props
  const tone = KIND_TONE[f.kind] ?? KIND_TONE.utility
  return (
    <article className="flex gap-3 rounded-lg border border-line bg-surface p-3">
      <span className={`w-1 shrink-0 rounded-full ${tone.bar}`} aria-hidden />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className={`rounded border px-1.5 py-0.5 ${tone.chip}`}>{f.code_label}</span>
          {f.round !== null && (
            <span className="font-mono text-ink-3">
              R{f.round} · {clock(f.t)}
            </span>
          )}
          {f.sight && (
            <span className="text-ink-3" title="Sighting-ээс (хэн хэнийг харсан) гаргасан дүгнэлт">
              ★ sighting
            </span>
          )}
          {Math.abs(f.swing) >= 0.005 && (
            <span className={`ml-auto font-mono ${f.swing > 0 ? 'text-good' : 'text-crit'}`} title="Swing">
              {swingText(f.swing)}
            </span>
          )}
        </div>
        <h4 className="mt-1 font-medium text-ink">{f.title}</h4>
        <p className="text-sm text-ink-2">{f.text}</p>
        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
          {f.round !== null && (
            <button
              type="button"
              onClick={() => onGoto(f.round!, f.t ?? 0, f.sids[0] ?? null)}
              className="rounded-md border border-line bg-raised px-2 py-0.5 text-ink hover:border-ink-3"
            >
              ▶ Replay
            </button>
          )}
          {[...new Set(f.sids)].map((sid) => (
            <button
              key={sid}
              type="button"
              onClick={() => onPlayer(sid)}
              className={`rounded-md px-1.5 py-0.5 ${active === sid ? 'bg-raised text-ink' : 'text-ink-3 hover:text-ink'}`}
            >
              {names[sid] || '?'}
            </button>
          ))}
          <FindingActions f={f} />
        </div>
      </div>
    </article>
  )
}

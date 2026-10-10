import type { CSSProperties } from 'react'
import type { components } from '../api/schema'

type RoundStripRow = components['schemas']['RoundStripRow']
type Side = 'ct' | 't'
type How = 'elim' | 'exploded' | 'defused' | 'time'
export type TimelineTeam = { name: string; score: number | null }

const HOW: Record<How, string> = {
  elim: 'Elimination',
  exploded: 'Bomb exploded',
  defused: 'Bomb defused',
  time: 'Time ran out',
}

// `reason` is the stored end_reason with spaces: "ct killed", "t killed", "bomb exploded", …
function how(reason: string): How {
  if (reason.includes('exploded')) return 'exploded'
  if (reason.includes('defused')) return 'defused'
  if (reason.includes('time')) return 'time'
  return 'elim'
}

function Icon({ kind }: { kind: How }) {
  if (kind === 'exploded' || kind === 'defused') {
    // Valve's icons (white), tinted through a mask so they take the side's colour.
    const url = `url(/icons/equipment/${kind === 'exploded' ? 'planted_c4' : 'defuser'}.svg)`
    const style: CSSProperties = {
      backgroundColor: 'currentColor',
      maskImage: url,
      WebkitMaskImage: url,
      maskSize: 'contain',
      maskRepeat: 'no-repeat',
      maskPosition: 'center',
    }
    return <span aria-hidden className="block size-4" style={style} />
  }
  if (kind === 'time') {
    return (
      <svg aria-hidden viewBox="0 0 16 16" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
        <circle cx="8" cy="9" r="5.6" />
        <path d="M8 6v3.2l2 1.3M6.3 1.8h3.4M8 1.8v1.6" />
      </svg>
    )
  }
  return (
    <svg aria-hidden viewBox="0 0 16 16" className="size-4" fill="currentColor">
      <path
        fillRule="evenodd"
        d="M8 1.2C4.5 1.2 2 3.6 2 6.7c0 1.8.8 3.2 2 4.1V13c0 .5.4.9.9.9h.9v-1.3h1.1v1.3h2.2v-1.3h1.1v1.3h.9c.5 0 .9-.4.9-.9v-2.2c1.2-.9 2-2.3 2-4.1 0-3.1-2.5-5.5-6-5.5ZM5.6 9.4a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3Zm4.8 0a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3ZM8 9.6l.9 1.5H7.1L8 9.6Z"
      />
    </svg>
  )
}

const sideText: Record<Side, string> = { ct: 'text-ct', t: 'text-t' }
const sideBar: Record<Side, string> = { ct: 'bg-ct', t: 'bg-t' }
const other = (s: Side | null): Side | null => (s === null ? null : s === 'ct' ? 't' : 'ct')

/** Team1's side, round by round: known from any round with a winner, carried across the
 * rest of its half (sides only change on a half break). */
function team1Sides(rounds: RoundStripRow[]): (Side | null)[] {
  const sides: (Side | null)[] = []
  let current: Side | null = null
  for (const r of rounds) {
    if (r.half_break && current) current = other(current)
    if (r.winner && (r.winner_side === 'ct' || r.winner_side === 't')) {
      current = r.mine ? r.winner_side : other(r.winner_side)
    }
    sides.push(current)
  }
  // Rounds before the first known one take the first known side.
  const first = sides.find((s) => s !== null) ?? null
  for (let i = 0; i < sides.length && sides[i] === null; i++) sides[i] = first
  return sides
}

/**
 * The map's rounds as a horizontal strip, HLTV style: one row per team, the
 * winner's cell carries how the round ended, in the colour of the side that
 * team played. Under the Replay's radar (`replay`) it is the round picker:
 * player.ts reads `#rp-rounds .r[data-round]`, listens for their clicks and
 * marks the open one `on`.
 */
export default function RoundTimeline(props: {
  rounds: RoundStripRow[]
  team1: TimelineTeam
  team2: TimelineTeam
  replay?: boolean
  /** Rounds the page's filters leave out, drawn faint. */
  dim?: Set<number>
}) {
  const { rounds, team1, team2, replay = false, dim } = props
  const sides = team1Sides(rounds)

  const cell = (r: RoundStripRow, side: Side | null, won: boolean, top: boolean) => (
    <span
      className={`relative flex h-9 items-center justify-center overflow-hidden rounded-[3px] transition-[filter] ${
        won ? (side ? sideText[side] : 'text-ink') : 'bg-surface-2'
      } ${replay ? 'group-hover:brightness-150' : ''}`}
      style={won && side ? { backgroundColor: `color-mix(in srgb, var(--${side}) 16%, var(--surface-2))` } : undefined}
    >
      {side && (
        <span className={`absolute inset-x-0 ${top ? 'top-0' : 'bottom-0'} h-[3px] ${sideBar[side]} ${won ? '' : 'opacity-35'}`} />
      )}
      {won ? <Icon kind={how(r.reason)} /> : <span className="size-1 rounded-full bg-line" />}
    </span>
  )

  const name = (team: TimelineTeam) => (
    <span className="flex h-9 items-center justify-between gap-3">
      <span className="truncate text-sm text-ink" title={team.name}>{team.name}</span>
      <span className="font-mono text-sm tabular-nums text-ink-2">{team.score ?? ''}</span>
    </span>
  )

  return (
    <div className="space-y-3 rounded-md border border-line bg-surface p-3">
      <div className="flex overflow-x-auto pb-1">
        <div className="sticky left-0 z-10 flex w-28 shrink-0 flex-col gap-1 bg-surface pr-3 sm:w-36">
          {name(team1)}
          <span className="h-4" />
          {name(team2)}
        </div>
        <div id={replay ? 'rp-rounds' : undefined} className="flex min-w-0 flex-1 gap-[3px]">
          {rounds.map((r, i) => {
            const side = sides[i]
            const kind = how(r.reason)
            return [
              r.half_break ? <span key={`gap-${r.number}`} className="w-2 shrink-0" /> : null,
              <button
                key={r.number}
                type="button"
                tabIndex={replay ? undefined : -1}
                data-round={r.number}
                // An attribute, not a class: player.ts owns the class list (it marks `on`).
                data-dim={dim?.has(r.number) ? '' : undefined}
                title={`Round ${r.number} · ${r.score}\n${r.winner || '?'} (${r.winner_side.toUpperCase()}) — ${HOW[kind]}${r.planted ? `\nPlanted ${r.site || '?'}` : ''}`}
                className={`r group flex min-w-3.5 flex-1 flex-col gap-1 rounded-[4px] outline-none outline-offset-2 focus-visible:outline-1 focus-visible:outline-dashed focus-visible:outline-line [&.on]:outline-1 [&.on]:outline-solid [&.on]:outline-ink-3 data-[dim]:opacity-30 ${
                  replay ? '' : 'cursor-default'
                }`}
              >
                {cell(r, side, !!r.winner && r.mine, true)}
                <span className="h-4 text-center font-mono text-[10px] leading-4 tabular-nums text-ink-3 group-[.on]:font-semibold group-[.on]:text-ink">
                  {r.number}
                </span>
                {cell(r, other(side), !!r.winner && !r.mine, false)}
              </button>,
            ]
          })}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-ink-3">
        {(Object.keys(HOW) as How[]).map((k) => (
          <span key={k} className="flex items-center gap-1.5 text-ink-2">
            <Icon kind={k} />
            {HOW[k]}
          </span>
        ))}
        <span className="flex items-center gap-1.5">
          <span className="h-[3px] w-4 rounded bg-ct" /> CT
          <span className="ml-2.5 h-[3px] w-4 rounded bg-t" /> T
        </span>
      </div>
    </div>
  )
}

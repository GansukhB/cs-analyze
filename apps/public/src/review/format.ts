/** The Review's numbers as the page writes them. */

/** How long a clip of the Replay runs, in Round seconds (VIZ-13). */
export const CLIP_SECONDS = 10

/** Seconds from freeze end as the Replay's clock: 83.4 → '1:23'. */
export function clock(t: number | null | undefined): string {
  const s = Math.max(0, Math.floor(t ?? 0))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/** A Swing (a share of a Round) as signed percent: 0.274 → '+27%'. */
export function swingText(v: number | null | undefined): string {
  const points = Math.round((v ?? 0) * 100)
  if (points > 0) return `+${points}%`
  if (points < 0) return `−${Math.abs(points)}%`
  return '0%'
}

/** A per-Round average Swing, which is small, with one decimal: 0.0026 → '+0.3%'. */
export function swingRateText(v: number | null | undefined): string {
  const points = Math.round((v ?? 0) * 1000) / 10
  if (points > 0) return `+${points.toFixed(1)}%`
  if (points < 0) return `−${Math.abs(points).toFixed(1)}%`
  return '0.0%'
}

export const KIND_TONE: Record<string, { bar: string; text: string; chip: string }> = {
  key_play: { bar: 'bg-good', text: 'text-good', chip: 'border-good/40 text-good' },
  mistake: { bar: 'bg-crit', text: 'text-crit', chip: 'border-crit/40 text-crit' },
  missed_chance: { bar: 'bg-warn', text: 'text-warn', chip: 'border-warn/40 text-warn' },
  utility: { bar: 'bg-ink-3', text: 'text-ink-2', chip: 'border-line text-ink-2' },
}

export const KIND_ORDER = ['key_play', 'mistake', 'missed_chance', 'utility'] as const

/** A Summary line's weight, in Rounds won or cost: 1.37 → '≈ 1.4 раунд'. */
export function weightText(v: number, good: boolean): string {
  return `${good ? '+' : '−'}${v.toFixed(1)} раунд`
}

export const BUY: Record<string, string> = { pistol: 'pistol', eco: 'eco', force: 'force', full: 'full buy' }

/** The two Teams of a Match Map, told apart the same way everywhere on the page. */
export const TEAM_DOT = ['bg-mine', 'bg-theirs']
export const TEAM_TEXT = ['text-mine', 'text-theirs']

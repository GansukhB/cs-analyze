// The v2 pages' pure helpers: colours by threshold, numbers and dates as the
// design writes them, paths for the sparklines. Tested without a browser.

export const GOOD = 'var(--good)'
export const WARN = 'var(--warn)'
export const CRIT = 'var(--crit)'
export const T = 'var(--t)'
export const CT = 'var(--ct)'
export const THEM = 'var(--them)'
export const MUTED = 'var(--ink-3)'

/** Green from `good` up, amber from `ok`, red below: the design's three steps. */
export function tone(value: number | null | undefined, good: number, ok: number): string {
  if (value == null) return MUTED
  return value >= good ? GOOD : value >= ok ? WARN : CRIT
}

export function pct(value: number | null | undefined, digits = 0): string {
  return value == null ? '—' : `${value.toFixed(digits)}%`
}

export function signed(value: number | null | undefined, digits = 1): string {
  if (value == null) return ''
  const s = value.toFixed(digits)
  return value > 0 ? `+${s}` : value < 0 ? `−${s.slice(1)}` : `±${s}`
}

/** A sparkline path over `values` in a w×h box, between lo and hi. */
export function sparkPath(values: number[], w: number, h: number, lo: number, hi: number): string {
  if (values.length === 0) return ''
  const span = hi - lo || 1
  const step = values.length > 1 ? w / (values.length - 1) : 0
  return values
    .map((v, i) => `${i ? 'L' : 'M'}${(i * step).toFixed(1)} ${(h - ((v - lo) / span) * h).toFixed(1)}`)
    .join(' ')
}

export function mmss(seconds: number | null | undefined): string {
  if (seconds == null) return '—'
  const s = Math.max(0, Math.round(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return `${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')}`
}

const TZ = 'Asia/Ulaanbaatar'

export function when(iso: string): string {
  return new Date(iso).toLocaleString('mn-MN', {
    timeZone: TZ,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

/** "4 өдөр үлдсэн", "5 цаг үлдсэн", "эхэлсэн". */
export function countdown(iso: string, now = Date.now()): string {
  const ms = new Date(iso).getTime() - now
  if (ms <= 0) return 'эхэлсэн'
  const hours = Math.floor(ms / 3_600_000)
  if (hours >= 48) return `${Math.floor(hours / 24)} өдөр үлдсэн`
  if (hours >= 1) return `${hours} цаг үлдсэн`
  return `${Math.max(1, Math.floor(ms / 60_000))} минут үлдсэн`
}

export function insightValue(x: { kind: string; value: number }) {
  return x.kind === 'rate' ? `${Math.round(100 * x.value)}%` : `${x.value.toFixed(1)}/24`
}

export function ghostLink(refs: { match: number; map: number; round: number }[]) {
  return `/ghost?r=${refs.map((r) => `${r.match}.${r.map}.${r.round}`).join(',')}`
}

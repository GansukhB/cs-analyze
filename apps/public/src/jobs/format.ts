import type { components } from '../api/schema'

export type JobRow = components['schemas']['JobRow']
export type JobDetail = components['schemas']['JobDetail']
export type JobStatus = components['schemas']['JobStatusPayload']
export type JobEvent = components['schemas']['JobEvent']
export type StageRow = components['schemas']['StageRow']
export type MatchSummary = components['schemas']['MatchSummary']
export type JobResult = components['schemas']['JobResult']

// Job states as every page says them (Mongolian, like cstat's job page).
export const STATUS_MN: Record<string, string> = {
  queued: 'Дараалалд',
  running: 'Ажиллаж байна',
  success: 'Дууслаа',
  failed: 'Унасан',
  cancelled: 'Цуцлагдсан',
}

export const PILL: Record<string, string> = {
  queued: 'border-line text-ink-3',
  running: 'border-ct text-ct',
  success: 'border-good text-good',
  failed: 'border-crit text-crit',
  cancelled: 'border-line text-ink-3',
}

export function secs(s: number | null | undefined): string {
  if (s === null || s === undefined) return ''
  return s < 60
    ? `${Math.round(s)}с`
    : `${Math.floor(s / 60)}м ${String(Math.round(s % 60)).padStart(2, '0')}с`
}

export function tally(counts: Record<string, number> | undefined, words: Record<string, string>) {
  if (!counts) return ''
  return Object.entries(counts)
    .filter(([, n]) => n)
    .map(([key, n]) => `${n} ${words[key] ?? key}`)
    .join(', ')
}

export function when(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function day(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

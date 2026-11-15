// Stored answers (docs/adr/0014): every analytic page answers at once from what
// the worker computed ahead of time. After a parse a page may be answered from
// the last answer while the worker computes the new one: the response then says
// `X-Answer: stale`, the fetch middleware marks the body with `_answer`, and
// `watchStaleAnswers` fetches that query again until it is current.

export const ANSWER_KEY = '_answer'

export type AnswerMark = { state: 'stale'; at: string }

/** The mark the middleware put on a stale answer, else null (current). */
export function answerOf(data: unknown): AnswerMark | null {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return null
  const mark = (data as Record<string, unknown>)[ANSWER_KEY]
  if (!mark || typeof mark !== 'object') return null
  const { state, at } = mark as { state?: unknown; at?: unknown }
  return state === 'stale' && typeof at === 'string' ? { state, at } : null
}

/** A stale body, marked; anything else as it came. */
export function markStale(body: unknown, at: string): unknown {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return body
  return { ...(body as object), [ANSWER_KEY]: { state: 'stale', at } }
}

// The worker takes the wanted pages first: most are ready within half a minute,
// a Game Plan's heavier tabs within a few. Past MAX_WAIT_MS the page keeps what
// it shows (the worker may be busy with a parse) and the chip says so.
const DELAYS_MS = [8_000, 15_000, 25_000, 40_000, 60_000]
export const MAX_WAIT_MS = 30 * 60_000

/** How long to wait before asking again, after `attempt` stale answers in a row. */
export function refetchDelay(attempt: number): number {
  return DELAYS_MS[Math.min(Math.max(attempt, 0), DELAYS_MS.length - 1)]
}

/** "14:02" in Ulaanbaatar (UTC+8), where the Staff read the clock. */
export function clockUb(iso: string): string {
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return ''
  const d = new Date(t + 8 * 3600_000)
  return `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`
}

/** The oldest of the stale answers on screen, for the chip's line. */
export function oldest(marks: AnswerMark[]): string | null {
  let best: string | null = null
  for (const m of marks) if (best === null || Date.parse(m.at) < Date.parse(best)) best = m.at
  return best
}

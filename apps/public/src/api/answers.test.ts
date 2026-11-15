import { describe, expect, it } from 'vitest'
import { ANSWER_KEY, answerOf, clockUb, markStale, oldest, refetchDelay } from './answers'

describe('stored answers', () => {
  it('marks a stale body and reads the mark back', () => {
    const body = markStale({ tab: 'todo', data: { a: 1 } }, '2026-11-15T06:02:00Z')
    expect(answerOf(body)).toEqual({ state: 'stale', at: '2026-11-15T06:02:00Z' })
    expect((body as Record<string, unknown>).tab).toBe('todo')
  })

  it('leaves current answers, lists and nothing alone', () => {
    expect(answerOf({ tab: 'todo' })).toBeNull()
    expect(answerOf(null)).toBeNull()
    expect(markStale([1, 2], 'x')).toEqual([1, 2])
    expect(answerOf({ [ANSWER_KEY]: { state: 'fresh', at: 'x' } })).toBeNull()
  })

  it('asks again sooner first, then once a minute', () => {
    expect(refetchDelay(0)).toBe(8_000)
    expect(refetchDelay(2)).toBe(25_000)
    expect(refetchDelay(40)).toBe(60_000)
  })

  it("says the time on Ulaanbaatar's clock", () => {
    expect(clockUb('2026-11-15T06:02:00Z')).toBe('14:02')
    expect(clockUb('2026-11-15T18:30:00Z')).toBe('02:30')
    expect(clockUb('nope')).toBe('')
  })

  it('names the oldest answer on screen', () => {
    const at = ['2026-11-15T06:02:00Z', '2026-11-15T05:00:00Z', '2026-11-15T07:00:00Z']
    expect(oldest(at.map((a) => ({ state: 'stale' as const, at: a })))).toBe(at[1])
    expect(oldest([])).toBeNull()
  })
})

import { describe, expect, it } from 'vitest'
import { lineupQuery, lineupSearch, readLineups } from './lineup'

describe('Lineups in the URL', () => {
  it('keeps at most five Steam ids a side and drops anything else', () => {
    const l = readLineups(new URLSearchParams('mine=1,2,x,3,4,5,6&theirs='))
    expect(l).toEqual({ mine: ['1', '2', '3', '4', '5'], theirs: [] })
    expect(lineupSearch(l)).toBe('?mine=1,2,3,4,5')
    expect(lineupQuery(l)).toEqual({ my_lineup: '1,2,3,4,5' })
    expect(lineupSearch({ mine: [], theirs: [] })).toBe('')
  })
})

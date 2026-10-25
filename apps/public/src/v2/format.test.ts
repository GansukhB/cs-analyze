import { describe, expect, it } from 'vitest'
import { asV1 } from '../assistant/context'
import { countdown, signed, sparkPath, tone } from './format'

describe('v2 format', () => {
  it('colours by the design three steps', () => {
    expect(tone(61, 60, 50)).toBe('var(--good)')
    expect(tone(55, 60, 50)).toBe('var(--warn)')
    expect(tone(40, 60, 50)).toBe('var(--crit)')
    expect(tone(null, 60, 50)).toBe('var(--ink-3)')
  })
  it('signs a change with a real minus', () => {
    expect(signed(6)).toBe('+6.0')
    expect(signed(-3)).toBe('−3.0')
    expect(signed(0)).toBe('±0.0')
  })
  it('draws a sparkline across its box', () => {
    expect(sparkPath([0, 1], 100, 10, 0, 1)).toBe('M0.0 10.0 L100.0 0.0')
  })
  it('counts down in days, then hours', () => {
    const now = Date.parse('2026-10-25T00:00:00Z')
    expect(countdown('2026-10-29T00:00:00Z', now)).toBe('4 өдөр үлдсэн')
    expect(countdown('2026-10-25T05:00:00Z', now)).toBe('5 цаг үлдсэн')
    expect(countdown('2026-10-24T05:00:00Z', now)).toBe('эхэлсэн')
  })
})

describe('the Assistant on v2 pages', () => {
  it('reads each v2 page as the v1 page about the same subject', () => {
    expect(asV1('/v2/t/11/gameplan/13')).toBe('/gameplan/11/vs/13')
    expect(asV1('/v2/t/11/scouting/13')).toBe('/gameplan/11/vs/13')
    expect(asV1('/v2/t/11/matches/9/m/2')).toBe('/matches/9/m/2')
    expect(asV1('/v2/t/11/replay/9/1')).toBe('/matches/9/m/1')
    expect(asV1('/v2/t/11/players/76561198276087202')).toBe('/players/76561198276087202')
    expect(asV1('/v2/t/11/briefings/new/13')).toBe('/gameplan/11/vs/13')
    expect(asV1('/v2/t/11/jobs/3de159ec')).toBe('/jobs/3de159ec')
    expect(asV1('/v2/t/11/briefings/3de159ec')).toBe('/teams/11')
    expect(asV1('/v2/t/11/practice')).toBe('/teams/11')
    expect(asV1('/v2/t/11')).toBe('/teams/11')
    expect(asV1('/teams/4')).toBe('/teams/4')
  })
})

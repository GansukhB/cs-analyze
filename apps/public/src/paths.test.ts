import { describe, expect, it } from 'vitest'
import { pathsFor, v2Team } from './paths'

describe('v2Team', () => {
  it('reads the my team from a v2 URL only', () => {
    expect(v2Team('/v2/t/11/briefings/abc')).toBe(11)
    expect(v2Team('/v2/t/11')).toBe(11)
    expect(v2Team('/v2')).toBeNull()
    expect(v2Team('/briefings')).toBeNull()
  })
})

describe('pathsFor', () => {
  it('keeps v1 links as they were', () => {
    const p = pathsFor(null)
    expect(p.briefing('abc')).toBe('/briefings/abc')
    expect(p.briefingNew(11, 13)).toBe('/gameplan/11/vs/13/briefing')
    expect(p.job('j1')).toBe('/jobs/j1')
    expect(p.stratNew(11)).toBe('/stratbook/new?team=11')
    expect(p.match(9)).toBe('/matches/9')
    expect(p.match(9, 2)).toBe('/matches/9/m/2')
    expect(p.match(9, 2, 14)).toBe('/matches/9/m/2?round=14')
  })

  it('keeps a v2 reader in v2', () => {
    const p = pathsFor(11)
    expect(p.briefings()).toBe('/v2/t/11/briefings')
    expect(p.briefing('abc')).toBe('/v2/t/11/briefings/abc')
    expect(p.briefingNew(11, 13)).toBe('/v2/t/11/briefings/new/13')
    expect(p.job('j1')).toBe('/v2/t/11/jobs/j1')
    expect(p.scout()).toBe('/v2/t/11/scout')
    expect(p.strat(5)).toBe('/v2/t/11/stratbook/5')
    expect(p.stratNew(11)).toBe('/v2/t/11/stratbook/new?team=11')
    expect(p.gameplanPick()).toBe('/v2/t/11/gameplan')
  })

  it('opens a Match on its report and a moment on the Replay', () => {
    const p = pathsFor(11)
    expect(p.match(9)).toBe('/v2/t/11/matches/9/m/1')
    expect(p.match(9, 2)).toBe('/v2/t/11/matches/9/m/2')
    expect(p.match(9, 2, 14)).toBe('/v2/t/11/replay/9/2?round=14')
  })

  it("sends another my team's Game Plan to v1", () => {
    const p = pathsFor(11)
    expect(p.gameplan(11, 13)).toBe('/v2/t/11/gameplan/13')
    expect(p.gameplan(12, 13)).toBe('/gameplan/12/vs/13')
  })
})

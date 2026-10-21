import { describe, expect, it } from 'vitest'
import type { components } from '../api/schema'
import { applyFilters, type Filters, isActive, roundPasses, sideOf } from './filters'
import { KIND_ORDER } from './format'

type Review = components['schemas']['Review']
type Round = components['schemas']['ReviewRound']

const none: Filters = { team: null, side: null, buy: null, player: null, kinds: new Set(KIND_ORDER), involved: false }
const round = (n: number, ct: number, t: number, ctBuy: string, tBuy: string) =>
  ({ n, ct_team_id: ct, t_team_id: t, ct_buy: ctBuy, t_buy: tBuy }) as unknown as Round

describe('Review filters', () => {
  it('reads a Side from the Team that played it', () => {
    const r = round(1, 10, 20, 'pistol', 'pistol')
    expect(sideOf(r, 10)).toBe('ct')
    expect(sideOf(r, 20)).toBe('t')
    expect(sideOf(r, 30)).toBeNull()
    expect(isActive(none)).toBe(false)
    expect(isActive({ ...none, side: 't' })).toBe(true)
  })

  it('keeps a Round by the buy of the Team asked about', () => {
    const r = round(2, 10, 20, 'full', 'eco')
    expect(roundPasses(r, { ...none, team: 10, buy: 'full' })).toBe(true)
    expect(roundPasses(r, { ...none, team: 20, buy: 'full' })).toBe(false)
    expect(roundPasses(r, { ...none, buy: 'eco' })).toBe(true)
    expect(roundPasses(r, { ...none, team: 10, side: 't' })).toBe(false)
  })

  it('narrows the Rounds to those with a Finding once a Player is picked', () => {
    const review = {
      rounds: [round(1, 10, 20, 'pistol', 'pistol'), round(2, 10, 20, 'full', 'full')],
      findings: [
        { id: 'a', round: 2, kind: 'mistake', code: 'untraded', sids: ['7'], team_id: 10, side: 'ct' },
        { id: 'b', round: 1, kind: 'key_play', code: 'clutch', sids: ['8', '7'], team_id: 20, side: 't' },
      ],
    } as unknown as Review
    const about = applyFilters(review, { ...none, player: '7' })
    expect(about.findings.map((f) => f.id)).toEqual(['a'])
    expect([...about.matching]).toEqual([2])
    const involved = applyFilters(review, { ...none, player: '7', involved: true })
    expect(involved.findings.map((f) => f.id)).toEqual(['a', 'b'])
  })
})

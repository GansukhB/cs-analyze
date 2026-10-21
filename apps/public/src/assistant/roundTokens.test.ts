import { describe, expect, it } from 'vitest'
import { segments } from './roundTokens'

describe('Round tokens', () => {
  it('links a bare round to the Match Map the question was asked on', () => {
    expect(segments('Тэд [R14] дээр алдсан.', { match: 31, map: 2 })).toEqual([
      'Тэд ',
      { label: 'R14', to: '/matches/31/m/2?round=14' },
      ' дээр алдсан.',
    ])
  })

  it('carries the moment and the player, and another map when named', () => {
    const [moment, other] = segments('[R5 1:23 @76561198000000001][4021.2:R3]', null)
    expect(moment).toEqual({ label: 'R5 1:23', to: null })
    expect(other).toEqual({ label: 'R3', to: '/matches/4021/m/2?round=3' })
    const [linked] = segments('[R5 1:23 @76561198000000001]', { match: 1, map: 1 })
    expect(linked).toEqual({ label: 'R5 1:23', to: '/matches/1/m/1?round=5&t=83&player=76561198000000001' })
  })

  it('leaves text that only looks like a token', () => {
    expect(segments('[R123] and R14 and [r14]')).toEqual(['[R123] and R14 and [r14]'])
  })
})

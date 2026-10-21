import { describe, expect, it } from 'vitest'
import { clock, swingRateText, swingText } from './format'

describe('Review numbers', () => {
  it('writes a moment as the Replay clock', () => {
    expect(clock(83.4)).toBe('1:23')
    expect(clock(-2)).toBe('0:00')
    expect(clock(null)).toBe('0:00')
  })

  it('signs a Swing with a real minus', () => {
    expect(swingText(0.274)).toBe('+27%')
    expect(swingText(-0.05)).toBe('−5%')
    expect(swingText(0.001)).toBe('0%')
    expect(swingRateText(0.0026)).toBe('+0.3%')
    expect(swingRateText(-0.012)).toBe('−1.2%')
  })
})

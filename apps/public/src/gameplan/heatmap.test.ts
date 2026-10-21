import { describe, expect, it } from 'vitest'
import { type Extent, GRID, density, difference } from './heatmap'

const extent: Extent = [0, 100, 0, 100]
const sum = (z: Float32Array) => z.reduce((a, b) => a + b, 0)

describe('Heatmap density', () => {
  it('peaks at 1, or sums to 1 by mass', () => {
    const points: [number, number][] = [[20, 20], [21, 19], [24, 26], [80, 80], [78, 83], [60, 40]]
    const peak = density(points, extent)!
    expect(peak.length).toBe(GRID * GRID)
    expect(Math.max(...peak)).toBeCloseTo(1, 5)
    expect(sum(density(points, extent, 'mass')!)).toBeCloseTo(1, 3)
    expect(density(points.slice(0, 3), extent)).toBeNull() // too few to fit
  })

  it('is above the Pool where the Team is, below where only the Pool is', () => {
    const team: [number, number][] = Array.from({ length: 30 }, (_, i) => [20 + (i % 3), 20 + (i % 5)])
    const pool: [number, number][] = Array.from({ length: 30 }, (_, i) => [80 - (i % 3), 80 - (i % 5)])
    const z = difference(team, pool, extent)!
    const at = (x: number, y: number) => z[Math.floor((y / 100) * GRID) * GRID + Math.floor((x / 100) * GRID)]
    expect(at(21, 22)).toBeGreaterThan(0.5)
    expect(at(79, 78)).toBeLessThan(-0.5)
    expect(Math.max(...z.map(Math.abs))).toBeCloseTo(1, 5)
  })
})

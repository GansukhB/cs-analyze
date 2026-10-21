import { describe, expect, it } from 'vitest'
import { blindAt, changeAt, clock, lerpAngle, paleTint, positionAt, toWorld, under, weaponAt, zoomedAt } from './motion'

const track = {
  x: [0, 10, null, 30],
  y: [0, 20, null, 60],
  hp: [100, 90, 0, 0],
  dir: [350, 10, null, null],
  blind: [[8, 2]] as [number, number][],
  weapons: [[1.5, 'ak47'], [4, 'deagle']] as [number, string][],
}

describe('Replay motion', () => {
  it('moves a Player between two frames, turning the short way', () => {
    expect(positionAt(track, 0.5)).toEqual({ x: 5, y: 10, hp: 100, dir: 360 })
    expect(lerpAngle(350, 10, 0.25)).toBe(355)
    expect(lerpAngle(null, 10, 0.5)).toBe(10)
    // The next frame has no position (dead): stay on the last one.
    expect(positionAt(track, 1.5)).toEqual({ x: 10, y: 20, hp: 90, dir: 10 })
    expect(positionAt(track, 2)).toBeNull()
    expect(positionAt(track, -1)).toBeNull()
  })

  it('reads change lists, weapons and blindness at a moment', () => {
    expect(changeAt([[0, 'a'], [5, 'b']] as [number, string][], 4)).toEqual([0, 'a'])
    expect(changeAt([[3, 'a']] as [number, string][], 2)).toBeNull()
    expect(weaponAt(track, 1)).toBe('')
    expect(weaponAt(track, 5)).toBe('deagle')
    expect(blindAt(track, 8, 8)).toBe(1)
    expect(blindAt(track, 16, 8)).toBe(0.5)
    expect(blindAt(track, 24, 8)).toBe(0)
  })

  it('writes the clock and pales a colour', () => {
    expect(clock(83.4)).toBe('1:23')
    expect(paleTint('#000000', 0.5)).toBe('rgb(128,128,128)')
  })

  it('zooms about the cursor and centres again at 1', () => {
    const cam = { zoom: 1, cx: 50, cy: 50 }
    const p = { x: 80, y: 20 }
    const zoomed = zoomedAt(cam, p, 2, 100, 100)
    expect(zoomed.zoom).toBe(2)
    expect(under(zoomed, p, 100, 100)).toEqual(under(cam, p, 100, 100))
    expect(zoomedAt(zoomed, p, 0.1, 100, 100)).toEqual({ zoom: 1, cx: 50, cy: 50 })
    expect(zoomedAt(cam, p, 100, 100, 100).zoom).toBe(6)
    expect(toWorld({ x: 0, y: 100 }, [-1000, 1000, -500, 500], 100, 100)).toEqual([-1000, -500])
  })
})

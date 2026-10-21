// The Replay's arithmetic, kept apart from the canvas and the DOM so it can be
// tested (docs/plans/09 VIZ-1): where a Player is between two 8 Hz frames,
// which way they face, what they hold, how blind they are, and the camera.

/** A Player's path as the Replay payload has it: one entry per frame. */
export interface Track {
  x: (number | null)[]
  y: (number | null)[]
  hp: number[]
  dir?: (number | null)[] | null
  blind?: [number, number][] | null
  weapons?: [number, string][]
}

/** The last change at or before frame `f` of a change list. */
export function changeAt<T extends [number, ...unknown[]]>(list: T[] | undefined | null, f: number): T | null {
  let found: T | null = null
  for (const c of list || []) {
    if (c[0] <= f) found = c
    else break
  }
  return found
}

/** Shortest-path interpolation between two headings (350° → 10° turns 20°). */
export function lerpAngle(a: number | null | undefined, b: number | null | undefined, k: number): number | null {
  if (a === null || a === undefined) return b === null || b === undefined ? null : b
  if (b === null || b === undefined) return a
  const delta = ((((b - a + 180) % 360) + 360) % 360) - 180
  return a + delta * k
}

/** Where a Player is at frame `f` (fractional), linearly between the frames
 *  either side; null before their first or after their last. */
export function positionAt(p: Track, f: number) {
  const i = Math.floor(f)
  const j = Math.min(i + 1, p.x.length - 1)
  if (i < 0 || i >= p.x.length) return null
  const a = p.x[i]
  const b = p.y[i]
  if (a === null || b === null) return null
  const c = p.x[j]
  const d = p.y[j]
  const dirA = p.dir ? p.dir[i] : null
  if (c === null || d === null) return { x: a, y: b, hp: p.hp[i], dir: dirA }
  const k = f - i
  const dirB = p.dir ? p.dir[j] : null
  return { x: a + (c - a) * k, y: b + (d - b) * k, hp: p.hp[i], dir: lerpAngle(dirA, dirB, k) }
}

/** The last weapon a Player fired by second `t`, or '' before their first shot. */
export function weaponAt(p: Track, t: number): string {
  let held = ''
  for (const w of p.weapons || []) {
    if (w[0] <= t) held = w[1]
    else break
  }
  return held
}

/** Blindness 0..1: 1 the instant the flash lands, fading over the Player's own
 *  blind duration (from the demo's flash_duration). */
export function blindAt(p: Track, f: number, hz: number): number {
  let onset: [number, number] | null = null
  for (const b of p.blind || []) {
    if (b[0] <= f) onset = b
    else break
  }
  if (!onset) return 0
  const elapsed = (f - onset[0]) / hz
  return elapsed >= 0 && elapsed < onset[1] ? 1 - elapsed / onset[1] : 0
}

/** A colour paled toward white by `k` (a blinded dot keeps its Side's hue). */
export function paleTint(hex: string, k: number): string {
  const n = parseInt(hex.slice(1), 16)
  const r = (n >> 16) & 255
  const g = (n >> 8) & 255
  const b = n & 255
  return `rgb(${Math.round(r + (255 - r) * k)},${Math.round(g + (255 - g) * k)},${Math.round(b + (255 - b) * k)})`
}

/** Seconds as the Replay's clock: 83.4 → '1:23'. */
export function clock(t: number): string {
  const s = Math.max(0, Math.floor(t))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

// -- the camera (VIZ-3) ---------------------------------------------------------
/** Zoom and the plate point at the canvas's centre, in plate pixels. */
export interface Camera {
  zoom: number
  cx: number
  cy: number
}

export const MAX_ZOOM = 6

/** The plate point under a canvas point (both in plate pixels, W×H). */
export function under(cam: Camera, p: { x: number; y: number }, W: number, H: number) {
  return { x: cam.cx + (p.x - W / 2) / cam.zoom, y: cam.cy + (p.y - H / 2) / cam.zoom }
}

/** The camera zoomed by `factor` about canvas point `p`, which stays put; back
 *  at 1 it centres again. */
export function zoomedAt(cam: Camera, p: { x: number; y: number }, factor: number, W: number, H: number): Camera {
  const before = under(cam, p, W, H)
  const zoom = Math.max(1, Math.min(MAX_ZOOM, cam.zoom * factor))
  if (zoom === 1) return { zoom, cx: W / 2, cy: H / 2 }
  return { zoom, cx: before.x - (p.x - W / 2) / zoom, cy: before.y - (p.y - H / 2) / zoom }
}

/** A plate point in world units, on the overview's world rectangle `ext`. */
export function toWorld(u: { x: number; y: number }, ext: readonly number[], W: number, H: number): [number, number] {
  return [ext[0] + (u.x / W) * (ext[1] - ext[0]), ext[2] + (1 - u.y / H) * (ext[3] - ext[2])]
}

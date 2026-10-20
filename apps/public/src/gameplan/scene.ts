// The animated walk of the movement grid, ported from cstat's _mapgrid.html
// (paintScene). The overview stays a raster <image>; everything that moves is SVG
// over it, placed by the world rectangle the image's edges sit at.
import type { GridWords, Scene, Track } from './types'

const SVG_NS = 'http://www.w3.org/2000/svg'
// One callout to the next: slow enough to follow with the eye, quick enough that
// a five-step route is over in about three seconds.
const STEP_MS = 620

function svg<K extends keyof SVGElementTagNameMap>(name: K, attrs: Record<string, string | number> = {}) {
  const el = document.createElementNS(SVG_NS, name)
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v))
  return el
}

const pathOf = (pts: number[][]) =>
  pts.map((p, n) => `${n ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ')

interface Walker {
  route: Scene['routes'][number]
  pts: number[][]
  stepAt: number[]
  cum: number[]
  glow: SVGPathElement
  line: SVGPathElement
  head: SVGCircleElement
  tally: SVGTextElement
  popped: number
  kills: number
  deaths: number
  width: number
  index: number
  chip: HTMLButtonElement | null
}

/** Mount the scene into ``frame`` (map) and ``below`` (legend + controls).
 *  ``loadTracks`` supplies the real walks when the response did not carry them.
 *  Returns the teardown. */
export function mountScene(
  frame: HTMLElement,
  below: HTMLElement,
  sc: Scene,
  words: GridWords,
  loadTracks: () => Promise<Track[]>,
): () => void {
  const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
  const plate = sc.plate
  const W = plate.width
  const H = plate.height
  const [x0, x1, y0, y1] = plate.extent
  // World to plate pixels; the image's origin is top left, the map's bottom left.
  const px = (x: number) => ((x - x0) / (x1 - x0)) * W
  const py = (y: number) => (1 - (y - y0) / (y1 - y0)) * H

  const root = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'gx-svg', role: 'img' })
  // A map with no shipped overview animates on the dark floor alone.
  if (plate.url) {
    const img = svg('image', { x: 0, y: 0, width: W, height: H })
    img.setAttribute('href', plate.url)
    root.append(img)
  }
  for (const l of sc.labels || []) {
    const t = svg('text', { x: px(l.x), y: py(l.y), class: 'place', 'text-anchor': 'middle', opacity: 0.75 })
    t.textContent = l.name
    root.append(t)
  }
  const marks = svg('g')
  const lines = svg('g')
  const heads = svg('g')
  root.append(lines, marks, heads)

  let maxSteps = 1
  const walkers: Walker[] = (sc.routes || []).map((route, index) => {
    const pts = route.steps.map((st) => [px(st.x), py(st.y)])
    maxSteps = Math.max(maxSteps, route.steps.length)
    const d = pathOf(pts)
    // Width follows the share, so a habit outweighs an experiment; dashed is a
    // route this player does worse on than the men who share it.
    const width = 2.2 + 6.0 * Math.min((route.share || 0) / 0.5, 1)
    const common = { d, fill: 'none', stroke: route.colour, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }
    const glow = svg('path', { ...common, 'stroke-width': width * 2.6, 'stroke-opacity': 0.16 })
    const line = svg('path', { ...common, 'stroke-width': width, 'stroke-opacity': 0.92 })
    if (route.verdict === 'misfits') line.setAttribute('stroke-dasharray', '14 9')
    lines.append(glow, line)
    const head = svg('circle', { r: width * 1.5 + 3, fill: route.colour, stroke: '#0d1116', 'stroke-width': 2 })
    const tally = svg('text', { class: 'tally', fill: route.colour, 'text-anchor': 'middle' })
    heads.append(head, tally)
    const w: Walker = {
      route, pts, stepAt: pts.map((_, i) => i), cum: [], glow, line, head, tally,
      popped: -1, kills: 0, deaths: 0, width, index, chip: null,
    } // prettier-ignore
    measure(w)
    return w
  })
  if (!walkers.length) return () => {}

  // Cumulative distance, so the dot moves at constant speed through a leg.
  function measure(w: Walker) {
    const cum = [0]
    for (let i = 1; i < w.pts.length; i++) {
      const a = w.pts[i - 1]
      const b = w.pts[i]
      cum.push(cum[i - 1] + Math.hypot(b[0] - a[0], b[1] - a[1]))
    }
    w.cum = cum
  }

  function atLength(w: Walker, want: number) {
    const cum = w.cum
    const last = cum.length - 1
    if (want <= 0) return { x: w.pts[0][0], y: w.pts[0][1], upto: 0 }
    if (want >= cum[last]) return { x: w.pts[last][0], y: w.pts[last][1], upto: last }
    let lo = 0
    let hi = last
    while (lo < hi) {
      const mid = (lo + hi) >> 1
      if (cum[mid] < want) lo = mid + 1
      else hi = mid
    }
    const i = Math.max(lo - 1, 0)
    const span = cum[i + 1] - cum[i]
    const frac = span > 0 ? (want - cum[i]) / span : 0
    const a = w.pts[i]
    const b = w.pts[i + 1]
    return { x: a[0] + (b[0] - a[0]) * frac, y: a[1] + (b[1] - a[1]) * frac, upto: i }
  }

  // Progress runs in callouts, not pixels: a long corridor does not make one man
  // look slower than another.
  let total = maxSteps - 1
  const state = { raf: 0, progress: 0, playing: false, focus: null as number | null, last: 0 }

  function popAt(w: Walker, index: number) {
    const st = w.route.steps[index]
    if (!st) return
    if (st.counted) {
      w.kills += st.kills
      w.deaths += st.deaths
    }
    // On the real walk this is the doorway he came through, not the room's middle.
    const p = w.pts[w.stepAt[index]] || w.pts[0]
    const events = st.kills + st.deaths
    if (!st.counted || events <= 0) return
    const colour = st.kills > st.deaths ? '#4fb286' : st.deaths > st.kills ? '#cf6a56' : '#a2acb6'
    const ring = svg('circle', { cx: p[0], cy: p[1], r: 4, fill: 'none', stroke: colour, 'stroke-width': 2.4, opacity: 0.95 })
    ring.dataset.track = String(w.index)
    ring.append(
      svg('animate', { attributeName: 'r', from: 4, to: 10 + Math.min(events, 20) * 1.5, dur: '0.7s', fill: 'freeze' }),
      svg('animate', { attributeName: 'opacity', from: 0.95, to: 0.25, dur: '0.7s', fill: 'freeze' }),
    )
    const txt = svg('text', { x: p[0], y: p[1] - 14, class: 'pop', fill: colour, 'text-anchor': 'middle', opacity: 0 })
    txt.textContent = `${st.kills}–${st.deaths}`
    txt.dataset.track = String(w.index)
    txt.append(svg('animate', { attributeName: 'opacity', from: 0, to: 0.9, dur: '0.35s', fill: 'freeze' }))
    marks.append(ring, txt)
  }

  function frameAt(progress: number) {
    for (const w of walkers) {
      const legs = w.stepAt.length - 1
      const at = Math.min(progress, legs)
      const i = Math.floor(at)
      const from = w.cum[w.stepAt[Math.min(i, legs)]]
      const to = w.cum[w.stepAt[Math.min(i + 1, legs)]]
      const here = atLength(w, from + (to - from) * (at - i))
      const lit = state.focus === null || state.focus === w.index
      w.head.setAttribute('cx', String(here.x))
      w.head.setAttribute('cy', String(here.y))
      w.head.setAttribute('opacity', String(lit ? (progress > legs + 0.5 ? 0.35 : 1) : 0.12))
      // The line is revealed behind the dot, which makes the callout order readable.
      const d = pathOf(w.pts.slice(0, here.upto + 1).concat([[here.x, here.y]]))
      w.line.setAttribute('d', d)
      w.glow.setAttribute('d', d)
      while (w.popped < Math.floor(at)) {
        w.popped += 1
        popAt(w, w.popped)
      }
      w.tally.textContent = `${w.kills}–${w.deaths}`
      w.tally.setAttribute('x', String(here.x))
      w.tally.setAttribute('y', String(here.y - w.width * 1.6 - 8))
      w.tally.setAttribute('opacity', String(!lit || progress >= total ? 0 : 0.95))
      w.line.setAttribute('stroke-opacity', String(lit ? 0.92 : 0.12))
      w.glow.setAttribute('stroke-opacity', String(lit ? 0.16 : 0.03))
      const b = w.chip?.querySelector('b')
      if (b) b.textContent = `${w.kills}–${w.deaths}`
    }
    marks.childNodes.forEach((m) => {
      const el = m as SVGElement
      el.style.display = state.focus === null || String(state.focus) === el.dataset.track ? '' : 'none'
    })
  }

  frame.replaceChildren(root)

  // The legend is the attribution layer and doubles as a filter: with nine paths
  // crossing one map, isolating one is the difference between a picture and a tangle.
  const legend = document.createElement('div')
  legend.className = 'gx-legend'
  const GLYPH: Record<string, string> = { suits: ' ✓', misfits: ' ✗' }
  for (const w of walkers) {
    const chip = document.createElement('button')
    chip.type = 'button'
    chip.setAttribute('aria-pressed', 'false')
    const dot = document.createElement('i')
    dot.style.background = w.route.colour
    if (w.route.verdict === 'misfits') dot.className = 'dash'
    const name = document.createElement('span')
    name.textContent =
      (sc.pooled ? `${w.route.player} · ` : '') + `${Math.round(w.route.share * 100)}%` + (GLYPH[w.route.verdict] || '')
    const num = document.createElement('b')
    num.textContent = '0–0'
    chip.append(dot, name, num)
    chip.addEventListener('click', () => {
      state.focus = state.focus === w.index ? null : w.index
      legend.querySelectorAll('button').forEach((b, i) => {
        b.setAttribute('aria-pressed', state.focus === i ? 'true' : 'false')
        b.classList.toggle('dim', state.focus !== null && state.focus !== i)
      })
      frameAt(state.progress)
    })
    w.chip = chip
    legend.append(chip)
  }

  const bar = document.createElement('div')
  bar.className = 'gx-controls'
  const play = document.createElement('button')
  const replay = document.createElement('button')
  replay.textContent = words.replay || '↻'
  const range = document.createElement('input')
  range.type = 'range'
  range.min = '0'
  range.max = '1000'
  range.value = '0'
  range.setAttribute('aria-label', words.scrub || 'progress')
  const readout = document.createElement('span')
  readout.className = 'step'

  const setLabel = () => (play.textContent = state.playing ? words.pause || '❚❚' : words.play || '▶')
  function show(progress: number) {
    state.progress = progress
    frameAt(progress)
    range.value = String(total ? Math.round((progress / total) * 1000) : 1000)
    readout.textContent = `${words.step || 'step'} ${Math.min(Math.floor(progress) + 1, maxSteps)}/${maxSteps}`
  }
  function reset() {
    marks.replaceChildren()
    for (const w of walkers) {
      w.popped = -1
      w.kills = 0
      w.deaths = 0
    }
    show(0)
  }
  function tick(now: number) {
    if (!state.playing) return
    const dt = now - (state.last || now)
    state.last = now
    const next = state.progress + dt / STEP_MS
    if (next >= total) {
      show(total)
      pause()
      return
    }
    show(next)
    state.raf = requestAnimationFrame(tick)
  }
  function playIt() {
    if (state.progress >= total) reset()
    state.playing = true
    state.last = 0
    setLabel()
    state.raf = requestAnimationFrame(tick)
  }
  function pause() {
    state.playing = false
    cancelAnimationFrame(state.raf)
    setLabel()
  }
  play.addEventListener('click', () => (state.playing ? pause() : playIt()))
  replay.addEventListener('click', () => {
    reset()
    playIt()
  })
  range.addEventListener('input', () => {
    pause()
    const target = (Number(range.value) / 1000) * total
    // Scrubbing back has to unwind the pops, or the tallies keep counting up.
    if (target < state.progress) reset()
    show(target)
  })
  bar.append(play, replay, range, readout)
  below.replaceChildren(bar, legend)

  const start = () => {
    reset()
    setLabel()
    if (reduceMotion) show(total)
    else playIt()
  }
  start()

  // The centroid path corners through walls; the walk somebody actually walked
  // replaces the geometry in place, and if it never arrives the straight one stands.
  let alive = true
  function upgrade(found: Track[]) {
    if (!alive) return
    // Keyed by player too: in the all-players view two men can share a route,
    // and each must walk his own medoid, not whichever was read last.
    const byKey = new Map(found.map((t) => [`${t.player}|${t.side}|${t.route_key}`, t]))
    let upgraded = 0
    for (const w of walkers) {
      const real = byKey.get(`${w.route.player}|${w.route.side}|${w.route.route_key}`)
      if (!real || !real.points || real.points.length < 2) continue
      w.pts = real.points.map((p) => [px(p[0]), py(p[1])])
      w.stepAt = real.steps.map((st) => Math.min(st.i, w.pts.length - 1))
      if (w.stepAt.length < 2) w.stepAt = [0, w.pts.length - 1]
      measure(w)
      const d = pathOf(w.pts)
      w.line.setAttribute('d', d)
      w.glow.setAttribute('d', d)
      upgraded += 1
    }
    if (!upgraded) return
    maxSteps = Math.max(...walkers.map((w) => w.stepAt.length))
    total = maxSteps - 1
    start()
  }
  if (sc.tracks?.length) upgrade(sc.tracks)
  else loadTracks().then(upgrade, () => {})

  return () => {
    alive = false
    pause()
    below.replaceChildren()
  }
}

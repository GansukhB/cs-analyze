// A heatmap drawn in the browser, as cstat drew it on the server with matplotlib
// (hltv/services/heatmaps.py: _render_local, radar._composite). The server sends
// the positions, the callout labels and where the overview images sit in the
// world; everything else happens here, so nothing is drawn or kept on the server.
import { COLORMAPS } from './colormaps'

export interface HeatPlate {
  url: string | null
  lower: string | null
  width: number
  height: number
  extent: [number, number, number, number]
}

export interface HeatData {
  cmap: string
  points: [number, number][]
  // False when there are too few points for a density: the dots alone.
  heat?: boolean
  labels: { name: string; x: number; y: number }[]
  level: string
  plate: HeatPlate | null
  // VIZ-9: every other Team's points the same way, to draw where this one is
  // more (red) or less (blue) than usual instead of the plain heat.
  pool?: [number, number][] | null
}

// radar.py's composite: the overview is a backdrop, not the subject -- pulled
// towards grey and towards the page ground so the heat stays the brightest thing.
const GROUND = [13, 17, 22]
const DIM = 0.72
const SATURATION = 0.6
const LOWER_ALPHA = 0.45
const UPPER_GHOST = 0.25
const OPAQUE = 25
const CROP_PAD = 8
// heatmaps.py: a 240x240 kernel density at bandwidth factor 0.22, transparent
// where cold (alpha = density x 1.5, capped at 0.88).
const GRID = 240
const BANDWIDTH = 0.22

type Extent = [number, number, number, number]

interface Backdrop {
  canvas: HTMLCanvasElement | null
  extent: Extent
}

const backdrops = new Map<string, Promise<Backdrop | null>>()

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error(`could not load ${url}`))
    img.src = url
  })
}

function pixels(img: HTMLImageElement): ImageData {
  const c = document.createElement('canvas')
  c.width = img.naturalWidth
  c.height = img.naturalHeight
  const g = c.getContext('2d')!
  g.drawImage(img, 0, 0)
  return g.getImageData(0, 0, c.width, c.height)
}

/** The dimmed, desaturated, cropped overview and the world rectangle it covers. */
function backdrop(plate: HeatPlate, level: string): Promise<Backdrop | null> {
  const key = `${plate.url}|${plate.lower}|${level}`
  let found = backdrops.get(key)
  if (!found) {
    found = build(plate, level).catch(() => null)
    backdrops.set(key, found)
  }
  return found
}

async function build(plate: HeatPlate, level: string): Promise<Backdrop | null> {
  if (!plate.url) return null
  const upperImg = await loadImage(plate.url)
  const lowerImg = plate.lower ? await loadImage(plate.lower).catch(() => null) : null
  const upper = pixels(upperImg)
  let lower = lowerImg ? pixels(lowerImg) : null
  if (lower && (lower.width !== upper.width || lower.height !== upper.height)) lower = null
  if ((level === 'upper' || level === 'lower') && !lower) return null

  const { width, height } = upper
  const out = new Float32Array(width * height * 3)
  for (let i = 0; i < width * height; i++) out.set(GROUND, i * 3)
  const paint = (img: ImageData, strength: number) => {
    const d = img.data
    for (let i = 0; i < width * height; i++) {
      const a = (d[i * 4 + 3] / 255) * strength
      if (!a) continue
      for (let c = 0; c < 3; c++) out[i * 3 + c] = out[i * 3 + c] * (1 - a) + d[i * 4 + c] * a
    }
  }
  if (level === 'lower' && lower) {
    paint(upper, UPPER_GHOST)
    paint(lower, 1)
  } else if (level === 'upper') {
    paint(upper, 1)
  } else {
    if (lower) paint(lower, LOWER_ALPHA)
    paint(upper, 1)
  }

  // Crop to what is drawn, taken from both floors so every form of a map lands
  // on the same rectangle.
  let r0 = height, r1 = -1, c0 = width, c1 = -1 // prettier-ignore
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4 + 3
      if (upper.data[i] > OPAQUE || (lower && lower.data[i] > OPAQUE)) {
        if (y < r0) r0 = y
        if (y > r1) r1 = y
        if (x < c0) c0 = x
        if (x > c1) c1 = x
      }
    }
  }
  if (r1 < 0) return null
  r0 = Math.max(r0 - CROP_PAD, 0)
  r1 = Math.min(r1 + CROP_PAD + 1, height)
  c0 = Math.max(c0 - CROP_PAD, 0)
  c1 = Math.min(c1 + CROP_PAD + 1, width)

  const canvas = document.createElement('canvas')
  canvas.width = c1 - c0
  canvas.height = r1 - r0
  const g = canvas.getContext('2d')!
  const img = g.createImageData(canvas.width, canvas.height)
  for (let y = r0; y < r1; y++) {
    for (let x = c0; x < c1; x++) {
      const s = (y * width + x) * 3
      const luma = 0.2126 * out[s] + 0.7152 * out[s + 1] + 0.0722 * out[s + 2]
      const t = ((y - r0) * canvas.width + (x - c0)) * 4
      for (let c = 0; c < 3; c++) {
        const grey = luma + (out[s + c] - luma) * SATURATION
        img.data[t + c] = Math.max(0, Math.min(255, GROUND[c] + (grey - GROUND[c]) * DIM))
      }
      img.data[t + 3] = 255
    }
  }
  g.putImageData(img, 0, 0)
  const [ex0, ex1, , ey1] = plate.extent
  const scale = (ex1 - ex0) / width
  return { canvas, extent: [ex0 + c0 * scale, ex0 + c1 * scale, ey1 - r1 * scale, ey1 - r0 * scale] }
}

/** scipy's gaussian_kde with bw_method=0.22, on a GRID x GRID lattice over the
 *  extent, normalised to its peak. Null when it cannot be fit (too few or
 *  co-linear points), which -- as in cstat -- leaves just the dots. */
function density(
  points: [number, number][],
  [x0, x1, y0, y1]: Extent,
  norm: 'peak' | 'mass' = 'peak',
): Float32Array | null {
  const n = points.length
  if (n < 4) return null
  let mx = 0, my = 0 // prettier-ignore
  for (const [x, y] of points) {
    mx += x
    my += y
  }
  mx /= n
  my /= n
  let sxx = 0, syy = 0, sxy = 0 // prettier-ignore
  for (const [x, y] of points) {
    sxx += (x - mx) * (x - mx)
    syy += (y - my) * (y - my)
    sxy += (x - mx) * (y - my)
  }
  // The data covariance (n - 1, as numpy) scaled by the bandwidth factor squared.
  const f2 = BANDWIDTH * BANDWIDTH
  const a = (sxx / (n - 1)) * f2
  const d = (syy / (n - 1)) * f2
  const b = (sxy / (n - 1)) * f2
  const det = a * d - b * b
  if (!(det > 1e-9)) return null
  const ia = d / det, ib = -b / det, id = a / det // prettier-ignore

  const z = new Float32Array(GRID * GRID)
  const dx = (x1 - x0) / (GRID - 1)
  const dy = (y1 - y0) / (GRID - 1)
  // Each point only reaches cells within 4 marginal standard deviations: past
  // that its weight is under e^-8 of the peak, invisible at this alpha.
  const rx = 4 * Math.sqrt(a)
  const ry = 4 * Math.sqrt(d)
  for (const [px, py] of points) {
    const i0 = Math.max(0, Math.floor((px - rx - x0) / dx))
    const i1 = Math.min(GRID - 1, Math.ceil((px + rx - x0) / dx))
    const j0 = Math.max(0, Math.floor((py - ry - y0) / dy))
    const j1 = Math.min(GRID - 1, Math.ceil((py + ry - y0) / dy))
    for (let j = j0; j <= j1; j++) {
      const vy = y0 + j * dy - py
      for (let i = i0; i <= i1; i++) {
        const vx = x0 + i * dx - px
        z[j * GRID + i] += Math.exp(-0.5 * (ia * vx * vx + 2 * ib * vx * vy + id * vy * vy))
      }
    }
  }
  let peak = 0
  let mass = 0
  for (let k = 0; k < z.length; k++) {
    if (z[k] > peak) peak = z[k]
    mass += z[k]
  }
  if (!(peak > 0)) return null
  const by = norm === 'peak' ? peak : mass
  for (let k = 0; k < z.length; k++) z[k] /= by
  return z
}

// Where this Team's density is above (red) or below (blue) every other Team's,
// each as a share of its own mass, scaled to the largest gap (VIZ-9).
const MORE = [209, 73, 91]
const LESS = [91, 155, 216]
function difference(points: [number, number][], pool: [number, number][], extent: Extent): Float32Array | null {
  const a = density(points, extent, 'mass')
  const b = density(pool, extent, 'mass')
  if (!a || !b) return null
  const z = new Float32Array(a.length)
  let top = 0
  for (let k = 0; k < z.length; k++) {
    z[k] = a[k] - b[k]
    top = Math.max(top, Math.abs(z[k]))
  }
  if (!(top > 0)) return null
  for (let k = 0; k < z.length; k++) z[k] /= top
  return z
}

/** Draw one heatmap into ``canvas``, sized to the map's own shape. */
export async function drawHeatmap(canvas: HTMLCanvasElement, data: HeatData, cssWidth: number): Promise<void> {
  const plate = data.plate ? await backdrop(data.plate, data.level) : null
  let extent: Extent
  if (plate) {
    extent = plate.extent
  } else {
    // No overview: frame the points themselves, as cstat's fallback did. A
    // single dot, or a line of them, spans nothing on an axis: give it room.
    const xs = data.points.map((p) => p[0])
    const ys = data.points.map((p) => p[1])
    const padX = (Math.max(...xs) - Math.min(...xs)) * 0.05 || 250
    const padY = (Math.max(...ys) - Math.min(...ys)) * 0.05 || 250
    extent = [Math.min(...xs) - padX, Math.max(...xs) + padX, Math.min(...ys) - padY, Math.max(...ys) + padY]
  }
  const [x0, x1, y0, y1] = extent
  const aspect = (y1 - y0) / (x1 - x0)
  const dpr = window.devicePixelRatio || 1
  const W = Math.round(cssWidth * dpr)
  const H = Math.round(cssWidth * aspect * dpr)
  canvas.width = W
  canvas.height = H
  canvas.style.aspectRatio = `${1 / aspect}`
  const g = canvas.getContext('2d')!
  const px = (x: number) => ((x - x0) / (x1 - x0)) * W
  const py = (y: number) => (1 - (y - y0) / (y1 - y0)) * H

  g.fillStyle = '#0d1116'
  g.fillRect(0, 0, W, H)
  g.imageSmoothingEnabled = true
  g.imageSmoothingQuality = 'high'
  if (plate?.canvas) g.drawImage(plate.canvas, 0, 0, W, H)

  const diff = data.pool && data.pool.length >= 20 ? difference(data.points, data.pool, extent) : null
  if (diff) {
    const heat = document.createElement('canvas')
    heat.width = GRID
    heat.height = GRID
    const hg = heat.getContext('2d')!
    const img = hg.createImageData(GRID, GRID)
    for (let j = 0; j < GRID; j++) {
      const row = GRID - 1 - j
      for (let i = 0; i < GRID; i++) {
        const v = diff[j * GRID + i]
        const c = v >= 0 ? MORE : LESS
        const t = (row * GRID + i) * 4
        img.data[t] = c[0]
        img.data[t + 1] = c[1]
        img.data[t + 2] = c[2]
        img.data[t + 3] = Math.round(Math.min(Math.abs(v) * 1.3, 0.85) * 255)
      }
    }
    hg.putImageData(img, 0, 0)
    g.drawImage(heat, 0, 0, W, H)
  }
  const z = diff || data.heat === false ? null : density(data.points, extent)
  if (z) {
    const lut = COLORMAPS[data.cmap] ?? COLORMAPS.inferno
    const heat = document.createElement('canvas')
    heat.width = GRID
    heat.height = GRID
    const hg = heat.getContext('2d')!
    const img = hg.createImageData(GRID, GRID)
    for (let j = 0; j < GRID; j++) {
      // Row j is y0 + j*dy: the first row is the bottom of the map, the last the top.
      const row = GRID - 1 - j
      for (let i = 0; i < GRID; i++) {
        const v = z[j * GRID + i]
        const k = Math.min(255, Math.round(v * 255)) * 3
        const t = (row * GRID + i) * 4
        img.data[t] = lut[k]
        img.data[t + 1] = lut[k + 1]
        img.data[t + 2] = lut[k + 2]
        img.data[t + 3] = Math.round(Math.min(Math.max(v * 1.5, 0), 0.88) * 255)
      }
    }
    hg.putImageData(img, 0, 0)
    g.drawImage(heat, 0, 0, W, H)
  }

  // matplotlib's s=13 dots and 6.2 pt labels, as a share of the plot's width.
  const dot = Math.max(1.5, W * 0.0049)
  g.lineWidth = Math.max(0.6, W * 0.0011)
  g.strokeStyle = '#0d1116'
  g.fillStyle = 'rgba(255, 255, 255, 0.75)'
  for (const [x, y] of data.points) {
    g.beginPath()
    g.arc(px(x), py(y), dot, 0, Math.PI * 2)
    g.fill()
    g.stroke()
  }
  const font = Math.max(9, W * 0.0168)
  g.font = `${font}px ui-sans-serif, system-ui, sans-serif`
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  g.lineJoin = 'round'
  g.lineWidth = font * 0.26
  g.strokeStyle = '#0d1116'
  g.fillStyle = 'rgba(195, 204, 213, 0.9)'
  for (const label of data.labels) {
    g.strokeText(label.name, px(label.x), py(label.y))
    g.fillText(label.name, px(label.x), py(label.y))
  }
}

/**
 * The round replay: a canvas over the map's radar, driven by one round's payload
 * at a time (see apps/api/app/services/replay.py for its shape).
 *
 * Ported from cstat's match_detail.html script, which is plain DOM and canvas code;
 * it stays that way here. `Replay.tsx` renders the markup (the ids below) and
 * calls `mountReplay`, which wires everything up and returns a teardown.
 */

import { canvasIcon, equipmentUrl, iconEl, iconHtml, KILL_ICONS } from './icons'

export interface Label {
  name: string
  x: number
  y: number
}

export interface SceneData {
  plate: { url: string | null; width: number; height: number; extent: number[] }
  labels: Label[]
  levels: { key: string; url: string | null; labels: Label[] }[]
}

interface Player {
  sid: string
  name: string
  team: string
  side: string
  colour: string
  x: (number | null)[]
  y: (number | null)[]
  hp: number[]
  dir: (number | null)[]
  place: [number, number][]
  lvl: [number, number][]
  blind: [number, number][]
  weapons: [number, string][]
  // The Loadout, as changes; absent on Tick Data read before it (schema < 5).
  held?: [number, string][]
  inv?: [number, string[]][]
  gear?: [number, number, number, number, number][] // frame, armor, helmet, kit, money
}

interface ReplayEvent {
  t: number
  kind: 'kill' | 'hurt' | 'shot' | 'bomb'
  by?: string
  who?: string
  whom?: string
  weapon?: string
  hs?: boolean
  blind?: boolean
  smoke?: boolean
  wall?: boolean
  dmg?: number
  left?: number
  hit?: string
  event?: string
  site?: string
  side?: string
  x: number | null
  y: number | null
  vx?: number | null
  vy?: number | null
  lvl?: number | null
  vlvl?: number | null
}

interface Nade {
  kind: string
  t0: number
  t1: number
  x: number[]
  y: number[]
  lvl?: (number | null)[]
}

interface Effect {
  kind: string
  x: number
  y: number
  r: number
  t0: number
  t1: number
  lvl: number | null
}

export interface RoundData {
  round: number
  hz: number
  frames: number
  seconds: number
  winner_side: string
  winner: string
  reason: string
  site: string
  plant_t: number | null
  levels: string[]
  loadout?: boolean
  places: string[]
  players: Player[]
  events: ReplayEvent[]
  nades: Nade[]
  effects: Effect[]
}

type Floor = number | null

// One player's row in the broadcast-style panel beside the map.
interface Chip {
  el: HTMLElement
  label: HTMLElement
  hp: HTMLElement
  fill: HTMLElement
  // The gun on the first line and the second line (armor, money, the rest of
  // the Loadout); absent on a round with no Loadout.
  gun?: HTMLElement
  kit?: HTMLElement
  shown?: string
}

// The Loadout's grenade labels.
const NADES = new Set(['flash', 'smoke', 'HE', 'molotov', 'incendiary', 'decoy'])
const PISTOLS = new Set(['Glock', 'USP-S', 'P2000', 'P250', 'Five-SeveN', 'Tec-9', 'CZ', 'Deagle', 'Duals', 'R8'])

// The last change at or before frame `f` of a change list.
function changeAt<T extends [number, ...unknown[]]>(list: T[] | undefined, f: number): T | null {
  let found: T | null = null
  for (const c of list || []) {
    if (c[0] <= f) found = c
    else break
  }
  return found
}

const WEAPONS: Record<string, string> = {
  ak47: 'AK-47', m4a1: 'M4', awp: 'AWP', 'usp/p2000': 'USP', glock: 'Glock',
  deagle: 'Deagle', galilar: 'Galil', famas: 'Famas', mp9: 'MP9', mac10: 'MAC-10',
  mp7: 'MP7', ump45: 'UMP', p90: 'P90', bizon: 'Bizon', elite: 'Duals',
  fiveseven: 'Five-SeveN', tec9: 'Tec-9', cz75a: 'CZ', p250: 'P250', revolver: 'R8',
  ssg08: 'Scout', aug: 'AUG', sg556: 'SG', nova: 'Nova', xm1014: 'XM1014',
  sawedoff: 'Sawed-Off', mag7: 'MAG-7', negev: 'Negev', m249: 'M249',
  hegrenade: 'HE', flashbang: 'flash', smokegrenade: 'smoke', molotov: 'molotov',
  incgrenade: 'incendiary', inferno: 'fire', decoy: 'decoy', knife: 'knife',
  world: 'the map', taser: 'zeus',
}
const gun = (w?: string) => WEAPONS[w ?? ''] || w || '?'

const HITGROUP: Record<string, string> = {
  head: 'head', neck: 'neck', chest: 'chest', stomach: 'body', left_arm: 'l.arm',
  right_arm: 'r.arm', left_leg: 'l.leg', right_leg: 'r.leg', generic: '', gear: 'gear',
}
const hit = (h?: string) => (h && h in HITGROUP ? HITGROUP[h] : (h || '').replace('_', '.'))

const NADE_COLOUR: Record<string, string> = {
  smoke: '#c8d2dc', flash: '#e8e0a0', he: '#cf6a56', fire: '#e0854a', decoy: '#8fa0b0',
  nade: '#a2acb6',
}

// How long a floor has to be the busier one before `auto` moves to it, on the
// round's clock: a third of live frames on Nuke have players on both floors.
const AUTO_DWELL = 1.0
const TRAIL_FRAMES = 24 // three seconds at 8 Hz
// The Held weapon's icon beside a name on the map, in plate pixels.
const ICON_H = 11
const ICON_GAP = 5
// cstat dims and desaturates the overview so the dots read over it; here a veil
// over the drawn radar does the dimming.
const RADAR_VEIL = 'rgba(13, 17, 22, .32)'

export function mountReplay(
  root: HTMLElement,
  scene: SceneData,
  fetchRound: (n: number) => Promise<RoundData>,
  startRound?: number,
  // Rounds each club had won when round `n` began, by club name.
  scoreBefore: (n: number) => Record<string, number> = () => ({}),
): () => void {
  const $ = <T extends HTMLElement = HTMLElement>(id: string) =>
    root.querySelector<T>(`#${id}`) as T
  const canvas = $<HTMLCanvasElement>('rp-canvas')
  const ctx = canvas.getContext('2d')!
  const loading = $('rp-loading')
  const feedBox = $('rp-feed')
  const seek = $<HTMLInputElement>('rp-seek')
  const marks = $('rp-marks')
  const floorBox = root.querySelector<HTMLElement>('#rp-floors')
  const ROUNDS = [...root.querySelectorAll<HTMLElement>('#rp-rounds .r')].map((b) => Number(b.dataset.round))
  const prevButton = $<HTMLButtonElement>('rp-prev')
  const nextButton = $<HTMLButtonElement>('rp-next')
  const timeEl = $('rp-time')
  let destroyed = false
  let frame = 0
  // Every listener goes through `on`, so teardown removes them all at once (React
  // mounts twice in development, and a stale player must not keep reacting).
  const abort = new AbortController()
  const on = (el: HTMLElement | Document, type: string, fn: EventListener) =>
    el.addEventListener(type, fn, { signal: abort.signal })

  // Plate space: one drawing unit is one plate pixel; CSS scales the canvas.
  const W = scene.plate.width
  const H = scene.plate.height
  const EXT = scene.plate.extent
  const DPR = Math.min(2, window.devicePixelRatio || 1)
  canvas.width = W * DPR
  canvas.height = H * DPR
  ctx.scale(DPR, DPR)

  const px = (x: number) => ((x - EXT[0]) / (EXT[1] - EXT[0])) * W
  const py = (y: number) => (1 - (y - EXT[2]) / (EXT[3] - EXT[2])) * H
  // World units per plate pixel, so a radius in the game is a radius on screen.
  const UNIT = W / (EXT[1] - EXT[0])

  // Facing marker: world yaw (0 = +X, counter-clockwise) to a canvas angle,
  // scaled per axis rather than assuming the extent is square.
  const scaleX = W / (EXT[1] - EXT[0])
  const scaleY = H / (EXT[3] - EXT[2])
  function facingRad(yawDeg: number) {
    const rad = (yawDeg * Math.PI) / 180
    return Math.atan2(-Math.sin(rad) * scaleY, Math.cos(rad) * scaleX)
  }

  // One image per floor beside the main one, all on the same rectangle, so
  // changing floor changes an image and nothing else.
  const LEVELS = scene.levels || []
  function preload(url: string | null) {
    if (!url) return null
    const img = new Image()
    img.onload = () => draw()
    img.src = url
    return img
  }
  const plate = preload(scene.plate.url)
  const floorPlates = LEVELS.map((level) => preload(level.url))
  const ready = (img: HTMLImageElement | null) => (img && img.complete && img.naturalWidth ? img : null)
  const plateFor = (floor: Floor) => ready(floor === null ? plate : floorPlates[floor]) || ready(plate)

  // An entity with no floor of its own is on every floor rather than on none.
  const onFloor = (lvl: number | null | undefined, floor: Floor) =>
    floor === null || lvl === null || lvl === undefined || lvl === floor

  const state = {
    round: null as number | null,
    data: null as RoundData | null,
    t: 0,
    playing: false,
    speed: 1,
    last: 0,
    names: true,
    trails: true,
    util: true,
    shots: true,
    labels: false,
    damage: true,
    // "auto" or a floor index; `autoFloor` is what auto has settled on this round.
    floor: 'auto' as 'auto' | number,
    autoFloor: null as Floor,
    shownFloor: undefined as Floor | undefined,
    // sid -> chip, rebuilt per round so draw() never walks the document.
    chips: {} as Record<string, Chip>,
  }

  function playerFloorAt(p: Player, f: number): Floor {
    if (!p.lvl || !p.lvl.length) return null
    let found: Floor = null
    for (const c of p.lvl) {
      if (c[0] <= f) found = c[1]
      else break
    }
    return found
  }

  function busiestFloor(f: number): Floor {
    // Which floor has more players still alive on it; null for a tie.
    const alive = LEVELS.map(() => 0)
    state.data!.players.forEach((p) => {
      const s = at(p, f)
      if (!s || s.hp <= 0) return
      const fl = playerFloorAt(p, f)
      if (fl !== null && fl < alive.length) alive[fl] += 1
    })
    const best = Math.max(...alive)
    return alive.filter((n) => n === best).length === 1 ? alive.indexOf(best) : null
  }

  function shownFloor(f: number, t: number): number {
    if (state.floor !== 'auto') return state.floor
    const d = state.data!
    // Once the bomb is down the round is wherever the bomb is.
    if (d.plant_t !== null && t >= d.plant_t) {
      const plantEvent = d.events.find((e) => e.kind === 'bomb' && e.event === 'plant')
      if (plantEvent && plantEvent.lvl !== null && plantEvent.lvl !== undefined) {
        state.autoFloor = plantEvent.lvl
        return plantEvent.lvl
      }
    }
    const now = busiestFloor(f)
    if (now !== null && now === busiestFloor(Math.max(0, f - AUTO_DWELL * d.hz))) {
      state.autoFloor = now
    }
    return state.autoFloor === null ? (now === null ? 0 : now) : state.autoFloor
  }

  function markFloor(floor: Floor) {
    // In auto, a dot under the floor auto has settled on.
    if (!floorBox || floor === state.shownFloor) return
    state.shownFloor = floor
    const dot = state.floor === 'auto' ? String(floor) : null
    floorBox.querySelectorAll<HTMLButtonElement>('button').forEach((b) =>
      b.classList.toggle('now', b.dataset.floor === dot),
    )
  }

  function setFloor(value: 'auto' | number) {
    state.floor = value
    state.shownFloor = undefined
    floorBox?.querySelectorAll<HTMLButtonElement>('button').forEach((b) =>
      b.classList.toggle('on', b.dataset.floor === String(value)),
    )
    draw()
  }

  // ---- loading a round ------------------------------------------------------
  // A round picked while the replay plays starts playing too, from its start.
  async function load(n: number) {
    const resume = state.playing
    state.round = n
    state.playing = false
    setPlay()
    loading.hidden = false
    loading.textContent = `loading round ${n}…`
    root.querySelectorAll<HTMLElement>('#rp-rounds .r').forEach((b) =>
      b.classList.toggle('on', Number(b.dataset.round) === n),
    )
    try {
      const data = await fetchRound(n)
      if (destroyed || state.round !== n) return
      state.data = data
    } catch (err) {
      if (destroyed) return
      loading.textContent = String((err as Error).message || err)
      state.data = null
      return
    }
    state.t = 0
    state.autoFloor = null
    renderRoundHead()
    renderScoreboard()
    seek.max = String(Math.max(1, Math.round(state.data.seconds * 100)))
    seek.value = '0'
    buildMarks()
    renderFeed()
    loading.hidden = true
    state.playing = resume
    state.last = performance.now()
    setPlay()
    draw()
  }

  // Who is on each side is fixed for the round, so it is built once here.
  function renderScoreboard() {
    const d = state.data
    state.chips = {}
    for (const side of ['ct', 't']) {
      const box = $(`rp-roster-${side}`)
      const nameEl = $(`rp-team-${side}`)
      box.replaceChildren()
      if (!d) {
        nameEl.textContent = side.toUpperCase()
        continue
      }
      const players = d.players.filter((p) => p.side === side).sort((a, b) => a.name.localeCompare(b.name))
      const club = players.find((p) => p.team)?.team
      nameEl.textContent = club || side.toUpperCase()
      $(`rp-${side}`).textContent = String((club && scoreBefore(d.round)[club]) || 0)
      $('rp-round-no').textContent = `round ${d.round}`
      players.forEach((p) => {
        const row = document.createElement('div')
        row.className = 'rp-pl'
        row.style.setProperty('--pc', p.colour)
        const fill = document.createElement('i')
        fill.className = 'rp-fill'
        const top = document.createElement('div')
        top.className = 'rp-l1'
        const hp = document.createElement('b')
        hp.className = 'rp-hp'
        const label = document.createElement('b')
        label.className = 'rp-nm'
        label.textContent = p.name
        label.style.color = p.colour
        top.append(hp, label)
        row.append(fill, top)
        box.append(row)
        state.chips[p.sid] = { el: row, label, hp, fill }
        if (d.loadout && p.gear) {
          const gun = document.createElement('span')
          gun.className = 'rp-gun'
          top.append(gun)
          const kit = document.createElement('div')
          kit.className = 'rp-l2'
          row.append(kit)
          Object.assign(state.chips[p.sid], { gun, kit })
        }
      })
    }
  }

  function renderRoundHead() {
    const head = $('rp-round-head')
    head.replaceChildren()
    const d = state.data
    if (!d) return
    head.append(document.createTextNode(`Round ${d.round} — `))
    const who = document.createElement('b')
    who.className = d.winner_side === 'ct' ? 'ct' : 't'
    who.textContent = d.winner || d.winner_side.toUpperCase() || '?'
    head.append(who)
    const how = document.createElement('span')
    how.textContent =
      ' · ' + (d.reason || '').replace(/_/g, ' ') +
      (d.plant_t !== null ? ` · plant ${d.site || ''} at ${clock(d.plant_t)}` : '')
    head.append(how)
  }

  function buildMarks() {
    marks.replaceChildren()
    const d = state.data
    if (!d || !d.seconds) return
    d.events.forEach((e) => {
      if (e.kind !== 'kill' && e.kind !== 'bomb') return
      const i = document.createElement('i')
      i.className = e.kind === 'bomb' ? 'bomb' : e.side === 'ct' ? 'ct' : 't'
      i.style.left = `${(100 * e.t) / d.seconds}%`
      i.title = describe(e)
      marks.append(i)
    })
  }

  function describe(e: ReplayEvent) {
    if (e.kind === 'kill') {
      const how = [e.hs ? 'headshot' : '', e.wall ? 'wallbang' : '', e.smoke ? 'through smoke' : '',
        e.blind ? 'blind' : ''].filter(Boolean)
      return `${e.who} killed ${e.whom} (${gun(e.weapon)})` + (how.length ? ' · ' + how.join(', ') : '')
    }
    if (e.kind === 'bomb') {
      return e.event === 'plant' ? `${e.who} planted ${e.site || ''}`
        : e.event === 'defuse' ? `${e.who} defused` : 'bomb exploded'
    }
    return ''
  }

  // ---- the log --------------------------------------------------------------
  let feedRows: { el: HTMLElement; t: number }[] = []
  let lastScrolled: HTMLElement | null = null
  function renderFeed() {
    lastScrolled = null
    feedBox.replaceChildren()
    feedRows = []
    const d = state.data
    if (!d) return
    const shown = d.events.filter(
      (e) => e.kind === 'kill' || e.kind === 'bomb' || (state.damage && e.kind === 'hurt'),
    )
    shown.forEach((e) => {
      const row = document.createElement('div')
      row.className = 'row' + (e.kind === 'bomb' ? ' bomb' : e.kind === 'hurt' ? ' hurt' : '')
      const time = document.createElement('span')
      time.className = 'tm'
      time.textContent = clock(e.t)
      row.append(time)
      if (e.kind === 'kill' || e.kind === 'hurt') {
        const a = document.createElement('span')
        a.className = e.side === 'ct' ? 'ct' : 't'
        a.textContent = e.who || 'world'
        const w = document.createElement('span')
        w.className = 'w'
        // A kill reads like the game's: the gun, then how (through a wall or a
        // smoke, blind, headshot). A damage row carries the number and what it
        // left: 12 and 89 damage are different rounds.
        const url = equipmentUrl(e.weapon)
        const weapon = url ? iconEl(url, gun(e.weapon)) : document.createTextNode(gun(e.weapon))
        if (e.kind === 'kill') {
          w.className = 'w how'
          w.append(weapon)
          for (const [flag, label] of [['wall', 'through a wall'], ['smoke', 'through smoke'],
            ['blind', 'while blind'], ['hs', 'headshot']] as const) {
            if (e[flag]) w.append(iconEl(KILL_ICONS[flag], label))
          }
        } else {
          w.append(` ${e.dmg} [`, weapon, `${hit(e.hit) ? ' ' + hit(e.hit) : ''}] `)
        }
        const v = document.createElement('span')
        v.className = e.side === 'ct' ? 't' : 'ct'
        v.textContent = e.whom || ''
        row.append(a, w, v)
        if (e.kind === 'hurt') {
          const left = document.createElement('span')
          left.className = 'w'
          left.textContent = ` → ${e.left}`
          row.append(left)
        }
      } else {
        row.append(document.createTextNode(describe(e)))
      }
      on(row, 'click', () => seekTo(Math.max(0, e.t - 3)))
      feedBox.append(row)
      feedRows.push({ el: row, t: e.t })
    })
    if (!feedRows.length) {
      const none = document.createElement('p')
      none.className = 'help'
      none.textContent = 'Nothing happened in this round.'
      feedBox.append(none)
    }
  }

  function markFeed() {
    let current: HTMLElement | null = null
    feedRows.forEach((r) => {
      const future = r.t > state.t
      r.el.classList.toggle('dim', future)
      if (!future) current = r.el
    })
    // Follow the clock only while it runs; scrubbing must not yank the panel.
    // Only the log's own list scrolls: scrollIntoView would move the whole page
    // down to the log, which sits under the map.
    if (state.playing && current && current !== lastScrolled) {
      const row = current as HTMLElement
      const top = row.offsetTop - feedBox.offsetTop
      if (top < feedBox.scrollTop) feedBox.scrollTop = top
      else if (top + row.offsetHeight > feedBox.scrollTop + feedBox.clientHeight)
        feedBox.scrollTop = top + row.offsetHeight - feedBox.clientHeight
      lastScrolled = current
    }
  }

  function clock(t: number) {
    const s = Math.max(0, Math.floor(t))
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
  }

  // ---- drawing --------------------------------------------------------------
  // Shortest-path interpolation between two headings (350° → 10° turns 20°).
  function lerpAngle(a: number | null | undefined, b: number | null | undefined, k: number) {
    if (a === null || a === undefined) return b === null || b === undefined ? null : b
    if (b === null || b === undefined) return a
    const delta = ((((b - a + 180) % 360) + 360) % 360) - 180
    return a + delta * k
  }

  function at(p: Player, f: number) {
    // Linear interpolation between the two 8 Hz frames either side of `f`.
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

  // What a player holds at frame `f`: the Loadout's Held weapon, or without one
  // the last weapon they fired.
  function heldAt(p: Player, f: number, t: number) {
    if (p.held) return changeAt(p.held, f)?.[1] || ''
    const fired = weaponAt(p, t)
    return fired ? gun(fired) : ''
  }

  // A player's row: the health bar, then the gun in their hands or on their
  // back, then armor, money and the rest of the Loadout, the Held weapon lit.
  // Rewritten only when something in it changed.
  function renderRow(chip: Chip, p: Player, f: number, hp: number) {
    const gear = changeAt(p.gear, f)
    const inv = changeAt(p.inv, f)?.[1] || []
    const held = changeAt(p.held, f)?.[1] || ''
    const key = `${hp}|${gear?.slice(1).join(',')}|${inv.join(',')}|${held}`
    if (key === chip.shown) return
    chip.shown = key
    chip.hp.textContent = String(hp)
    chip.fill.style.width = `${hp}%`
    chip.el.classList.toggle('low', hp <= 25)
    if (!chip.gun || !chip.kit) return

    const guns = inv.filter((item) => !NADES.has(item) && item !== 'C4' && item !== 'zeus')
    const main = guns.find((g) => !PISTOLS.has(g)) || guns[0] || ''
    chip.gun.innerHTML = main ? iconHtml(main) : ''
    chip.gun.classList.toggle('on', !!main && main === held)

    const [, armor, helmet, kit, money] = gear || [0, 0, 0, 0, 0]
    const parts: HTMLElement[] = []
    const add = (cls: string, html: string, on = false, title = '') => {
      const el = document.createElement('span')
      el.className = cls + (on ? ' on' : '')
      el.innerHTML = html
      if (title) el.title = title
      parts.push(el)
      return el
    }
    add(`rp-armor${armor ? '' : ' none'}`,
      iconHtml(helmet ? 'armor_helmet' : 'armor', helmet ? 'armor + helmet' : 'armor') + `<em>${armor}</em>`)
    add('rp-money', `$${money.toLocaleString('en-US')}`)
    const rest = document.createElement('span')
    rest.className = 'rp-rest'
    for (const g of guns) if (g !== main) add('rp-side', iconHtml(g), g === held)
    if (held === 'knife') add('rp-side', iconHtml('knife'), true)
    for (const item of inv) if (NADES.has(item)) add('rp-nade', iconHtml(item), item === held)
    if (inv.includes('zeus')) add('rp-side', iconHtml('zeus'), held === 'zeus')
    if (inv.includes('C4')) add('rp-icon c4', iconHtml('C4', 'bomb'), held === 'C4')
    if (kit) add('rp-icon kit', iconHtml('defuser', 'defuse kit'))
    rest.append(...parts.splice(2))
    chip.kit.replaceChildren(...parts, rest)
  }

  function weaponAt(p: Player, t: number) {
    let held = ''
    for (const w of p.weapons) {
      if (w[0] <= t) held = w[1]
      else break
    }
    return held
  }

  // Blindness 0..1: 1 the instant the flash lands, fading over the player's
  // own blind duration (from the demo's flash_duration).
  function blindAt(p: Player, f: number, hz: number) {
    let onset: [number, number] | null = null
    for (const b of p.blind || []) {
      if (b[0] <= f) onset = b
      else break
    }
    if (!onset) return 0
    const elapsed = (f - onset[0]) / hz
    return elapsed >= 0 && elapsed < onset[1] ? 1 - elapsed / onset[1] : 0
  }

  // A blinded dot pales toward white rather than losing its side colour.
  function paleTint(hex: string, k: number) {
    const n = parseInt(hex.slice(1), 16)
    const r = (n >> 16) & 255
    const g = (n >> 8) & 255
    const b = n & 255
    return `rgb(${Math.round(r + (255 - r) * k)},${Math.round(g + (255 - g) * k)},${Math.round(b + (255 - b) * k)})`
  }

  function drawPlate(floor: Floor) {
    const img = plateFor(floor)
    if (!img) return
    ctx.drawImage(img, 0, 0, W, H)
    ctx.fillStyle = RADAR_VEIL
    ctx.fillRect(0, 0, W, H)
  }

  function draw() {
    if (destroyed) return
    ctx.clearRect(0, 0, W, H)
    ctx.fillStyle = '#0d1116'
    ctx.fillRect(0, 0, W, H)

    const d = state.data
    if (!d) {
      drawPlate(null)
      return
    }
    const t = state.t
    const f = Math.min(t * d.hz, d.frames - 1)
    const floor = LEVELS.length && d.levels && d.levels.length ? shownFloor(f, t) : null
    markFloor(floor)
    drawPlate(floor)

    if (state.labels) drawCallouts(floor)
    if (state.util) drawEffects(t, floor)
    if (state.util) drawNades(t, floor)
    if (state.shots) drawShots(t, floor)
    drawKills(t, floor)
    if (state.trails) drawTrails(f, floor)
    drawPlayers(f, t, floor)

    $('rp-clock').textContent = clock(t)
    timeEl.textContent = `${clock(t)} / ${clock(d.seconds)}`
    syncTransport()
    d.players.forEach((p) => {
      const s = at(p, f)
      const alive = !!(s && s.hp > 0)
      const chip = state.chips[p.sid]
      if (chip) {
        chip.el.classList.toggle('dead', !alive)
        renderRow(chip, p, Math.floor(f), alive && s ? s.hp : 0)
        const blind = blindAt(p, f, d.hz)
        chip.label.style.color = blind > 0 ? paleTint(p.colour, 0.85 * blind) : p.colour
      }
    })
    const note = $('rp-note')
    if (d.plant_t === null || t < d.plant_t) {
      note.textContent = ''
      note.className = 'alive'
    } else {
      const left = Math.max(0, 40 - (t - d.plant_t))
      note.textContent = `bomb ${d.site || ''} · ${left.toFixed(1)}s`
      note.className = 'alive bombclock'
    }
  }

  function drawCallouts(floor: Floor) {
    // The floor's own callouts: Nuke's Ramp is two rooms 308 units apart.
    const labels = floor !== null && LEVELS[floor] ? LEVELS[floor].labels : scene.labels
    ctx.save()
    ctx.font = '600 11px ui-monospace, Menlo, monospace'
    ctx.fillStyle = 'rgba(226, 232, 237, .42)'
    ctx.textAlign = 'center'
    ;(labels || []).forEach((l) => ctx.fillText(l.name, px(l.x), py(l.y)))
    ctx.restore()
  }

  function drawEffects(t: number, floor: Floor) {
    state.data!.effects.forEach((e) => {
      if (t < e.t0 || t > e.t1) return
      // A cloud on the other floor is a hint that it is there, not a wall.
      const onF = onFloor(e.lvl, floor) ? 1 : 0.3

      if (e.kind === 'flash' || e.kind === 'he') {
        // A pop: brightest the instant it lands, fading as a ring expands.
        const k = (t - e.t0) / Math.max(0.001, e.t1 - e.t0)
        const fade = (1 - k) * onF
        const ring = e.r * UNIT * (0.25 + 0.75 * k)
        ctx.beginPath()
        ctx.arc(px(e.x), py(e.y), ring, 0, Math.PI * 2)
        if (e.kind === 'flash') {
          ctx.fillStyle = `rgba(245, 245, 225, ${0.38 * fade})`
          ctx.strokeStyle = `rgba(250, 250, 235, ${0.85 * fade})`
          ctx.lineWidth = 2.4
        } else {
          ctx.fillStyle = `rgba(224, 118, 58, ${0.3 * fade})`
          ctx.strokeStyle = `rgba(245, 160, 90, ${0.8 * fade})`
          ctx.lineWidth = 2
        }
        ctx.fill()
        ctx.stroke()
        return
      }

      const fade = Math.min(1, (e.t1 - t) / 1.5) * onF
      ctx.beginPath()
      ctx.arc(px(e.x), py(e.y), e.r * UNIT, 0, Math.PI * 2)
      if (e.kind === 'smoke') {
        ctx.fillStyle = `rgba(190, 200, 210, ${0.3 * fade})`
        ctx.strokeStyle = `rgba(210, 220, 230, ${0.45 * fade})`
      } else {
        ctx.fillStyle = `rgba(214, 108, 48, ${0.26 * fade})`
        ctx.strokeStyle = `rgba(232, 140, 70, ${0.55 * fade})`
      }
      ctx.fill()
      ctx.lineWidth = 1.5
      ctx.stroke()
    })
  }

  function drawNades(t: number, floor: Floor) {
    state.data!.nades.forEach((n) => {
      // In the air, then held a moment where it landed.
      if (t < n.t0 || t > n.t1 + 1.2) return
      const colour = NADE_COLOUR[n.kind] || NADE_COLOUR.nade
      const span = Math.max(0.001, n.t1 - n.t0)
      const k = Math.min(1, (t - n.t0) / span)
      const upto = Math.max(1, Math.round(k * (n.x.length - 1)))
      // Dimmed by where it is *now*, so a throw about to arrive stays visible.
      const here = onFloor(n.lvl ? n.lvl[upto] : null, floor)
      const shade = here ? 1 : 0.3
      ctx.save()
      ctx.strokeStyle = colour
      ctx.globalAlpha = 0.55 * shade
      ctx.lineWidth = 1.4
      ctx.setLineDash([4, 3])
      ctx.beginPath()
      ctx.moveTo(px(n.x[0]), py(n.y[0]))
      for (let i = 1; i <= upto; i++) ctx.lineTo(px(n.x[i]), py(n.y[i]))
      ctx.stroke()
      ctx.restore()

      ctx.save()
      ctx.globalAlpha = shade
      ctx.beginPath()
      ctx.arc(px(n.x[upto]), py(n.y[upto]), 3.5, 0, Math.PI * 2)
      ctx.fillStyle = colour
      ctx.fill()
      ctx.restore()
    })
  }

  function drawShots(t: number, floor: Floor) {
    state.data!.events.forEach((e) => {
      if (e.kind !== 'shot' || e.x === null || e.y === null) return
      const age = t - e.t
      if (age < 0 || age > 0.45) return
      const alpha = 0.75 * (1 - age / 0.45) * (onFloor(e.lvl, floor) ? 1 : 0.3)
      ctx.beginPath()
      ctx.arc(px(e.x), py(e.y), 5.5, 0, Math.PI * 2)
      ctx.strokeStyle = (e.side === 'ct' ? 'rgba(140, 190, 235, ' : 'rgba(235, 190, 130, ') + alpha + ')'
      ctx.lineWidth = 1.6
      ctx.stroke()
    })
  }

  // A shot between floors belongs to both: drawn on both and marked.
  const crossFloor = (e: ReplayEvent) =>
    e.lvl !== null && e.lvl !== undefined && e.vlvl !== null && e.vlvl !== undefined && e.lvl !== e.vlvl

  function drawKills(t: number, floor: Floor) {
    const d = state.data!
    d.events.forEach((e) => {
      if (e.kind === 'hurt') {
        // Damage is a line from shooter to victim: who is trading with whom.
        const age = t - e.t
        if (age < 0 || age > 0.6 || e.x === null || e.y === null || e.vx == null || e.vy == null) return
        const cross = crossFloor(e)
        if (!cross && !onFloor(e.lvl, floor) && !onFloor(e.vlvl, floor)) return
        ctx.save()
        ctx.globalAlpha = 0.5 * (1 - age / 0.6)
        ctx.strokeStyle = e.side === 'ct' ? '#5b9bd8' : '#d39a55'
        ctx.lineWidth = 1.2
        if (cross) ctx.setLineDash([3, 3])
        ctx.beginPath()
        ctx.moveTo(px(e.x), py(e.y))
        ctx.lineTo(px(e.vx), py(e.vy))
        ctx.stroke()
        ctx.restore()
        return
      }
      if (e.kind !== 'kill' || e.vx == null || e.vy == null) return
      const age = t - e.t
      if (age < 0) return
      const cross = crossFloor(e)
      // The cross is where the body is, so it follows the victim's floor.
      if (!cross && !onFloor(e.vlvl, floor)) return
      const fresh = Math.max(0, 1 - age / 6)
      ctx.save()
      ctx.globalAlpha = (0.25 + 0.6 * fresh) * (onFloor(e.vlvl, floor) ? 1 : 0.35)
      ctx.strokeStyle = '#cf6a56'
      ctx.lineWidth = 1.8
      const x = px(e.vx)
      const y = py(e.vy)
      const r = 4.5
      ctx.beginPath()
      ctx.moveTo(x - r, y - r)
      ctx.lineTo(x + r, y + r)
      ctx.moveTo(x + r, y - r)
      ctx.lineTo(x - r, y + r)
      ctx.stroke()
      if (cross) {
        ctx.font = '600 10px ui-monospace, Menlo, monospace'
        ctx.fillStyle = '#cf6a56'
        ctx.textAlign = 'left'
        ctx.fillText('↕', x + r + 2, y + 3)
      }
      ctx.restore()
    })
    if (d.plant_t !== null && t >= d.plant_t) {
      const plantEvent = d.events.find((e) => e.kind === 'bomb' && e.event === 'plant')
      if (plantEvent && plantEvent.x !== null && plantEvent.y !== null) {
        const blink = 0.55 + 0.45 * Math.sin(t * 6)
        ctx.save()
        ctx.globalAlpha = blink * (onFloor(plantEvent.lvl, floor) ? 1 : 0.3)
        ctx.fillStyle = '#cf6a56'
        ctx.beginPath()
        ctx.arc(px(plantEvent.x), py(plantEvent.y), 5, 0, Math.PI * 2)
        ctx.fill()
        ctx.restore()
      }
    }
  }

  function drawTrails(f: number, floor: Floor) {
    const last = Math.floor(f)
    state.data!.players.forEach((p) => {
      const from = Math.max(0, last - TRAIL_FRAMES)
      // Runs that share a floor, joined at the seam, so a descent reads as one.
      const runs: { here: boolean; points: [number, number][] }[] = []
      let run: { here: boolean; points: [number, number][] } | null = null
      for (let i = from; i <= last; i++) {
        const x = p.x[i]
        const y = p.y[i]
        if (x === null || y === null) {
          run = null
          continue
        }
        const here = onFloor(playerFloorAt(p, i), floor)
        if (!run || run.here !== here) {
          const seam: [number, number] | null = run && run.points.length ? run.points[run.points.length - 1] : null
          run = { here, points: seam ? [seam] : [] }
          runs.push(run)
        }
        run.points.push([x, y])
      }
      ctx.save()
      ctx.strokeStyle = p.colour
      ctx.lineWidth = 1.6
      runs.forEach((r) => {
        if (r.points.length < 2) return
        ctx.globalAlpha = r.here ? 0.32 : 0.1
        ctx.beginPath()
        r.points.forEach((q, i) => (i ? ctx.lineTo(px(q[0]), py(q[1])) : ctx.moveTo(px(q[0]), py(q[1]))))
        ctx.stroke()
      })
      ctx.restore()
    })
  }

  function drawPlayers(f: number, t: number, floor: Floor) {
    const d = state.data!
    d.players.forEach((p) => {
      const s = at(p, f)
      if (!s) return
      const x = px(s.x)
      const y = py(s.y)
      const dead = s.hp <= 0
      // A man on the other floor is dimmed, never dropped.
      const theirFloor = playerFloorAt(p, Math.floor(f))
      const away = !onFloor(theirFloor, floor)
      ctx.save()
      if (dead) {
        // The body stays where it fell: where a side died is the round.
        ctx.globalAlpha = away ? 0.12 : 0.28
        ctx.strokeStyle = p.colour
        ctx.lineWidth = 1.4
        ctx.beginPath()
        ctx.moveTo(x - 3, y - 3)
        ctx.lineTo(x + 3, y + 3)
        ctx.moveTo(x + 3, y - 3)
        ctx.lineTo(x - 3, y + 3)
        ctx.stroke()
        ctx.restore()
        return
      }
      if (away) {
        ctx.globalAlpha = 0.28
        ctx.beginPath()
        ctx.arc(x, y, 4.5, 0, Math.PI * 2)
        ctx.fillStyle = p.colour
        ctx.fill()
        ctx.globalAlpha = 0.6
        ctx.font = '600 9px ui-monospace, Menlo, monospace'
        ctx.fillStyle = p.colour
        ctx.textAlign = 'left'
        ctx.fillText((theirFloor ?? 0) > (floor ?? 0) ? '▼' : '▲', x + 5.5, y - 3)
        ctx.restore()
        return
      }

      const blind = blindAt(p, f, d.hz)
      const dotColour = blind > 0 ? paleTint(p.colour, 0.85 * blind) : p.colour
      if (blind > 0) {
        ctx.beginPath()
        ctx.arc(x, y, 12.5 + 5 * blind, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(245, 245, 232, ${0.3 * blind})`
        ctx.fill()
      }

      ctx.beginPath()
      ctx.arc(x, y, 6.5, 0, Math.PI * 2)
      ctx.fillStyle = dotColour
      ctx.fill()
      ctx.lineWidth = 1.4
      ctx.strokeStyle = 'rgba(13, 17, 22, .85)'
      ctx.stroke()

      // Which way he is looking: a small triangle on the dot's edge.
      if (s.dir !== null && s.dir !== undefined) {
        const rad = facingRad(s.dir)
        const fx = Math.cos(rad)
        const fy = Math.sin(rad)
        const nx = -fy
        const ny = fx
        const base = 6.5
        const tip = 15
        const half = 4
        ctx.beginPath()
        ctx.moveTo(x + fx * tip, y + fy * tip)
        ctx.lineTo(x + fx * base + nx * half, y + fy * base + ny * half)
        ctx.lineTo(x + fx * base - nx * half, y + fy * base - ny * half)
        ctx.closePath()
        ctx.fillStyle = dotColour
        ctx.fill()
        ctx.lineWidth = 1
        ctx.strokeStyle = 'rgba(13, 17, 22, .75)'
        ctx.stroke()
      }

      // Health as an arc around the dot.
      if (s.hp < 100) {
        ctx.beginPath()
        ctx.arc(x, y, 9.5, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * (s.hp / 100))
        ctx.strokeStyle = s.hp > 50 ? '#4fa77f' : s.hp > 20 ? '#d39a55' : '#cf6a56'
        ctx.lineWidth = 2
        ctx.stroke()
      }

      if (state.names) {
        const held = heldAt(p, Math.floor(f), t)
        const icon = held ? canvasIcon(held, draw) : null
        ctx.font = '600 11.5px ui-monospace, Menlo, monospace'
        ctx.textAlign = 'left'
        ctx.fillStyle = 'rgba(13, 17, 22, .72)'
        // The Held weapon's icon after the name; its name while it has none.
        const text = p.name + (held && !icon ? ' · ' + held : '') + (blind > 0 ? ' ✦' : '')
        const tw = ctx.measureText(text).width
        const iw = icon ? (icon.naturalWidth / icon.naturalHeight) * ICON_H : 0
        const w = tw + (icon ? ICON_GAP + iw : 0)
        ctx.fillRect(x - w / 2 - 3, y - 24, w + 6, 14)
        ctx.fillStyle = dotColour
        ctx.fillText(text, x - w / 2, y - 13)
        if (icon) ctx.drawImage(icon, x - w / 2 + tw + ICON_GAP, y - 22.5, iw, ICON_H)
      }
      ctx.restore()
    })
  }

  // ---- playback -------------------------------------------------------------
  const playButton = $<HTMLButtonElement>('rp-play')
  function setPlay() {
    const label = state.playing ? 'Pause' : 'Play'
    playButton.classList.toggle('playing', state.playing)
    playButton.setAttribute('aria-label', label)
    playButton.title = `${label} (space)`
  }

  // Like a music player: back restarts the round once it is under way, and only
  // goes to the round before from (near) its start.
  const RESTART_AFTER = 3
  function syncTransport() {
    const i = ROUNDS.indexOf(state.round ?? -1)
    prevButton.disabled = i <= 0 && state.t <= RESTART_AFTER
    nextButton.disabled = i < 0 || i >= ROUNDS.length - 1
  }

  function seekTo(t: number) {
    const d = state.data
    if (!d) return
    state.t = Math.max(0, Math.min(d.seconds, t))
    seek.value = String(Math.round(state.t * 100))
    markFeed()
    draw()
  }

  function tick(now: number) {
    if (destroyed) return
    if (state.playing && state.data) {
      const dt = (now - state.last) / 1000
      state.last = now
      state.t += dt * state.speed
      if (state.t >= state.data.seconds) {
        state.t = state.data.seconds
        state.playing = false
        setPlay()
      }
      seek.value = String(Math.round(state.t * 100))
      markFeed()
      draw()
    } else {
      state.last = now
    }
    frame = requestAnimationFrame(tick)
  }
  frame = requestAnimationFrame(tick)

  const onPlay = () => {
    if (!state.data) return
    if (state.t >= state.data.seconds) state.t = 0
    state.playing = !state.playing
    state.last = performance.now()
    setPlay()
  }
  on(playButton, 'click', onPlay)

  on(seek, 'input', () => {
    state.playing = false
    setPlay()
    state.t = Number(seek.value) / 100
    markFeed()
    draw()
  })

  const speedBox = $('rp-speeds')
  speedBox.replaceChildren()
  for (const sp of [0.25, 0.5, 1, 2, 4]) {
    const b = document.createElement('button')
    b.type = 'button'
    b.textContent = `${sp}x`
    b.className = sp === 1 ? 'on' : ''
    on(b, 'click', () => {
      state.speed = sp
      ;[...speedBox.children].forEach((c) => c.classList.toggle('on', c === b))
    })
    speedBox.append(b)
  }

  const toggles: [string, 'names' | 'trails' | 'util' | 'shots' | 'labels'][] = [
    ['rp-names', 'names'], ['rp-trails', 'trails'], ['rp-util', 'util'], ['rp-shots', 'shots'],
    ['rp-labels', 'labels'],
  ]
  for (const [id, key] of toggles) {
    const box = $<HTMLInputElement>(id)
    on(box, 'change', () => {
      state[key] = box.checked
      draw()
    })
  }

  if (floorBox) on(floorBox, 'click', (e) => {
    const b = (e.target as HTMLElement).closest<HTMLElement>('[data-floor]')
    if (b) setFloor(b.dataset.floor === 'auto' ? 'auto' : Number(b.dataset.floor))
  })

  const dmgBox = $<HTMLInputElement>('rp-dmg')
  on(dmgBox, 'change', () => {
    state.damage = dmgBox.checked
    renderFeed()
    markFeed()
  })

  on($('rp-rounds'), 'click', (e) => {
    const b = (e.target as HTMLElement).closest<HTMLElement>('[data-round]')
    if (b) void load(Number(b.dataset.round))
  })

  function step(delta: number) {
    if (delta < 0 && state.data && state.t > RESTART_AFTER) {
      seekTo(0)
      return
    }
    const i = ROUNDS.indexOf(state.round ?? -1)
    const next = ROUNDS[Math.max(0, Math.min(ROUNDS.length - 1, i + delta))]
    if (next && next !== state.round) void load(next)
  }
  on(prevButton, 'click', () => step(-1))
  on(nextButton, 'click', () => step(1))

  const onKey = (e: KeyboardEvent) => {
    if ((e.target as HTMLElement).matches('input, textarea, select')) return
    if (e.key === ' ') {
      e.preventDefault()
      onPlay()
    } else if (e.key === 'ArrowRight') {
      e.preventDefault()
      seekTo(state.t + (e.shiftKey ? 1 : 5))
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault()
      seekTo(state.t - (e.shiftKey ? 1 : 5))
    } else if (e.key === '[') step(-1)
    else if (e.key === ']') step(1)
    else if (LEVELS.length && e.key === 'v') {
      const order: ('auto' | number)[] = ['auto', ...LEVELS.map((_, i) => i)]
      const i = order.findIndex((o) => String(o) === String(state.floor))
      setFloor(order[(i + 1) % order.length])
    } else if (LEVELS.length && /^[1-9]$/.test(e.key) && Number(e.key) <= LEVELS.length) {
      setFloor(Number(e.key) - 1)
    }
  }
  on(document, 'keydown', onKey as EventListener)

  draw()
  if (ROUNDS.length) void load(startRound && ROUNDS.includes(startRound) ? startRound : ROUNDS[0])

  return () => {
    destroyed = true
    cancelAnimationFrame(frame)
    abort.abort()
  }
}

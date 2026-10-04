// CS2's own equipment and kill-feed icons (white on transparent), served from
// public/icons/. They are Valve's, taken from the game files through
// github.com/Juknum/counter-strike-icons: see public/icons/NOTICE.md.

const EQUIPMENT = [
  'ak47', 'm4a1', 'm4a1_silencer', 'awp', 'usp_silencer', 'p2000', 'hkp2000', 'glock', 'deagle',
  'galilar', 'famas', 'mp9', 'mac10', 'mp7', 'mp5sd', 'ump45', 'p90', 'bizon', 'elite', 'fiveseven',
  'tec9', 'cz75a', 'p250', 'revolver', 'ssg08', 'aug', 'sg556', 'nova', 'xm1014', 'sawedoff', 'mag7',
  'negev', 'm249', 'g3sg1', 'scar20', 'hegrenade', 'flashbang', 'smokegrenade', 'molotov',
  'incgrenade', 'inferno', 'decoy', 'knife', 'taser', 'world', 'c4', 'planted_c4', 'defuser', 'armor',
  'armor_helmet',
]

// Every other name a gun reaches the page under: the Loadout's labels (AK-47,
// M4A1-S, Deagle, flash), the kill feed's keys (usp/p2000) and their short labels.
const ALIASES: Record<string, string> = {
  usps: 'usp_silencer', usp: 'usp_silencer', uspp2000: 'usp_silencer', m4a1s: 'm4a1_silencer',
  m4a4: 'm4a1', m4: 'm4a1', glock18: 'glock', deserteagle: 'deagle', duals: 'elite',
  dualberettas: 'elite', cz: 'cz75a', cz75auto: 'cz75a', r8: 'revolver', r8revolver: 'revolver',
  galil: 'galilar', scout: 'ssg08', sg: 'sg556', sg553: 'sg556', ppbizon: 'bizon', ump: 'ump45',
  zeus: 'taser', zeusx27: 'taser', flash: 'flashbang', smoke: 'smokegrenade', he: 'hegrenade',
  highexplosivegrenade: 'hegrenade', incendiary: 'incgrenade', incendiarygrenade: 'incgrenade',
  decoygrenade: 'decoy', fire: 'inferno', themap: 'world', c4explosive: 'c4', bomb: 'c4', kit: 'defuser',
}

const norm = (name: string) => name.toLowerCase().replace(/[^a-z0-9]/g, '')
const FILES: Record<string, string> = Object.fromEntries(EQUIPMENT.map((f) => [norm(f), f]))

/** The icon's URL for a gun, grenade or piece of gear, or null when there is none. */
export function equipmentUrl(name?: string | null): string | null {
  if (!name) return null
  const key = norm(name)
  const file = FILES[key] ?? ALIASES[key]
  return file ? `/icons/equipment/${file}.svg` : null
}

export const KILL_ICONS = {
  wall: '/icons/deathnotice/penetrate.svg',
  smoke: '/icons/deathnotice/smoke_kill.svg',
  blind: '/icons/deathnotice/blind_kill.svg',
  hs: '/icons/deathnotice/icon_headshot.svg',
}

const escape = (s: string) =>
  s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!)

/** An `<img>` for this item, its name as the tooltip; the name as text when there is no icon. */
export function iconHtml(name: string, label = name): string {
  const url = equipmentUrl(name)
  const text = escape(label)
  return url ? `<img class="gi" src="${url}" alt="${text}" title="${text}">` : text
}

/** The same as an element. */
export function iconEl(url: string, label: string): HTMLImageElement {
  const img = document.createElement('img')
  img.className = 'gi'
  img.src = url
  img.alt = label
  img.title = label
  return img
}

// Images for the canvas, loaded once per page; `onReady` redraws when one lands.
const loaded = new Map<string, HTMLImageElement>()
export function canvasIcon(name: string, onReady: () => void): HTMLImageElement | null {
  const url = equipmentUrl(name)
  if (!url) return null
  let img = loaded.get(url)
  if (!img) {
    img = new Image()
    img.src = url
    loaded.set(url, img)
  }
  if (img.complete && img.naturalWidth) return img
  img.addEventListener('load', onReady, { once: true })
  return null
}

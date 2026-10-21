// AS-5: a reply's Round tokens, [R14], [R14 1:23], [R14 1:23 @<steamid>] or
// [4021.2:R14], split out of its text with the Replay link each one opens. A
// bare [R14] is of the Match Map the question was asked on; without one it
// has no link.

export interface MapAt {
  match: number
  map: number
}

export interface RoundToken {
  label: string
  to: string | null
}

const TOKEN = /\[(?:(\d+)\.(\d+):)?R(\d{1,2})(?: (\d{1,2}):(\d{2}))?(?: @(\d{5,20}))?\]/g

function href(token: RegExpMatchArray, at: MapAt | null | undefined): string | null {
  const [, match, map, round, min, sec, sid] = token
  const where = match && map ? { match: Number(match), map: Number(map) } : at
  if (!where) return null
  const query = new URLSearchParams({ round })
  if (min !== undefined) query.set('t', String(Number(min) * 60 + Number(sec)))
  if (sid) query.set('player', sid)
  return `/matches/${where.match}/m/${where.map}?${query}`
}

/** The text in order: plain strings, and a token wherever one was written. */
export function segments(text: string, at?: MapAt | null): (string | RoundToken)[] {
  const out: (string | RoundToken)[] = []
  let last = 0
  for (const m of text.matchAll(TOKEN)) {
    if (m.index > last) out.push(text.slice(last, m.index))
    out.push({ label: `R${m[3]}${m[4] !== undefined ? ` ${m[4]}:${m[5]}` : ''}`, to: href(m, at) })
    last = m.index + m[0].length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

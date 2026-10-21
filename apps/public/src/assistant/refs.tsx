// AS-5: Round tokens in a reply, [R14], [R14 1:23], [R14 1:23 @<steamid>] or
// [4021.2:R14], become links that open the Replay at that Round (and second,
// and Player). A bare [R14] is of the Match Map the question was asked on;
// without one it stays text.
import type { ReactNode } from 'react'
import { Link } from 'react-router'

export interface MapAt {
  match: number
  map: number
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

export function WithRefs({ text, at }: { text: string; at?: MapAt | null }): ReactNode {
  const out: ReactNode[] = []
  let last = 0
  for (const m of text.matchAll(TOKEN)) {
    const to = href(m, at)
    if (m.index > last) out.push(text.slice(last, m.index))
    const label = `R${m[3]}${m[4] !== undefined ? ` ${m[4]}:${m[5]}` : ''}`
    out.push(
      to ? (
        <Link key={m.index} to={to} className="rounded bg-raised px-1 font-mono text-xs text-ct hover:underline">
          ▶ {label}
        </Link>
      ) : (
        <span key={m.index} className="font-mono text-xs text-ink-2">
          {label}
        </span>
      ),
    )
    last = m.index + m[0].length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

// A Fixture's Lineups (CONTEXT.md) live in the page's URL as Steam ids, so a
// picked plan is a link like any other: ?mine=…&theirs=…, each side optional.
// The API takes them as my_lineup / their_lineup. The window (TM-3, ?since=day)
// rides along the same way: a plan read since a patch is a link too.

export interface Lineups {
  mine: string[]
  theirs: string[]
  since?: string
}

const ids = (raw: string | null) => (raw ?? '').split(',').filter((s) => /^\d{1,20}$/.test(s)).slice(0, 5)

export function readLineups(params: URLSearchParams): Lineups {
  const since = params.get('since') ?? ''
  const out: Lineups = { mine: ids(params.get('mine')), theirs: ids(params.get('theirs')) }
  if (/^\d{4}-\d{2}-\d{2}$/.test(since)) out.since = since
  return out
}

/** The query string to keep on every link of the page: "" when neither side is picked. */
export function lineupSearch(l: Lineups): string {
  const parts = []
  if (l.mine.length) parts.push(`mine=${l.mine.join(',')}`)
  if (l.theirs.length) parts.push(`theirs=${l.theirs.join(',')}`)
  if (l.since) parts.push(`since=${l.since}`)
  return parts.length ? `?${parts.join('&')}` : ''
}

/** The API's query parameters; a side left out is the Team's most recent five. */
export function lineupQuery(l: Lineups): { my_lineup?: string; their_lineup?: string; since?: string } {
  return {
    ...(l.mine.length ? { my_lineup: l.mine.join(',') } : {}),
    ...(l.theirs.length ? { their_lineup: l.theirs.join(',') } : {}),
    ...(l.since ? { since: l.since } : {}),
  }
}

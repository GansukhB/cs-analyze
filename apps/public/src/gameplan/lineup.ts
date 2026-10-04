// A Fixture's Lineups (CONTEXT.md) live in the page's URL as Steam ids, so a
// picked plan is a link like any other: ?mine=…&theirs=…, each side optional.
// The API takes them as my_lineup / their_lineup.

export interface Lineups {
  mine: string[]
  theirs: string[]
}

const ids = (raw: string | null) => (raw ?? '').split(',').filter((s) => /^\d{1,20}$/.test(s)).slice(0, 5)

export function readLineups(params: URLSearchParams): Lineups {
  return { mine: ids(params.get('mine')), theirs: ids(params.get('theirs')) }
}

/** The query string to keep on every link of the page: "" when neither side is picked. */
export function lineupSearch(l: Lineups): string {
  const parts = []
  if (l.mine.length) parts.push(`mine=${l.mine.join(',')}`)
  if (l.theirs.length) parts.push(`theirs=${l.theirs.join(',')}`)
  return parts.length ? `?${parts.join('&')}` : ''
}

/** The API's query parameters; a side left out is the Team's most recent five. */
export function lineupQuery(l: Lineups): { my_lineup?: string; their_lineup?: string } {
  return {
    ...(l.mine.length ? { my_lineup: l.mine.join(',') } : {}),
    ...(l.theirs.length ? { their_lineup: l.theirs.join(',') } : {}),
  }
}

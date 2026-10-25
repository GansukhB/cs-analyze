// Where a page's links go, from v1 or from inside v2 (/v2/t/:team/...): the
// pages both mount (Workspace, Briefings, Forecasts, Scouts, Uploads, the
// Stratbook) link through this, so a v1 page shown in v2 keeps the reader in v2.
import { useLocation } from 'react-router'

export interface Paths {
  /** The my team in the URL when inside v2, else null. */
  team: number | null
  briefings: () => string
  briefing: (id: string | number) => string
  briefingNew: (mine: number, theirs: number) => string
  jobs: () => string
  job: (publicId: string) => string
  scout: () => string
  uploads: () => string
  stratbook: () => string
  strat: (id: number) => string
  stratNew: (team: number) => string
  forecasts: () => string
  workspace: () => string
  gameplan: (mine: number, theirs: number) => string
  gameplanPick: () => string
  /** A Match, a Match Map, or a moment of one (`round`). */
  match: (id: number, map?: number | null, round?: number | null) => string
}

export function v2Team(pathname: string): number | null {
  const m = pathname.match(/^\/v2\/t\/(\d+)/)
  return m ? Number(m[1]) : null
}

export function pathsFor(team: number | null): Paths {
  const v2 = (...parts: (string | number)[]) => ['/v2/t', team, ...parts].join('/')
  if (team === null)
    return {
      team,
      briefings: () => '/briefings',
      briefing: (id) => `/briefings/${id}`,
      briefingNew: (mine, theirs) => `/gameplan/${mine}/vs/${theirs}/briefing`,
      jobs: () => '/jobs',
      job: (id) => `/jobs/${id}`,
      scout: () => '/',
      uploads: () => '/uploads',
      stratbook: () => '/stratbook',
      strat: (id) => `/stratbook/${id}`,
      stratNew: (t) => `/stratbook/new?team=${t}`,
      forecasts: () => '/forecasts',
      workspace: () => '/workspace',
      gameplan: (mine, theirs) => `/gameplan/${mine}/vs/${theirs}`,
      gameplanPick: () => '/gameplan',
      match: (id, map, round) => (map ? `/matches/${id}/m/${map}${round ? `?round=${round}` : ''}` : `/matches/${id}`),
    }
  return {
    team,
    briefings: () => v2('briefings'),
    briefing: (id) => v2('briefings', id),
    // A Briefing is made from the Game Plan of the my team in the URL.
    briefingNew: (_mine, theirs) => v2('briefings', 'new', theirs),
    jobs: () => v2('jobs'),
    job: (id) => v2('jobs', id),
    scout: () => v2('scout'),
    uploads: () => v2('uploads'),
    stratbook: () => v2('stratbook'),
    strat: (id) => v2('stratbook', id),
    stratNew: (t) => `${v2('stratbook', 'new')}?team=${t}`,
    forecasts: () => v2('forecasts'),
    workspace: () => v2('workspace'),
    gameplan: (mine, theirs) => (mine === team ? v2('gameplan', theirs) : `/gameplan/${mine}/vs/${theirs}`),
    gameplanPick: () => v2('gameplan'),
    // A moment opens the Replay; a Match Map its report; a Match its first Map's.
    match: (id, map, round) =>
      round ? `${v2('replay', id, map ?? 1)}?round=${round}` : v2('matches', id, 'm', map ?? 1),
  }
}

export function usePaths(): Paths {
  return pathsFor(v2Team(useLocation().pathname))
}

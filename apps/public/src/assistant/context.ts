// What page the Assistant was opened from (CONTEXT.md): a Game Plan's Fixture
// with its Lineups, a Team, or a Match. The names come from the queries those
// pages already made, under the same keys, so reading them costs no request.
import { matchPath, useLocation, useSearchParams } from 'react-router'
import { $api } from '../api/client'
import { lineupQuery, readLineups } from '../gameplan/lineup'
import type { ChatContext } from './api'

export type Scope = 'fixture' | 'team' | 'match' | 'player' | 'job' | 'picker' | 'general'

export interface PageContext {
  scope: Scope
  context: ChatContext | null
  /** "The MongolZ vs The Huns", a Team's name, or "" while it loads / for general. */
  label: string
  /** Changes whenever the page's subject does, so a reply knows what it was about. */
  key: string
}

const KEEP = { staleTime: Infinity }

/** A v2 page (/v2/t/:team/...) read as the v1 page about the same subject: a
 *  Fixture for scouting, the Game plan and a new Briefing, a Match Map for the
 *  report and the Replay, a Player, a Scout's job, else the my team itself. */
export function asV1(pathname: string): string {
  const v2 = pathname.match(/^\/v2\/t\/(\d+)(?:\/(.*))?$/)
  if (!v2) return pathname
  const [, team, rest = ''] = v2
  const [section, a, b, c] = rest.split('/')
  if ((section === 'gameplan' || section === 'scouting') && a) return `/gameplan/${team}/vs/${a}`
  if (section === 'briefings' && a === 'new' && b) return `/gameplan/${team}/vs/${b}`
  if (section === 'jobs' && a) return `/jobs/${a}`
  if (section === 'matches' && a && b === 'm' && c) return `/matches/${a}/m/${c}`
  if (section === 'replay' && a && b) return `/matches/${a}/m/${b}`
  if (section === 'players' && a) return `/players/${a}`
  return `/teams/${team}`
}

export function usePageContext(): PageContext {
  const pathname = asV1(useLocation().pathname)
  const [searchParams] = useSearchParams()
  const fixture = matchPath('/gameplan/:mine/vs/:theirs/*', pathname)
  const team = matchPath('/teams/:teamId', pathname)
  const match = matchPath('/matches/:matchId/*', pathname)
  const matchMap = matchPath('/matches/:matchId/m/:mapNumber', pathname)
  // AS-7: a Player page, a Scout's job page, the Game Plan picker.
  const playerPath = matchPath('/players/:steamid', pathname)
  const jobPath = matchPath('/jobs/:publicId', pathname)
  const isPicker = matchPath('/gameplan', pathname) !== null

  const mine = Number(fixture?.params.mine)
  const theirs = Number(fixture?.params.theirs)
  const lineups = readLineups(searchParams)
  const teamId = Number(team?.params.teamId)
  const matchId = Number(match?.params.matchId)
  const isFixture = Number.isFinite(mine) && Number.isFinite(theirs) && mine > 0 && theirs > 0
  const isTeam = !isFixture && Number.isFinite(teamId) && teamId > 0
  const isMatch = !isFixture && !isTeam && Number.isFinite(matchId) && matchId > 0

  const header = $api.useQuery(
    'get',
    '/gameplan/{mine}/vs/{theirs}',
    { params: { path: { mine: mine || 0, theirs: theirs || 0 }, query: lineupQuery(lineups) } },
    { ...KEEP, enabled: isFixture },
  )
  const teamDetail = $api.useQuery(
    'get',
    '/teams/{team_id}',
    { params: { path: { team_id: teamId || 0 } } },
    { ...KEEP, enabled: isTeam },
  )
  const matchInfo = $api.useQuery(
    'get',
    '/matches/{match_id}',
    { params: { path: { match_id: matchId || 0 } } },
    { ...KEEP, enabled: isMatch },
  )
  const steamid = playerPath?.params.steamid ?? ''
  const publicId = jobPath?.params.publicId ?? ''
  const playerPage = $api.useQuery('get', '/players/{steamid}', { params: { path: { steamid } } }, { ...KEEP, enabled: !!steamid })
  const jobPage = $api.useQuery('get', '/jobs/{public_id}', { params: { path: { public_id: publicId } } }, { enabled: !!publicId })

  if (isFixture) {
    const h = header.data
    return {
      scope: 'fixture',
      context: {
        mine,
        theirs,
        my_lineup: lineups.mine,
        their_lineup: lineups.theirs,
        page: h ? `${h.my_team.name} vs ${h.opponent.name}` : '',
      },
      label: h ? `${h.my_team.name} vs ${h.opponent.name}` : '',
      key: `f:${mine}:${theirs}:${lineups.mine.join(',')}:${lineups.theirs.join(',')}`,
    }
  }
  if (isTeam) {
    const name = teamDetail.data?.team.name ?? ''
    return { scope: 'team', context: { team: teamId, page: name }, label: name, key: `t:${teamId}` }
  }
  if (isMatch) {
    const m = matchInfo.data
    const label = m ? [m.team1?.name, m.team2?.name].filter(Boolean).join(' vs ') : ''
    const map = Number(matchMap?.params.mapNumber) || null
    // The Round open on the Replay rides along, so "this round" resolves; it is
    // not part of the key, which would otherwise change at every click.
    const round = map ? Number(searchParams.get('round')) || null : null
    return { scope: 'match', context: { match: matchId, map, round, page: label }, label, key: `m:${matchId}:${map ?? ''}` }
  }
  if (steamid) {
    const name = playerPage.data?.player.name ?? ''
    return { scope: 'player', context: { player: steamid, page: name }, label: name, key: `p:${steamid}` }
  }
  if (publicId) {
    const label = jobPage.data?.job.label ?? ''
    return { scope: 'job', context: { job: publicId, page: label }, label, key: `j:${publicId}` }
  }
  if (isPicker) return { scope: 'picker', context: { picker: true, page: 'Game Plan' }, label: 'Game Plan', key: 'pick' }
  return { scope: 'general', context: null, label: '', key: 'g' }
}

/** Questions worth one tap, for the page the Assistant was opened from. */
export function suggestions(scope: Scope): string[] {
  switch (scope) {
    case 'fixture':
      return [
        'Ямар map сонгож, алийг нь ban хийх вэ?',
        'Тэдний хамгийн аюултай тоглогч хэн бэ?',
        'Бидний T талын төлөвлөгөө ямар байх вэ?',
      ]
    case 'team':
      return ['Энэ багийн map pool ямар вэ?', 'Хэн ямар үүрэгтэй тоглодог вэ?', 'Хамгийн сул тоглогч нь хэн бэ?']
    case 'player':
      return ['Энэ тоглогчийн хүчтэй, сул тал юу вэ?', 'Аль map дээр хамгийн сайн тоглодог вэ?', 'Сүүлийн үеийн form ямар байна?']
    case 'job':
      return ['Энэ Scout хаана явж байна?', 'Дууссаны дараа юу хийх вэ?']
    case 'picker':
      return ['Манай одоогийн тав хэн бэ?', 'Шинэ тоглогч авбал хэнийг Lineup-д оруулах вэ?']
    case 'match':
      return [
        'Энэ map-ийг юунаас болж алдсан бэ?',
        'Хэн хамгийн их алдаа гаргасан бэ?',
        'Аль раунд тоглолтын эргэлт болсон бэ?',
      ]
    default:
      return ['Ямар багуудын өгөгдөл байна?', 'The MongolZ-ийн map pool ямар вэ?', 'Хамгийн их parse хийгдсэн баг аль нь вэ?']
  }
}

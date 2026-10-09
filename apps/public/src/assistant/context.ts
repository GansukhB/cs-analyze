// What page the Assistant was opened from (CONTEXT.md): a Game Plan's Fixture
// with its Lineups, a Team, or a Match. The names come from the queries those
// pages already made, under the same keys, so reading them costs no request.
import { matchPath, useLocation, useSearchParams } from 'react-router'
import { $api } from '../api/client'
import { lineupQuery, readLineups } from '../gameplan/lineup'
import type { ChatContext } from './api'

export type Scope = 'fixture' | 'team' | 'match' | 'general'

export interface PageContext {
  scope: Scope
  context: ChatContext | null
  /** "The MongolZ vs The Huns", a Team's name, or "" while it loads / for general. */
  label: string
  /** Changes whenever the page's subject does, so a reply knows what it was about. */
  key: string
}

const KEEP = { staleTime: Infinity }

export function usePageContext(): PageContext {
  const { pathname } = useLocation()
  const [searchParams] = useSearchParams()
  const fixture = matchPath('/gameplan/:mine/vs/:theirs/*', pathname)
  const team = matchPath('/teams/:teamId', pathname)
  const match = matchPath('/matches/:matchId/*', pathname)
  const matchMap = matchPath('/matches/:matchId/m/:mapNumber', pathname)

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

  if (isFixture) {
    const h = header.data
    return {
      scope: 'fixture',
      context: { mine, theirs, my_lineup: lineups.mine, their_lineup: lineups.theirs },
      label: h ? `${h.my_team.name} vs ${h.opponent.name}` : '',
      key: `f:${mine}:${theirs}:${lineups.mine.join(',')}:${lineups.theirs.join(',')}`,
    }
  }
  if (isTeam) {
    return { scope: 'team', context: { team: teamId }, label: teamDetail.data?.team.name ?? '', key: `t:${teamId}` }
  }
  if (isMatch) {
    const m = matchInfo.data
    const label = m ? [m.team1?.name, m.team2?.name].filter(Boolean).join(' vs ') : ''
    const map = Number(matchMap?.params.mapNumber) || null
    return { scope: 'match', context: { match: matchId, map }, label, key: `m:${matchId}:${map ?? ''}` }
  }
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

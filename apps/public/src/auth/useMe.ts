import { $api } from '../api/client'

// Who is signed in and for which club (GET /auth/me). The pages read "we" from
// the Workspace's my teams: the Scout form and the Game Plan picker start from them.
export function useMe() {
  return $api.useQuery('get', '/auth/me', {}, { staleTime: 5 * 60_000 })
}

export function useMyTeams() {
  return useMe().data?.workspace.my_teams ?? []
}

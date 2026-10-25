// "We" on a v2 page: the my team in the URL (/v2/t/:team/...), one of the
// Workspace's my teams (CONTEXT.md), and the links that keep it.
import { useParams } from 'react-router'
import { useMyTeams } from '../auth/useMe'

export function useTeam() {
  const { team = '' } = useParams()
  const mine = useMyTeams()
  const id = Number(team)
  const found = mine.find((t) => t.id === id)
  return { id, name: found?.name ?? '', label: found?.label ?? '', known: !!found, mine }
}

/** A v2 path for this my team: `at(id, 'players', sid)` → /v2/t/<id>/players/<sid>. */
export function at(teamId: number, ...parts: (string | number)[]): string {
  return ['/v2/t', teamId, ...parts].join('/')
}

export function initials(name: string): string {
  const words = name.trim().split(/\s+/)
  const two = words.length > 1 ? words[0][0] + words[1][0] : name.slice(0, 2)
  return two.toUpperCase()
}

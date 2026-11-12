// The v2 Playbook's shared pieces that are not components (v2/playbook.tsx):
// strength words, Staff's notes per Team and Map (GP-13), and the GP-9 view
// read off the page URL.
import { $api } from '../api/client'
import type { Strength } from '../gameplan/types'
import { GOOD, MUTED, WARN } from './format'

export const STRENGTH: Record<Strength, [string, string]> = {
  weak: ['Сул', MUTED],
  medium: ['Дунд', WARN],
  strong: ['Хүчтэй', GOOD],
}

// GP-13: Staff's notes on habit lines, theirs and our own, kept across parses.
export interface NoteBook {
  team: number
  map: string
  notes: Record<string, { text: string; by: string }>
  refresh: () => void
}

export function useNoteBook(team: number, map: string): NoteBook {
  const q = $api.useQuery('get', '/playbook-notes', { params: { query: { team_id: team, map_name: map } } }, { enabled: !!map })
  return { team, map, notes: q.data ?? {}, refresh: () => void q.refetch() }
}

export function viewQuery(search: URLSearchParams) {
  const buy = search.get('buy') ?? ''
  const days = Number(search.get('days') ?? 0)
  const score = search.get('score') ?? ''
  return {
    ...(buy === 'full' || buy === 'light' ? { buy } : {}),
    ...(days ? { days } : {}),
    ...(['ahead', 'close', 'behind'].includes(score) ? { score } : {}),
  }
}

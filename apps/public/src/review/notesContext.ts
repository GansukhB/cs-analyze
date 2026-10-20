// The match page's notes for one Match Map, shared by the Finding cards and the
// Round's notes box (RV-7).
import { createContext, useContext } from 'react'
import type { components } from '../api/schema'

export interface Actions {
  staff: boolean
  matchId: number
  mapNumber: number
  notes: components['schemas']['NoteRead'][]
  reasons: Record<string, string>
  refresh: () => void
}

export const NotesContext = createContext<Actions | null>(null)

export function useNotes() {
  return useContext(NotesContext)
}

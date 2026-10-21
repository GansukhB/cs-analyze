// The match page's notes for one Match Map, shared by the Finding cards and the
// Round's notes box (RV-7).
import { createContext, useContext } from 'react'
import type { components } from '../api/schema'
import type { Shape } from '../replay/player'

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

// VIZ-8: what the Round's notes box hands the Replay: the pen it holds, where a
// stroke goes, and the marks to show at a moment.
export interface PenHooks {
  pen: () => { kind: 'arrow' | 'circle' | 'text'; text: string } | null
  onShape: (shape: Shape) => void
  shapes: (round: number, t: number) => Shape[]
}

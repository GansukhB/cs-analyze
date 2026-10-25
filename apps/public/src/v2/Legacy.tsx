// A v1 page shown in the v2 frame (grilling 2026-10-25): remounted per my team,
// so a page that keeps the team in its state follows the switch, and dressed by
// the `.v2-legacy` rules in v2.css (the design's type, panels and tables).
import type { ReactNode } from 'react'
import { useParams } from 'react-router'

export default function Legacy({ children }: { children: ReactNode }) {
  const { team = '' } = useParams()
  return (
    <div key={team} className="v2-legacy">
      {children}
    </div>
  )
}

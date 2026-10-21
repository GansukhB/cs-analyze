// AS-5: a reply's Round tokens as links that open the Replay at that Round
// (and second, and Player); the parsing is roundTokens.ts.
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { type MapAt, segments } from './roundTokens'

export function WithRefs({ text, at }: { text: string; at?: MapAt | null }): ReactNode {
  return segments(text, at).map((part, i) =>
    typeof part === 'string' ? (
      part
    ) : part.to ? (
      <Link key={i} to={part.to} className="rounded bg-raised px-1 font-mono text-xs text-ct hover:underline">
        ▶ {part.label}
      </Link>
    ) : (
      <span key={i} className="font-mono text-xs text-ink-2">
        {part.label}
      </span>
    ),
  )
}

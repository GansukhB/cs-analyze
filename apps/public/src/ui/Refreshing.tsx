// The chip in the bottom-left corner, in both layouts, while some of the page is
// shown from before the latest parse (docs/adr/0014): it is current again on its
// own, nothing to press. Fixed, so it never pushes the header's menu around.
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useSyncExternalStore } from 'react'
import { answerOf, clockUb, oldest, type AnswerMark } from '../api/answers'

function useStaleOnScreen(): { count: number; at: string | null } {
  const cache = useQueryClient().getQueryCache()
  const subscribe = useCallback((onChange: () => void) => cache.subscribe(onChange), [cache])
  // A string, so the snapshot only changes when what it says does.
  const read = useCallback(() => {
    const marks = cache
      .getAll()
      .filter((q) => q.getObserversCount() > 0)
      .map((q) => answerOf(q.state.data))
      .filter((m): m is AnswerMark => m !== null)
    return `${marks.length}|${oldest(marks) ?? ''}`
  }, [cache])
  const [count, at] = useSyncExternalStore(subscribe, read).split('|')
  return { count: Number(count), at: at || null }
}

export default function Refreshing() {
  const { count, at } = useStaleOnScreen()
  if (!count) return null
  const when = at ? clockUb(at) : ''
  return (
    <span
      role="status"
      title={`${count} хэсэг ${when ? `${when}-ны ` : ''}тооцоогоор харагдаж байна. Шинэ parse-ийн дагуу worker дахин тооцоолж байна, бэлэн болмогц хуудас өөрөө шинэчлэгдэнэ.`}
      className="fixed bottom-4 left-4 z-40 inline-flex items-center gap-1.5 rounded-full border border-line bg-raised px-3 py-1.5 text-xs whitespace-nowrap text-ink-2 shadow-lg print:hidden"
    >
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" className="animate-spin [animation-duration:2s]" aria-hidden="true">
        <path d="M21 12a9 9 0 1 1-3-6.7M21 4v5h-5" />
      </svg>
      Шинэ дататай болгож байна{when && <span className="text-ink-3">· одоо {when}-ны тооцоо</span>}
    </span>
  )
}

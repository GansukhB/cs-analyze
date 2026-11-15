// docs/adr/0014: a query answered stale is fetched again, sooner at first, then
// once a minute, until the worker's warm-up has computed it (`api/answers.ts`).
// Only queries someone is looking at are asked again; one mounted later fetches
// on its own and starts over.
import type { Query, QueryClient } from '@tanstack/react-query'
import { MAX_WAIT_MS, answerOf, refetchDelay } from './answers'

type Pending = { timer: ReturnType<typeof setTimeout> | null; attempt: number; since: number }

export function watchStaleAnswers(client: QueryClient): () => void {
  const pending = new Map<string, Pending>()

  function drop(hash: string) {
    const p = pending.get(hash)
    if (p?.timer) clearTimeout(p.timer)
    pending.delete(hash)
  }

  function schedule(query: Query) {
    const hash = query.queryHash
    if (!answerOf(query.state.data)) return drop(hash)
    const prev = pending.get(hash)
    if (prev?.timer) clearTimeout(prev.timer)
    const since = prev?.since ?? Date.now()
    if (Date.now() - since > MAX_WAIT_MS) return drop(hash)
    const attempt = prev ? prev.attempt + 1 : 0
    const timer = setTimeout(() => {
      const entry = pending.get(hash)
      if (entry) entry.timer = null
      if (query.getObserversCount() > 0) void client.invalidateQueries({ queryKey: query.queryKey, exact: true })
      else drop(hash)
    }, refetchDelay(attempt))
    pending.set(hash, { timer, attempt, since })
  }

  return client.getQueryCache().subscribe((event) => {
    if (event.type === 'updated' && event.action.type === 'success') schedule(event.query)
    else if (event.type === 'removed') drop(event.query.queryHash)
  })
}

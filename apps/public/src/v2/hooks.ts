// The v2 pages' shared hooks.
import { useQueryClient } from '@tanstack/react-query'

/** Refetch every v2 query, after a change Staff made (an Upcoming match, a goal...). */
export function useInvalidateV2() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('/v2/') })
}

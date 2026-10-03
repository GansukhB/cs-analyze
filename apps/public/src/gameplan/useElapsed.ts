import { useEffect, useState } from 'react'

/** Seconds since ``active`` last became true, ticking every 100 ms while it is. */
export function useElapsed(active: boolean): number {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    if (!active) return
    const started = performance.now()
    const id = setInterval(() => setElapsed((performance.now() - started) / 1000), 100)
    return () => {
      clearInterval(id)
      setElapsed(0)
    }
  }, [active])
  return elapsed
}

// "Review жагсаалтад нэмэх": puts a moment on this week's Review queue (CONTEXT.md).
import { useState } from 'react'
import { $api } from '../api/client'
import { useInvalidateV2 } from './hooks'

export function AddToQueue(props: {
  teamId: number
  moment: () => { match_id: number; map_number: number; round: number; t: number } | null
  title: string
  tag?: string
  source: string
  label?: string
  className?: string
}) {
  const invalidate = useInvalidateV2()
  const [done, setDone] = useState(false)
  const add = $api.useMutation('post', '/v2/teams/{team_id}/queue', {
    onSuccess: () => {
      setDone(true)
      void invalidate()
      setTimeout(() => setDone(false), 2000)
    },
  })
  return (
    <button
      type="button"
      disabled={add.isPending}
      className={props.className ?? 'py-1.5 text-left text-sm text-ct underline disabled:text-ink-3'}
      onClick={() => {
        const m = props.moment()
        if (!m) return
        add.mutate({
          params: { path: { team_id: props.teamId } },
          body: { ...m, t: Math.max(0, Math.floor(m.t)), seconds: 30, title: props.title.slice(0, 300), tag: props.tag ?? '', source: props.source.slice(0, 80) },
        })
      }}
    >
      {done ? 'Нэмсэн ✓' : (props.label ?? 'Review жагсаалтад нэмэх')}
    </button>
  )
}

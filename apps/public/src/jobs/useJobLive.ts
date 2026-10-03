import { useEffect, useReducer, useRef, useState } from 'react'
import { $api, fetchClient } from '../api/client'
import { tokenStore } from '../auth/token'
import type { JobDetail, JobEvent, JobStatus } from './format'

type Live = { status: JobStatus | null; events: JobEvent[] }
type Action =
  | { type: 'reset'; detail: JobDetail }
  | { type: 'status'; status: JobStatus }
  | { type: 'activity'; activity: JobStatus['activity'] }
  | { type: 'events'; events: JobEvent[] }

// Event ids only grow, so anything at or below the last one is a duplicate: the
// snapshot and the stream overlap by design (subscribe first, then snapshot).
function merge(old: JobEvent[], incoming: JobEvent[]): JobEvent[] {
  const last = old.length ? old[old.length - 1].id : 0
  const fresh = incoming.filter((e) => e.id > last)
  return fresh.length ? [...old, ...fresh] : old
}

function reducer(state: Live, action: Action): Live {
  switch (action.type) {
    case 'reset':
      return { status: action.detail.status, events: merge([], action.detail.events) }
    case 'status':
      return { ...state, status: action.status }
    case 'activity':
      return state.status ? { ...state, status: { ...state.status, activity: action.activity } } : state
    case 'events':
      return { ...state, events: merge(state.events, action.events) }
  }
}

type Message =
  | { kind: 'snapshot'; payload: JobStatus & { events: JobEvent[] } }
  | { kind: 'status'; payload: JobStatus }
  | { kind: 'event'; payload: JobEvent }
  | { kind: 'activity'; payload: JobStatus['activity'] }

/**
 * One job, kept live: the REST detail first, then the WebSocket (snapshot, then
 * every published message), falling back to polling `?after=<last event>` if the
 * socket can't be had. Once the job finishes, the detail is refetched for its result.
 */
export function useJobLive(publicId: string) {
  const query = $api.useQuery('get', '/jobs/{public_id}', { params: { path: { public_id: publicId } } })
  const [live, dispatch] = useReducer(reducer, { status: null, events: [] })
  const [conn, setConn] = useState('холбогдож байна…')
  const lastId = useRef(0)
  const { data: detail, refetch } = query

  useEffect(() => {
    if (detail) dispatch({ type: 'reset', detail })
  }, [detail])

  useEffect(() => {
    lastId.current = live.events.length ? live.events[live.events.length - 1].id : 0
  }, [live.events])

  const loaded = detail !== undefined
  const finishedAtLoad = detail?.status.finished ?? false

  useEffect(() => {
    if (!loaded || finishedAtLoad) return
    let socket: WebSocket | null = null
    let poller: number | undefined
    let stopped = false

    const stop = () => {
      stopped = true
      window.clearInterval(poller)
      socket?.close()
    }
    const onStatus = (status: JobStatus) => {
      dispatch({ type: 'status', status })
      if (status.finished) {
        stop()
        void refetch()
      }
    }
    const poll = (reason: string) => {
      if (poller !== undefined || stopped) return
      setConn(reason)
      poller = window.setInterval(async () => {
        const { data } = await fetchClient.GET('/jobs/{public_id}', {
          params: { path: { public_id: publicId }, query: { after: lastId.current } },
        })
        if (!data) return
        dispatch({ type: 'events', events: data.events })
        onStatus(data.status)
      }, 2000)
    }

    socket = new WebSocket(`${import.meta.env.VITE_API_URL.replace(/^http/, 'ws')}/ws/jobs/${publicId}`)
    socket.onopen = () => {
      // Browsers can't set headers on a WebSocket; the first message authenticates.
      socket?.send(JSON.stringify({ token: tokenStore.get() }))
      setConn('шууд')
    }
    socket.onmessage = (raw) => {
      const message = JSON.parse(raw.data) as Message
      if (message.kind === 'snapshot') {
        dispatch({ type: 'events', events: message.payload.events })
        onStatus(message.payload)
      } else if (message.kind === 'event') {
        dispatch({ type: 'events', events: [message.payload] })
      } else if (message.kind === 'status') {
        onStatus(message.payload)
      } else if (message.kind === 'activity') {
        dispatch({ type: 'activity', activity: message.payload })
      }
    }
    socket.onclose = () => poll('асууж байна (холболт хаагдсан)')
    socket.onerror = () => poll('асууж байна (холболтын алдаа)')
    return stop
  }, [loaded, finishedAtLoad, publicId, refetch])

  const finished = live.status?.finished ?? false
  return { detail, status: live.status, events: live.events, conn: finished ? 'дууссан' : conn, error: query.error }
}

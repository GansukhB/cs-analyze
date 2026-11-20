// OPS-5: what the every-5-minutes check finds, shown to Staff on every page, since
// without Telegram nobody else hears it (app/services/alerts.py `shown`). Red while
// the latest check still finds it, amber for what was said in the last day. The
// same GET /system query as the footer, so it costs no extra request.
import { $api } from '../api/client'
import type { components } from '../api/schema'

type SystemAlert = components['schemas']['SystemAlert']

const POLL_MS = 10_000

function when(at?: string | null): string {
  if (!at) return ''
  const d = new Date(at)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString('mn-MN', {
    timeZone: 'Asia/Ulaanbaatar',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function SystemAlerts({ width = 'max-w-[1376px]' }: { width?: string }) {
  const system = $api.useQuery('get', '/system', {}, { refetchInterval: POLL_MS })
  const list: SystemAlert[] = system.data?.alerts ?? []
  if (!list.length) return null
  return (
    <div role="status" className="border-b border-line bg-surface print:hidden">
      <ul className={`mx-auto w-full ${width} space-y-1 px-4 py-2 text-xs sm:px-8`}>
        {list.map((a) => (
          <li key={a.key} title={a.text} className={a.active ? 'text-crit' : 'text-warn'}>
            <span className={`mr-2 inline-block h-2 w-2 rounded-full ${a.active ? 'bg-crit' : 'bg-warn'}`} />
            {a.title}
            {!a.active && a.at && <span className="ml-1 text-ink-3">· {when(a.at)}</span>}
            <span className="ml-2 text-ink-3">{a.text}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

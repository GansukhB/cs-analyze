// The footer: the whole host's load and what the worker is on (GET /system,
// app/services/system.py). Polled every 10 s while the tab is visible.
import { Link } from 'react-router'
import { $api } from '../api/client'
import type { components } from '../api/schema'

type Usage = components['schemas']['Usage']

const POLL_MS = 10_000

type Tone = 'ok' | 'warn' | 'crit'

// The fill carries the severity; the track is the same hue, faint.
const FILL: Record<Tone, string> = { ok: 'bg-ct', warn: 'bg-warn', crit: 'bg-crit' }
const TRACK: Record<Tone, string> = { ok: 'bg-ct/20', warn: 'bg-warn/20', crit: 'bg-crit/20' }

function tone(pct: number): Tone {
  return pct >= 90 ? 'crit' : pct >= 80 ? 'warn' : 'ok'
}

function gb(bytes: number): string {
  const n = bytes / 1024 ** 3
  return n < 100 ? n.toFixed(1) : String(Math.round(n))
}

function sized({ used, total }: Usage): string {
  return `${gb(used)} / ${gb(total)} GB`
}

function share({ used, total }: Usage): number {
  return total > 0 ? (used / total) * 100 : 0
}

function uptime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const h = Math.floor(m / 60)
  const d = Math.floor(h / 24)
  if (d) return `${d}d ${h % 24}h`
  if (h) return `${h}h ${m % 60}m`
  return `${m}m`
}

function Meter({ label, pct, detail }: { label: string; pct: number; detail: string }) {
  const t = tone(pct)
  return (
    <>
      <span>{label}</span>
      <span
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pct)}
        className={`h-1.5 w-24 overflow-hidden rounded-full ${TRACK[t]}`}
      >
        <span className={`block h-full rounded-full ${FILL[t]}`} style={{ width: `${Math.min(pct, 100)}%` }} />
      </span>
      <span className="text-right text-ink tabular-nums">{Math.round(pct)}%</span>
      <span className="tabular-nums">{detail}</span>
    </>
  )
}

export default function SystemFooter({ width }: { width: string }) {
  const system = $api.useQuery('get', '/system', {}, { refetchInterval: POLL_MS })
  const data = system.data
  if (!data) return null
  const { host, scout } = data

  return (
    // max-sm: room under the last line for the Assistant's button.
    <footer className="border-t-1 border-line bg-surface">
      <div className={`mx-auto flex w-full ${width} flex-wrap gap-x-16 gap-y-4 px-4 py-4 text-xs text-ink-3 max-sm:pb-20`}>
        <section className="space-y-2">
          <h2 className="font-medium text-ink-2">
            Server <span className="font-normal text-ink-3">· up {uptime(host.uptime)}</span>
            {system.isError && <span className="ml-2 font-normal text-warn">stale</span>}
          </h2>
          <div className="grid grid-cols-[auto_auto_auto_auto] items-center gap-x-3 gap-y-1.5">
            <Meter
              label="CPU"
              pct={host.cpu_percent}
              detail={`load ${host.load.map((n) => n.toFixed(2)).join(' · ')} / ${host.cpus} cores`}
            />
            <Meter label="RAM" pct={share(host.memory)} detail={sized(host.memory)} />
            {host.swap.total > 0 && <Meter label="Swap" pct={share(host.swap)} detail={sized(host.swap)} />}
            <Meter label="Disk" pct={share(host.disk)} detail={sized(host.disk)} />
          </div>
        </section>

        <section className="space-y-2">
          <h2 className="font-medium text-ink-2">Jobs</h2>
          <div className="grid grid-cols-[auto_1fr] items-center gap-x-3 gap-y-1.5">
            <span>Worker</span>
            <span className={data.worker ? 'text-ink' : 'text-crit'}>
              <span className={`mr-1.5 inline-block h-2 w-2 rounded-full ${data.worker ? 'bg-good' : 'bg-crit'}`} />
              {data.worker ? 'up' : 'down'}
            </span>
            <span>Scout</span>
            <span>
              {scout ? (
                <Link to={`/jobs/${scout.public_id}`} className="text-ink hover:underline">
                  {scout.label}
                  {scout.cycle && ` · match ${scout.cycle.n}/${scout.cycle.of}`} · {scout.stage_label} →
                </Link>
              ) : (
                'idle'
              )}
              {data.queued > 0 && <span className="ml-2">+{data.queued} queued</span>}
            </span>
            <span>Build</span>
            <span className="font-mono">{data.version || 'dev'}</span>
          </div>
        </section>
      </div>
    </footer>
  )
}

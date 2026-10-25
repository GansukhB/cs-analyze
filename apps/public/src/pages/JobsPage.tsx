import { $api } from '../api/client'
import { STATUS_MN } from '../jobs/format'
import JobTable from '../jobs/JobTable'

export default function JobsPage() {
  const list = $api.useQuery('get', '/jobs')
  // The worker panel is the one thing here that changes second to second.
  const broker = $api.useQuery('get', '/workers', {}, { refetchInterval: 4000 })
  const timings = $api.useQuery('get', '/jobs/timings')

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold text-ink">Scout-ууд</h1>
        <p className="text-ink-2">Ажилласан бүх Scout, ард нь буй worker-уудын байдал.</p>
      </div>

      <section className="space-y-2">
        <h2 className="font-medium text-ink">Broker ба worker</h2>
        {broker.data && (
          <div className="space-y-3 rounded-xl border border-line bg-surface p-4">
            <div className="flex flex-wrap gap-8 font-mono text-sm">
              <Stat label="redis">
                <span className={`mr-2 inline-block h-2 w-2 rounded-full ${broker.data.connected ? 'bg-good' : 'bg-crit'}`} />
                {broker.data.redis_url}
              </Stat>
              <Stat label="дараалалд">{broker.data.queued ?? '—'}</Stat>
              <Stat label="workers">{broker.data.workers.length}</Stat>
              <Stat label="ажиллаж буй">{broker.data.active.length}</Stat>
            </div>
            {broker.data.error && <p className="text-sm text-warn">{broker.data.error}</p>}
            {broker.data.connected && broker.data.workers.length === 0 && (
              <p className="text-sm text-ink-2">
                Worker ажиллахгүй байгаа тул дараалалд буй ажлууд хүлээнэ. Эхлүүлэх:{' '}
                <code className="rounded bg-surface-2 px-1">npm run dev:worker</code>.
              </p>
            )}
          </div>
        )}
      </section>

      {timings.data && timings.data.jobs > 0 && (
        <section className="space-y-2">
          <h2 className="font-medium text-ink">Scout хэр удаан ажилладаг</h2>
          <p className="text-sm text-ink-3">Дууссан сүүлийн {timings.data.jobs} Scout-ийн медиан.</p>
          <div className="flex flex-wrap gap-3">
            {timings.data.rows.map((r) => (
              <div key={r.label} className="rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink-2" title={`${r.n} хэмжилт`}>
                <b className="block font-mono text-xl text-ink">{r.median === null ? '—' : seconds(r.median)}</b>
                {r.label}
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="space-y-3">
        <h2 className="font-medium text-ink">Ажлууд</h2>
        {list.data && (
          <>
            <div className="flex flex-wrap gap-3">
              {Object.entries(list.data.counts).map(([status, n]) => (
                <div key={status} className="rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink-2">
                  <b className="block text-xl text-ink">{n}</b>
                  {STATUS_MN[status] ?? status}
                </div>
              ))}
            </div>
            {list.data.jobs.length ? (
              <JobTable jobs={list.data.jobs} />
            ) : (
              <p className="text-sm text-ink-3">Ажил алга.</p>
            )}
          </>
        )}
      </section>
    </div>
  )
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs text-ink-3">{label}</div>
      <div className="text-ink">{children}</div>
    </div>
  )
}

/** 98.8 → "1:39", 9.9 → "9.9с". */
function seconds(v: number): string {
  if (v < 60) return `${v}с`
  const s = Math.round(v)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

import { $api } from '../api/client'
import { STATUS_EN } from '../jobs/format'
import JobTable from '../jobs/JobTable'

export default function JobsPage() {
  const list = $api.useQuery('get', '/jobs')
  // The worker panel is the one thing here that changes second to second.
  const broker = $api.useQuery('get', '/workers', {}, { refetchInterval: 4000 })

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold text-ink">Jobs</h1>
        <p className="text-ink-2">Every analysis run, and the state of the workers behind them.</p>
      </div>

      <section className="space-y-2">
        <h2 className="font-medium text-ink">Broker &amp; workers</h2>
        {broker.data && (
          <div className="space-y-3 rounded-xl border border-line bg-surface p-4">
            <div className="flex flex-wrap gap-8 font-mono text-sm">
              <Stat label="redis">
                <span className={`mr-2 inline-block h-2 w-2 rounded-full ${broker.data.connected ? 'bg-good' : 'bg-crit'}`} />
                {broker.data.redis_url}
              </Stat>
              <Stat label="queued">{broker.data.queued ?? '—'}</Stat>
              <Stat label="workers">{broker.data.workers.length}</Stat>
              <Stat label="active tasks">{broker.data.active.length}</Stat>
            </div>
            {broker.data.error && <p className="text-sm text-warn">{broker.data.error}</p>}
            {broker.data.connected && broker.data.workers.length === 0 && (
              <p className="text-sm text-ink-2">
                No worker is running, so queued jobs will wait. Start one with{' '}
                <code className="rounded bg-surface-2 px-1">npm run dev:worker</code>.
              </p>
            )}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="font-medium text-ink">Runs</h2>
        {list.data && (
          <>
            <div className="flex flex-wrap gap-3">
              {Object.entries(list.data.counts).map(([status, n]) => (
                <div key={status} className="rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink-2">
                  <b className="block text-xl text-ink">{n}</b>
                  {STATUS_EN[status] ?? status}
                </div>
              ))}
            </div>
            {list.data.jobs.length ? (
              <JobTable jobs={list.data.jobs} />
            ) : (
              <p className="text-sm text-ink-3">No runs yet.</p>
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

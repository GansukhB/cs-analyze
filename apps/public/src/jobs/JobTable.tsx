import { Link } from 'react-router'
import { secs, when, type JobRow } from './format'
import StatusPill from './StatusPill'

export default function JobTable({ jobs }: { jobs: JobRow[] }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full text-sm">
        <thead className="border-b border-line text-left text-xs uppercase text-ink-3">
          <tr>
            <th className="px-4 py-2">Matchup</th>
            <th className="px-4 py-2 text-right">a/b/c</th>
            <th className="px-4 py-2">Status</th>
            <th className="px-4 py-2">Stage</th>
            <th className="px-4 py-2 text-right">%</th>
            <th className="px-4 py-2">Created</th>
            <th className="px-4 py-2 text-right">Took</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.public_id} className="border-b border-line-soft last:border-0">
              <td className="px-4 py-2">
                <Link to={`/jobs/${job.public_id}`} className="font-medium text-ct hover:underline">
                  {job.label}
                </Link>
                {job.requested_by && <span className="ml-2 text-xs text-ink-3">{job.requested_by}</span>}
              </td>
              <td className="px-4 py-2 text-right tabular-nums">{job.windows}</td>
              <td className="px-4 py-2">
                <StatusPill status={job.status} />
              </td>
              <td className="px-4 py-2 text-ink-2">{job.stage_label}</td>
              <td className="px-4 py-2 text-right tabular-nums">{job.progress}</td>
              <td className="px-4 py-2 text-ink-2">{when(job.created_at)}</td>
              <td className="px-4 py-2 text-right tabular-nums">{secs(job.duration) || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

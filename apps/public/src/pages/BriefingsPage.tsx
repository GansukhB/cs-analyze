// The Workspace's Briefings (docs/plans/01 WS-5): Staff see drafts too; a Player
// sees what was shared with them.
import { Link } from 'react-router'
import { $api } from '../api/client'
import { day } from '../jobs/format'
import { usePaths } from '../paths'

export default function BriefingsPage() {
  const list = $api.useQuery('get', '/briefings')
  if (list.isError) return <p className="text-crit">Briefing-үүдийг уншиж чадсангүй.</p>
  if (!list.data) return <p className="text-ink-3">Уншиж байна…</p>
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold text-ink">Briefing</h1>
      <BriefingList rows={list.data.briefings} />
    </div>
  )
}

export function BriefingList({ rows }: { rows: { id: string; title: string; created_at: string; shared_at?: string | null; my_team: { name: string }; opponent: { name: string } }[] }) {
  const paths = usePaths()
  if (!rows.length)
    return <p className="text-sm text-ink-3">Briefing алга. Game plan-ийн хуудаснаас «Briefing бэлдэх».</p>
  return (
    <ul className="space-y-2">
      {rows.map((b) => (
        <li key={b.id} className="flex flex-wrap items-baseline gap-3 rounded-md border border-line bg-surface px-4 py-3 text-sm">
          <Link to={paths.briefing(b.id)} className="font-medium text-ct hover:underline">
            {b.title}
          </Link>
          <span className="text-ink-3">
            {b.my_team.name} vs {b.opponent.name}
          </span>
          <span className="ml-auto text-xs text-ink-3">
            {day(b.created_at)}
            {b.shared_at ? '' : ' · ноорог'}
          </span>
        </li>
      ))}
    </ul>
  )
}

// /v2/t/:team/scouting and /gameplan without an opponent: the next Upcoming
// match's, else a pick from recent opponents or any Team with parsed Maps.
import { useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router'
import { $api } from '../api/client'
import { PageSkeleton } from '../ui/Skeleton'
import { TeamPicker, type PickedTeam } from './TeamPicker'
import { at, useTeam } from './team'
import { Button, PageHead, Panel } from './ui'

export default function OpponentIndex({ section, title }: { section: 'scouting' | 'gameplan'; title: string }) {
  const team = useTeam()
  const navigate = useNavigate()
  const [picked, setPicked] = useState<PickedTeam | null>(null)
  // ?pick=1 ("change opponent") always shows the picker.
  const [search] = useSearchParams()
  const next = $api.useQuery('get', '/v2/upcoming', { params: { query: { team_id: team.id } } })
  const matches = $api.useQuery('get', '/v2/teams/{team_id}/matches', { params: { path: { team_id: team.id } } })
  if (!next.data || !matches.data) return <PageSkeleton />
  const u = next.data.upcoming[0]
  if (u && search.get('pick') !== '1') return <Navigate to={at(team.id, section, u.opponent.id)} replace />
  const recent = new Map<string, number>()
  for (const m of matches.data.matches) {
    // The matches list names opponents only; their ids come from the picker below.
    if (!recent.has(m.opponent)) recent.set(m.opponent, m.match_id)
  }
  return (
    <>
      <PageHead label={title} title="Өрсөлдөгч сонгох" sub="Ирэх тоглолт оруулаагүй байна: өрсөлдөгчөө сонгоно уу." />
      <Panel>
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault()
            if (picked) navigate(at(team.id, section, picked.id))
          }}
        >
          <div className="min-w-72 flex-1">
            <TeamPicker label="Өрсөлдөгч" value={picked} onChange={setPicked} exclude={[team.id]} parsedOnly />
          </div>
          <Button type="submit" primary disabled={!picked}>
            Нээх
          </Button>
        </form>
        <span className="text-[13px] text-ink-3">
          Сүүлд тоглосон: {[...recent.keys()].slice(0, 8).join(', ') || '—'} ·{' '}
          <Link to={at(team.id)}>Тоймоос ирэх тоглолт нэмэх</Link>
        </span>
      </Panel>
    </>
  )
}

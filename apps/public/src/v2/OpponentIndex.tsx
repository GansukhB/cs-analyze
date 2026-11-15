// /v2/t/:team/scouting and /gameplan without an opponent: the next Upcoming
// match's, else a pick from recent opponents or any Team with parsed Maps.
import { useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router'
import { $api } from '../api/client'
import type { components } from '../api/schema'
import { PageSkeleton } from '../ui/Skeleton'
import { TeamPicker, type PickedTeam } from './TeamPicker'
import { GOOD, MUTED, WARN } from './format'
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
      <ReadyPlans teamId={team.id} section={section} />
    </>
  )
}

type Ready = components['schemas']['ReadyFixtures']
const STATE: Record<string, { color: string; label: string }> = {
  fresh: { color: GOOD, label: 'Бэлэн, шинэ' },
  stale: { color: WARN, label: 'Шууд нээгдэнэ, шинэ дататай болгож байна' },
  none: { color: MUTED, label: 'Хараахан тооцоолоогүй: анх нээхэд хэдэн секунд хүлээнэ' },
}

// docs/adr/0014: the opponents the worker computes this my team's Game Plan
// against ahead of time, in its order, and how each stands now.
function ReadyPlans({ teamId, section }: { teamId: number; section: 'scouting' | 'gameplan' }) {
  const ready = $api.useQuery('get', '/v2/teams/{team_id}/ready', { params: { path: { team_id: teamId } } }, { refetchInterval: 30_000 })
  const d: Ready | undefined = ready.data
  if (!d || !d.opponents.length) return null
  const fresh = d.opponents.filter((o) => o.state === 'fresh').length
  const w = d.warm
  const sub =
    w?.state === 'working'
      ? `Worker тооцоолж байна: ${w.done}/${w.total} хуудас${w.current ? ` · одоо ${w.current}` : ''}`
      : w?.state === 'paused'
        ? 'Parse явж байна: дууссаны дараа үргэлжлүүлнэ'
        : 'Scout бүрийн дараа worker эдгээрийг урьдчилан тооцоолдог'
  return (
    <Panel title={`Бэлэн Game Plan · ${fresh}/${d.opponents.length}`} sub={sub}>
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-ink-3">
        {Object.entries(STATE).map(([k, v]) => (
          <span key={k} className="inline-flex items-center gap-1.5">
            <Dot color={v.color} />
            {v.label}
          </span>
        ))}
      </div>
      <ul className="grid grid-cols-[repeat(auto-fill,minmax(13rem,1fr))] gap-1.5">
        {d.opponents.map((o) => (
          <li key={o.id}>
            <Link
              to={at(teamId, section, o.id)}
              title={STATE[o.state]?.label}
              className="plain flex min-h-11 items-center gap-2 rounded-md border border-line px-3 py-2 !text-ink hover:border-line-strong"
            >
              <Dot color={STATE[o.state]?.color ?? MUTED} />
              <span className="min-w-0 flex-1 truncate">{o.name}</span>
              <span className="text-xs text-ink-3 tabular-nums">{o.maps} Map</span>
            </Link>
          </li>
        ))}
      </ul>
    </Panel>
  )
}

function Dot({ color }: { color: string }) {
  return <span aria-hidden="true" className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: color }} />
}

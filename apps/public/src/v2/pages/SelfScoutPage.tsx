// v2's Self-scout (grilled 2026-11-12; CONTEXT.md: Self-scout, Tell): what a
// my team does on one Map read the way the Playbook reads an opponent, with no
// opponent picked, so Staff see each week what any opponent could prepare
// against: the Tells first, then the Veto history, the habits and Set plays
// with how an opponent could use them, and the five slots per Side.
import { useSearchParams } from 'react-router'
import { $api } from '../../api/client'
import type { Habit, Slot, Tell } from '../../gameplan/types'
import { LoadError } from '../../ui/LoadError'
import { PageSkeleton } from '../../ui/Skeleton'
import { CT, T, WARN } from '../format'
import { HabitList, Slots, TellList, VetoHistoryView, ViewChips } from '../playbook'
import { useNoteBook } from '../playbookData'
import { useTeam } from '../team'
import { Empty, Kpi, PageHead, Panel, Tag } from '../ui'

export default function SelfScoutPage() {
  const team = useTeam()
  const [params, setParams] = useSearchParams()
  const map = params.get('map') ?? undefined
  const buy = params.get('buy') ?? ''
  const days = Number(params.get('days') ?? 0)
  const q = $api.useQuery('get', '/v2/teams/{team_id}/self-scout', {
    params: {
      path: { team_id: team.id },
      query: {
        ...(map ? { map } : {}),
        ...(buy === 'full' || buy === 'light' ? { buy } : {}),
        ...(days ? { days } : {}),
      },
    },
  })
  const book = useNoteBook(team.id, q.data?.map ?? '')
  if (q.error) return <LoadError error={q.error} what="Self-scout" retry={() => void q.refetch()} />
  if (!q.data) return <PageSkeleton />
  const d = q.data
  const tells = d.tells as unknown as Tell[]
  const found = tells.filter((t) => t.tell)
  const vetoTells = d.vetoes.formats.flatMap((f) => f.tells).filter((t) => t.tell)
  const pick = (m: string) => {
    const next = new URLSearchParams(params)
    next.set('map', m)
    setParams(next, { replace: true })
  }
  return (
    <>
      <PageHead
        label="Self-scout · бидний таамаглагдах байдал"
        title={d.team.name}
        sub="Өрсөлдөгч бидний талаар юуг урьдчилан мэдэж, бэлдэж болох вэ: Pool-ийн багуудаас илүү давтан хийдэг сонголт (Tell), зуршил, veto. Scrim тооцогдохгүй."
      />
      <nav aria-label="Газрын зураг" className="flex flex-wrap gap-1.5">
        {d.maps
          .filter((m) => m.maps > 0 || m.active)
          .map((m) => (
            <button
              key={m.map}
              type="button"
              aria-pressed={m.map === d.map}
              disabled={m.maps === 0}
              onClick={() => pick(m.map)}
              className={`h-11 rounded-md border px-4 text-sm disabled:opacity-40 ${m.map === d.map ? 'border-accent bg-accent-soft text-accent' : 'border-line-strong text-ink-2'}`}
            >
              {m.label} <span className="num text-xs text-ink-3">{m.maps}</span>
            </button>
          ))}
      </nav>
      <ViewChips score={false} note={d.sample && d.sample.rounds < d.sample.of ? `${d.sample.rounds}/${d.sample.of} раунд` : undefined} />
      {d.sample ? (
        <section className="grid grid-cols-[repeat(auto-fit,minmax(min(200px,100%),1fr))] gap-3">
          <Kpi label="Таамаглагдах сонголт" value={`${found.length}/${tells.length}`} color={found.length ? WARN : undefined} sub={`${d.label} дээрх шийдвэрийн цэг`} />
          <Kpi label="Veto Tell" value={vetoTells.length} color={vetoTells.length ? WARN : undefined} sub={`${d.vetoes.vetoes} veto (${d.vetoes.since}-аас)`} />
          <Kpi label="Map" value={d.sample.maps} sub={d.sample.all_maps > d.sample.maps ? `одоогийн тавын үе; бүгд ${d.sample.all_maps}` : 'одоогийн тавын үе'} />
          <Kpi label="Раунд" value={d.sample.rounds} sub={`CT ${d.sample.ct} · T ${d.sample.t}`} />
        </section>
      ) : (
        <Panel>
          <Empty>Энэ багт Window дотор задлан шинжилсэн Map алга.</Empty>
        </Panel>
      )}
      {d.sample && !d.sample.sites_known && <span className="text-[13px] text-warn">Энэ Map-ын цэгүүдийн байрлал тодорхойгүй тул CT Setup-ыг уншихгүй.</span>}
      <section className="grid grid-cols-[repeat(auto-fit,minmax(min(480px,100%),1fr))] gap-4">
        <Panel title={`Таамаглагдах зуршил · ${d.label ?? '—'}`} sub="Шугам дээрх зураас нь Pool-ийн 75-р percentile: түүнээс баруун тийш бол бусдаас илүү таамаглагдана">
          <TellList tells={tells} whose="mine" empty="Энэ Map-д шийдвэрийн цэг уншихад хангалттай раунд алга." />
        </Panel>
        <Panel title="Veto" sub="Бидний эхний ban, pick-ийг өрсөлдөгч хэр урьдчилан тооцох вэ">
          <VetoHistoryView v={d.vetoes} whose="mine" />
        </Panel>
      </section>
      {d.map &&
        d.habits.map((s) => (
          <Panel
            key={s.side}
            title={
              <span className="flex items-center gap-2">
                <Tag color={s.side === 'ct' ? CT : T}>{s.label}</Tag> зуршил ба Set play
              </span>
            }
            sub="Хариу нь өрсөлдөгч үүнийг яаж ашиглаж болохыг хэлнэ"
          >
            <HabitList habits={s.habits as unknown as Habit[]} book={book} strat={{ whose: 'mine', team: team.id, map: d.map ?? '' }} />
          </Panel>
        ))}
      {d.map && (
        <Panel title="Хэн хаана: 20 с-д таван slot">
          <Slots slots={{ mine: d.slots as unknown as Record<string, Slot[] | null> }} names={{ mine: d.team.name }} />
        </Panel>
      )}
    </>
  )
}

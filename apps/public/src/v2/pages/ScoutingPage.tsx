// v2 screen 07, scouting an opponent: what they play (and the model's guess at
// their veto), on one Map their bomb by buy and its clock, their CT Setups,
// utility, habits and dangerous Players from the Playbook, and the counters
// Staff pick for the Upcoming match.
import { useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { $api } from '../../api/client'
import type { components } from '../../api/schema'
import '../../gameplan/gameplan.css'
import type { Habit, PlaybookPanel } from '../../gameplan/types'
import UtilityMap from '../../gameplan/UtilityMap'
import { LoadError } from '../../ui/LoadError'
import { PageSkeleton } from '../../ui/Skeleton'
import { CRIT, CT, GOOD, MUTED, T, WARN, ghostLink, shortDate } from '../format'
import { useInvalidateV2 } from '../hooks'
import OpponentIndex from '../OpponentIndex'
import { at, useTeam } from '../team'
import { UpcomingForm } from '../Upcoming'
import { Bar, Box, Button, ButtonLink, Empty, PageHead, Panel, SideToggle, Swatch, Tag } from '../ui'

type Scouting = components['schemas']['Scouting']
type CounterPick = components['schemas']['CounterPick']

export function ScoutingIndex() {
  return <OpponentIndex section="scouting" title="Өрсөлдөгчийн скаутинг" />
}

const STRENGTH: Record<string, [string, string]> = {
  strong: ['өндөр', GOOD],
  medium: ['дунд', WARN],
  weak: ['сул', CRIT],
}

export default function ScoutingPage() {
  const team = useTeam()
  const { opponent = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const map = params.get('map') ?? undefined
  const q = $api.useQuery('get', '/v2/teams/{team_id}/scouting/{opponent_id}', {
    params: { path: { team_id: team.id, opponent_id: Number(opponent) }, query: { map } },
  })
  const chosen = q.data?.map ?? null
  const pb = $api.useQuery(
    'get',
    '/gameplan/{mine}/vs/{theirs}/playbook/{map_name}',
    { params: { path: { mine: team.id, theirs: Number(opponent), map_name: chosen ?? '' } } },
    { enabled: !!chosen, retry: false },
  )
  const [side, setSide] = useState<'t' | 'ct'>('t')
  if (q.error) return <LoadError error={q.error} what="Скаутинг" retry={() => void q.refetch()} />
  if (!q.data) return <PageSkeleton />
  const d = q.data
  const book = pb.data?.data as PlaybookPanel | undefined
  return (
    <>
      <PageHead
        label="Өрсөлдөгчийн скаутинг · Anti-strat"
        title={d.opponent.name}
        sub={`${d.window.maps} Map · ${d.window.rounds} раунд${d.window.since ? ` · ${shortDate(d.window.since)}-аас хойш` : ''} · ${d.window.h2h_maps} нь бидэнтэй`}
        actions={
          <>
            <ButtonLink primary to={at(team.id, 'gameplan', d.opponent.id)}>
              Game plan нээх
            </ButtonLink>
            <ButtonLink to={`/gameplan/${team.id}/vs/${d.opponent.id}/briefing`}>Briefing (тайлан хуваалцах)</ButtonLink>
          </>
        }
      />
      <nav aria-label="Газрын зураг" className="flex flex-wrap gap-1.5">
        {d.maps
          .filter((m) => m.theirs > 0)
          .map((m) => (
            <button
              key={m.map}
              type="button"
              aria-pressed={m.map === chosen}
              onClick={() => setParams({ map: m.map }, { replace: true })}
              className={`h-11 rounded-md border px-4 text-sm ${m.map === chosen ? 'border-accent bg-accent-soft text-accent' : 'border-line-strong text-ink-2'}`}
            >
              {m.label} <span className="num text-xs text-ink-3">{m.theirs} Map</span>
            </button>
          ))}
      </nav>
      <section className="flex flex-wrap gap-4">
        <Veto d={d} />
        <Panel
          title={`Тэдний зан төлөв · ${d.maps.find((m) => m.map === chosen)?.label ?? '—'}`}
          className="flex-[999_1_640px]"
          right={<SideToggle value={side} onChange={setSide} h={40} />}
        >
          {side === 't' ? <TSide d={d} /> : <CTSide book={book} loading={pb.isPending && !!chosen} />}
        </Panel>
      </section>
      <section className="flex flex-wrap gap-4">
        <Panel title="Utility буух цэгүүд" className="flex-[1_1_440px]">
          {chosen ? (
            <div className="max-h-[960px] overflow-auto pr-1 text-sm">
              <UtilityMap mine={team.id} theirs={d.opponent.id} map={chosen} />
            </div>
          ) : (
            <Empty />
          )}
        </Panel>
        <div className="flex min-w-0 flex-[999_1_560px] flex-col gap-4">
          <Patterns book={book} />
          <Threats book={book} />
        </div>
      </section>
      <Counters d={d} book={book} teamId={team.id} />
    </>
  )
}

function Veto({ d }: { d: Scouting }) {
  const rows = d.maps.filter((m) => m.active)
  return (
    <Panel title="Veto таамаг" sub="Veto-гийн түүх уншаагүй: тоглосон давтамж, бидний боломжоос гаргасан загвар" className="flex-[1_1_380px]">
      {rows.map((m) => (
        <div key={m.map} className="grid grid-cols-[80px_minmax(0,1fr)_minmax(0,1fr)] items-center gap-2.5">
          <span className="cond font-semibold">
            {m.label} <span className="num text-[11px] text-ink-3">{m.theirs}</span>
          </span>
          <div className="flex items-center gap-1.5">
            <div className="flex h-2 flex-1 justify-end rounded-full bg-line">
              <div className="rounded-full" style={{ width: `${m.ban ?? 0}%`, background: CRIT }} />
            </div>
            <span className="num w-8 text-xs">{m.ban ?? '—'}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Bar pct={m.pick} color={GOOD} className="flex-1" />
            <span className="num w-8 text-xs">{m.pick ?? '—'}</span>
          </div>
        </div>
      ))}
      <div className="grid grid-cols-[80px_minmax(0,1fr)_minmax(0,1fr)] gap-2.5 text-xs text-ink-3">
        <span>тоо = Map</span>
        <span className="text-right">Ban %</span>
        <span>Pick %</span>
      </div>
    </Panel>
  )
}

const BUY: Record<string, string> = { pistol: 'Pistol', eco: 'Eco', force: 'Force', full: 'Full buy' }

function TSide({ d }: { d: Scouting }) {
  const max = Math.max(1, ...d.timing.map((b) => b.from !== undefined ? b.n : 0))
  return (
    <div className="flex flex-col gap-4.5">
      <div className="flex flex-col gap-2.5">
        <div className="flex flex-wrap justify-between gap-2.5">
          <span className="lbl">Бөмбөг хаана суусан · худалдан авалтаар</span>
          <div className="flex flex-wrap gap-3 text-xs text-ink-3">
            <Swatch color={T}>A</Swatch>
            <Swatch color={CT}>B</Swatch>
            <Swatch color="#3A4652">Суулгаагүй</Swatch>
          </div>
        </div>
        {d.sites.length === 0 ? (
          <Empty>Энэ Map дээр тэдний T раунд алга.</Empty>
        ) : (
          d.sites.map((s) => (
            <div key={s.buy} className="grid grid-cols-[90px_minmax(0,1fr)_60px] items-center gap-2.5">
              <span className="text-sm">{BUY[s.buy] ?? s.buy}</span>
              <div className="flex h-[26px] overflow-hidden rounded">
                {[
                  [s.a, s.won_a, T, '#0A0D10'],
                  [s.b, s.won_b, CT, '#0A0D10'],
                  [s.none, s.won_none, '#3A4652', 'var(--ink)'],
                ].map(([n, won, bg, fg], i) =>
                  (n as number) > 0 ? (
                    <div
                      key={i}
                      title={`${n} раунд, ${won} хожсон`}
                      className="num grid place-items-center text-xs"
                      style={{ width: `${(100 * (n as number)) / s.n}%`, background: bg as string, color: fg as string }}
                    >
                      {Math.round((100 * (n as number)) / s.n)}
                    </div>
                  ) : null,
                )}
              </div>
              <span className="num text-xs text-ink-3">n={s.n}</span>
            </div>
          ))
        )}
      </div>
      <div className="flex flex-col gap-2">
        <span className="lbl">Бөмбөг суулгасан цаг · buy дууссанаас секунд</span>
        <div className="grid h-[130px] items-end gap-1 border-b border-line-strong" style={{ gridTemplateColumns: `repeat(${d.timing.length}, minmax(0, 1fr))` }}>
          {d.timing.map((b) => (
            <div key={b.from} title={`${b.from}–${b.from + 10}с: ${b.n} раунд`} className="rounded-t-[3px]" style={{ height: `${(100 * b.n) / max}%`, background: b.n >= max * 0.6 ? T : '#6B5530' }} />
          ))}
        </div>
        <div className="num grid gap-1 text-[11px] text-ink-3" style={{ gridTemplateColumns: `repeat(${d.timing.length}, minmax(0, 1fr))` }}>
          {d.timing.map((b) => (
            <span key={b.from} className="text-center">
              {b.from}
            </span>
          ))}
        </div>
        <span className="text-xs text-ink-3">{d.t_rounds} T раунд</span>
      </div>
    </div>
  )
}

function HabitLine({ h }: { h: Habit }) {
  const [word, color] = STRENGTH[h.evidence.strength] ?? STRENGTH.weak
  return (
    <div className="grid grid-cols-[64px_minmax(0,1fr)] items-center gap-3.5 border-t border-line py-2.5">
      <span className="num text-[22px] font-semibold text-accent">
        {h.evidence.of ? `${Math.round((100 * h.evidence.n) / h.evidence.of)}%` : h.evidence.n}
      </span>
      <div className="flex flex-col gap-1">
        <span className="text-[15px] font-semibold">{h.title}</span>
        <span className="text-[13px] text-ink-3">
          {h.detail} · {h.evidence.n}/{h.evidence.of} {h.evidence.unit ?? 'раунд'} · {h.evidence.maps} Map ·{' '}
          <span style={{ color }}>итгэл {word}</span>
          {h.evidence.refs.length > 1 && (
            <>
              {' · '}
              <Link to={ghostLink(h.evidence.refs)}>⧉ давхар</Link>
            </>
          )}
        </span>
      </div>
    </div>
  )
}

function CTSide({ book, loading }: { book?: PlaybookPanel; loading: boolean }) {
  if (loading) return <Empty>Playbook уншиж байна…</Empty>
  const ct = book?.sections.find((s) => s.key === 'their_ct')?.habits ?? []
  const setups = ct.filter((h) => ['setup', 'stack', 'soft_site', 'spot'].includes(h.kind))
  return (
    <div className="flex flex-col gap-3">
      <span className="lbl">CT байрлалын загварууд (20 секундэд)</span>
      {setups.length === 0 ? <Empty>4+ раундад давтагдсан setup алга.</Empty> : setups.map((h) => <HabitLine key={h.title} h={h} />)}
    </div>
  )
}

function Patterns({ book }: { book?: PlaybookPanel }) {
  const all = [...(book?.sections.find((s) => s.key === 'their_t')?.habits ?? []), ...(book?.sections.find((s) => s.key === 'their_ct')?.habits ?? [])]
  const top = all.filter((h) => h.evidence.strength !== 'weak').slice(0, 5)
  return (
    <Panel title="Илрүүлсэн хэв маяг">
      {!book ? <Empty>Playbook уншиж байна…</Empty> : top.length === 0 ? <Empty>Дунд, өндөр итгэлтэй хэв маяг алга.</Empty> : top.map((h) => <HabitLine key={h.title} h={h} />)}
    </Panel>
  )
}

function Threats({ book }: { book?: PlaybookPanel }) {
  const players = (book?.players ?? []).slice(0, 3)
  return (
    <Panel title="Аюултай тоглогчид">
      {players.length === 0 ? (
        <Empty />
      ) : (
        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(200px,100%),1fr))] gap-2.5">
          {players.map((p) => (
            <Box key={p.player}>
              <span className="cond text-lg font-bold">{p.player}</span>
              {p.tags.length > 0 && <span className="text-[13px] text-ink-3">{p.tags.join(' · ')}</span>}
              {[...(p.card ?? []), ...p.lines].slice(0, 3).map((l) => (
                <span key={l} className="text-[13px] leading-snug text-ink-2">
                  {l}
                </span>
              ))}
            </Box>
          ))}
        </div>
      )}
    </Panel>
  )
}

function Counters({ d, book, teamId }: { d: Scouting; book?: PlaybookPanel; teamId: number }) {
  const invalidate = useInvalidateV2()
  const options = useMemo<CounterPick[]>(() => {
    if (!book) return []
    const out: CounterPick[] = []
    for (const p of book.plan) out.push({ key: `plan:${p.side}:${p.title}`, title: p.title, body: p.counter, map: book.map })
    for (const s of book.advice.sides)
      for (const a of s.levers) out.push({ key: `lever:${s.side}:${a.title}`, title: a.title, body: a.counter, map: book.map })
    return out.filter((o, i) => out.findIndex((x) => x.key === o.key) === i).slice(0, 8)
  }, [book])
  const saved = d.upcoming?.counters ?? []
  const [picked, setPicked] = useState<string[] | null>(null)
  const chosen = picked ?? saved.map((c) => c.key)
  const save = $api.useMutation('patch', '/v2/upcoming/{upcoming_id}', {
    onSuccess: () => {
      setPicked(null)
      void invalidate()
    },
  })
  const [adding, setAdding] = useState(false)
  return (
    <Panel
      title="Хариу төлөвлөгөө"
      sub="Playbook-ийн хариу ба Lever-ууд · сонгосныг ирэх тоглолтын Game plan-д хадгална"
      right={
        d.upcoming ? (
          <Button
            primary
            disabled={save.isPending || picked === null}
            onClick={() => {
              const keep = saved.filter((c) => c.map !== book?.map && chosen.includes(c.key))
              const fresh = options.filter((o) => chosen.includes(o.key))
              save.mutate({ params: { path: { upcoming_id: d.upcoming!.id } }, body: { counters: [...keep, ...fresh] } })
            }}
          >
            Сонгосныг Game plan-д нэмэх
          </Button>
        ) : null
      }
    >
      {!d.upcoming &&
        (adding ? (
          <UpcomingForm teamId={teamId} opponent={d.opponent} onDone={() => setAdding(false)} />
        ) : (
          <span className="text-[13px] text-ink-3">
            Сонголтоо хадгалахын тулд {d.opponent.name}-тэй хийх ирэх тоглолтоо оруулна уу.{' '}
            <button type="button" className="text-ct underline" onClick={() => setAdding(true)}>
              Ирэх тоглолт нэмэх
            </button>
          </span>
        ))}
      {options.length === 0 ? (
        <Empty>{book ? 'Энэ Map-д хариу санал алга.' : 'Playbook уншиж байна…'}</Empty>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(300px,100%),1fr))] gap-2.5">
          {options.map((o) => (
            <label key={o.key} className="flex cursor-pointer items-start gap-3 rounded-md border border-line-soft bg-surface-2 p-3.5">
              <input
                type="checkbox"
                checked={chosen.includes(o.key)}
                disabled={!d.upcoming}
                onChange={() => setPicked(chosen.includes(o.key) ? chosen.filter((k) => k !== o.key) : [...chosen, o.key])}
                className="mt-0.5 h-5 w-5 accent-[var(--accent)]"
              />
              <span className="flex flex-col gap-1">
                <span className="text-[15px] font-semibold">
                  {o.title} <Tag color={o.key.startsWith('lever') ? GOOD : MUTED}>{o.key.startsWith('lever') ? 'Lever' : 'Хариу'}</Tag>
                </span>
                <span className="text-[13px] leading-snug text-ink-3">{o.body}</span>
              </span>
            </label>
          ))}
        </div>
      )}
    </Panel>
  )
}

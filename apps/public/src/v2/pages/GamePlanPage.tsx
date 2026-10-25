// v2 screen 08, the Game plan: the next match with this opponent, the three
// things to do, the veto played out, both styles, each Map's plan with the
// counters picked on the scouting page, the "if … then" card, the matchups,
// what is new about them and the pre-match checklist. Read from the v1 Game Plan
// endpoints (decision, todo, maps, veto lab, Playbook, style, timeout, between)
// and the Upcoming match.
import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { $api } from '../../api/client'
import type { components } from '../../api/schema'
import type { DecisionPanel, MapsPanel, PlaybookPanel, TodoPanel } from '../../gameplan/types'
import { LoadError } from '../../ui/LoadError'
import { PageSkeleton } from '../../ui/Skeleton'
import { CRIT, CT, GOOD, MUTED, T, WARN, countdown, when } from '../format'
import { useInvalidateV2 } from '../hooks'
import OpponentIndex from '../OpponentIndex'
import { at, useTeam } from '../team'
import { UpcomingForm } from '../Upcoming'
import { Bar, Box, Button, ButtonLink, Empty, Panel, Swatch, Tag } from '../ui'

type Scouting = components['schemas']['Scouting']
type Upcoming = components['schemas']['UpcomingRead']

export function GamePlanIndex() {
  return <OpponentIndex section="gameplan" title="Game plan" />
}

const CALL: Record<string, [string, string]> = {
  pick: ['Бидний pick', GOOD],
  ban: ['Ban', CRIT],
  contest: ['Тэмцэлдэх', WARN],
  blind: ['Мэдээлэлгүй', MUTED],
  avoid: ['Зайлсхийх', CRIT],
  unknown: ['—', MUTED],
}

export default function GamePlanPage() {
  const team = useTeam()
  const { opponent = '' } = useParams()
  const theirs = Number(opponent)
  const fixture = { params: { path: { mine: team.id, theirs } } }
  const scout = $api.useQuery('get', '/v2/teams/{team_id}/scouting/{opponent_id}', {
    params: { path: { team_id: team.id, opponent_id: theirs } },
  })
  const tab = (t: string) => ({ params: { path: { mine: team.id, theirs, tab: t } } })
  const decision = $api.useQuery('get', '/gameplan/{mine}/vs/{theirs}/s/{tab}', tab('decision'))
  const todo = $api.useQuery('get', '/gameplan/{mine}/vs/{theirs}/s/{tab}', tab('todo'))
  const mapsPanel = $api.useQuery('get', '/gameplan/{mine}/vs/{theirs}/s/{tab}', tab('maps'))
  const h2h = $api.useQuery('get', '/gameplan/{mine}/vs/{theirs}/s/{tab}', tab('h2h'))
  const u = scout.data?.upcoming ?? null
  const format = (`bo${u?.best_of ?? 3}` as 'bo1' | 'bo3' | 'bo5')
  const veto = $api.useQuery('post', '/gameplan/{mine}/vs/{theirs}/veto', { ...fixture, body: { format, we_start: true, done: [], adjust: {} } })
  const between = $api.useQuery('get', '/gameplan/{mine}/vs/{theirs}/between', fixture, { retry: false })
  const [params, setParams] = useSearchParams()
  if (scout.error) return <LoadError error={scout.error} what="Game plan" retry={() => void scout.refetch()} />
  if (!scout.data) return <PageSkeleton />
  const d = scout.data
  const dec = decision.data?.data as DecisionPanel | undefined
  const todoData = todo.data?.data as TodoPanel | undefined
  const board = (mapsPanel.data?.data as MapsPanel | undefined)?.board ?? []
  const played = (todoData?.maps ?? []).filter((m) => m.call === 'pick' || m.call === 'contest')
  const chosen = params.get('map') ?? played[0]?.map ?? todoData?.maps[0]?.map ?? d.map
  return (
    <>
      <Header d={d} u={u} dec={dec} h2h={h2h.data?.data as { totals?: { maps_played?: number; maps_won?: number }; matches?: { my_maps_won: number; their_maps_won: number }[] } | undefined} teamId={team.id} />
      <Keys dec={dec} loading={decision.isPending} />
      <section className="flex flex-wrap gap-4">
        <Veto lab={veto.data} board={board} loading={veto.isPending} />
        {chosen && <Style mine={team.id} theirs={theirs} map={chosen} names={[d.team.name, d.opponent.name]} />}
      </section>
      <MapPlan
        teamId={team.id}
        theirs={theirs}
        maps={todoData?.maps ?? []}
        map={chosen}
        onMap={(m) => setParams({ map: m }, { replace: true })}
        counters={(u?.counters ?? []).filter((c) => c.map === chosen)}
      />
      {chosen && <Triggers mine={team.id} theirs={theirs} map={chosen} />}
      <section className="flex flex-wrap gap-4">
        {chosen && <Duels mine={team.id} theirs={theirs} map={chosen} />}
        <div className="flex min-w-0 flex-[1_1_380px] flex-col gap-4">
          <Novel data={between.data} />
          <Checklist u={u} teamId={team.id} opponent={d.opponent} />
        </div>
      </section>
    </>
  )
}

function Header(props: {
  d: Scouting
  u: Upcoming | null
  dec?: DecisionPanel
  h2h?: { totals?: { maps_played?: number; maps_won?: number }; matches?: { my_maps_won: number; their_maps_won: number }[] }
  teamId: number
}) {
  const { d, u, dec, h2h, teamId } = props
  const [adding, setAdding] = useState(false)
  const fmt = `BO${u?.best_of ?? 3}`
  const series = dec?.decision.forecast.series.find((s) => s.format.toUpperCase() === fmt)
  const won = (h2h?.matches ?? []).filter((m) => m.my_maps_won > m.their_maps_won).length
  const lost = (h2h?.matches ?? []).length - won
  const mapsWon = h2h?.totals?.maps_won ?? 0
  const mapsPlayed = h2h?.totals?.maps_played ?? 0
  const enough = d.window.maps >= 8 ? ['Өндөр', GOOD] : d.window.maps >= 4 ? ['Дунд', WARN] : ['Бага', CRIT]
  return (
    <section className="flex flex-wrap items-center justify-between gap-5 rounded-lg border border-line bg-surface p-6">
      <div className="flex flex-col gap-2">
        <span className="lbl">Game plan · тоглолтын төлөвлөгөө</span>
        <div className="flex flex-wrap items-center gap-4">
          <h1 className="cond m-0 text-[40px] font-bold">vs {d.opponent.name}</h1>
          <Link to={`${at(teamId, 'gameplan')}?pick=1`} className="plain flex h-9 items-center rounded-md border border-line-strong px-3 text-[13px] !text-ink-2">
            Өрсөлдөгч солих
          </Link>
        </div>
        {u ? (
          <span className="text-[15px] text-ink-3">
            {when(u.starts_at)} · BO{u.best_of}
            {u.tournament && ` · ${u.tournament}`} · <span className="num text-accent">{countdown(u.starts_at)}</span>
          </span>
        ) : adding ? (
          <UpcomingForm teamId={teamId} opponent={d.opponent} onDone={() => setAdding(false)} />
        ) : (
          <span className="text-[15px] text-ink-3">
            Ирэх тоглолт оруулаагүй ·{' '}
            <button type="button" className="text-ct underline" onClick={() => setAdding(true)}>
              нэмэх
            </button>
          </span>
        )}
        <div className="mt-1.5 flex flex-wrap gap-2">
          <ButtonLink primary to={`/gameplan/${teamId}/vs/${d.opponent.id}/briefing`}>
            Briefing горим
          </ButtonLink>
          <Button onClick={() => window.print()}>PDF</Button>
          <ButtonLink to={at(teamId, 'scouting', d.opponent.id)}>Скаутингийн дата</ButtonLink>
          <ButtonLink to={`/gameplan/${teamId}/vs/${d.opponent.id}/veto`}>Veto lab</ButtonLink>
        </div>
      </div>
      <div className="flex flex-wrap gap-7">
        <Stat label="Цуврал хожих магадлал" value={series ? `${series.pct}%` : '—'} color={series ? (series.pct >= 55 ? GOOD : series.pct >= 45 ? WARN : CRIT) : MUTED} sub={series ? `${fmt} Forecast · ${series.word}` : 'Rating алга'} />
        <Stat label="Хоорондын түүх" value={`${won}–${lost}`} sub={`Газрын зураг ${mapsWon}–${mapsPlayed - mapsWon}`} />
        <Stat label="Датаны хангалт" value={enough[0]} color={enough[1]} sub={`${d.window.maps} Map · ${d.window.rounds} раунд`} />
      </div>
    </section>
  )
}

function Stat(props: { label: string; value: string; sub: string; color?: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="lbl">{props.label}</span>
      <span className="num text-[34px] font-semibold" style={{ color: props.color }}>
        {props.value}
      </span>
      <span className="text-xs text-ink-3">{props.sub}</span>
    </div>
  )
}

function Keys({ dec, loading }: { dec?: DecisionPanel; loading: boolean }) {
  const advice = dec?.top_advice
  const keys = [...(advice?.levers ?? []).map((x) => ({ ...x, lever: true })), ...(advice?.cautions ?? []).map((x) => ({ ...x, lever: false }))].slice(0, 3)
  return (
    <section className="flex flex-col gap-3.5">
      <h2 className="cond m-0 text-[22px] font-bold">Ялахын тулд хийх 3 гол зүйл</h2>
      {loading ? (
        <Empty>Уншиж байна…</Empty>
      ) : keys.length === 0 ? (
        <Empty>Review-ээс Lever, Caution гараагүй (Review хангалтгүй).</Empty>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(320px,100%),1fr))] gap-3">
          {keys.map((k, i) => (
            <article key={k.what} className="flex flex-col gap-3 rounded-lg border border-t-[3px] border-line border-t-accent bg-surface p-5">
              <div className="flex items-baseline justify-between gap-2">
                <span className="num text-4xl leading-none font-semibold text-accent">{String(i + 1).padStart(2, '0')}</span>
                <Tag color={k.lever ? GOOD : WARN}>{k.lever ? 'Lever' : 'Caution'}</Tag>
              </div>
              <h3 className="cond m-0 text-[21px] leading-tight font-bold">{k.what}</h3>
              <p className="m-0 text-sm leading-relaxed text-ink-2">{k.why}</p>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

type VetoLab = components['schemas']['VetoLab']

function Veto({ lab, board, loading }: { lab?: VetoLab; board: MapsPanel['board']; loading: boolean }) {
  const steps = lab?.veto?.line ?? []
  // The Map no step took is the decider (a Bo1's only Map).
  const left = (lab?.maps ?? []).map((m) => m.map).filter((m) => !steps.some((v) => v.map === m))
  const line = steps.length && left.length === 1 ? [...steps, { who: 'decider', kind: 'decider', map: left[0], chance: lab?.maps.find((m) => m.map === left[0])?.p ?? null }] : steps
  const rec = (r: { won: number; lost: number } | null | undefined) => (r ? `${r.won}–${r.lost}` : '—')
  return (
    <Panel title="Veto стратеги" sub="Хоёр багийн Map-ийн хүч, хоорондын түүх, тэдний тоглох давтамжаас (Veto lab)" className="flex-[999_1_640px]">
      {loading ? (
        <Empty>Уншиж байна…</Empty>
      ) : line.length === 0 ? (
        <Empty>Veto-г загварчлах Rating алга.</Empty>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(120px,100%),1fr))] gap-1.5">
          {line.map((v, i) => {
            const us = v.who === 'mine'
            const color = v.kind === 'ban' ? CRIT : v.kind === 'pick' ? GOOD : WARN
            return (
              <div key={i} className="flex flex-col gap-1 rounded-md border p-2.5" style={{ borderColor: us ? '#4A3A20' : 'var(--line-soft)', background: us ? '#1A160F' : 'var(--surface-2)' }}>
                <span className="num text-[11px] text-ink-3">
                  {i + 1}. {us ? 'Бид' : v.who === 'decider' ? '—' : 'Тэд'}
                </span>
                <span className="cond text-xs font-bold tracking-[0.06em] uppercase" style={{ color }}>
                  {v.kind}
                </span>
                <span className="cond text-lg font-bold">{v.map.replace('de_', '')}</span>
                {v.chance != null && <span className="num text-[11px] text-ink-3">хожих {Math.round(100 * v.chance)}%</span>}
              </div>
            )
          })}
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="grid-table nums">
          <thead>
            <tr>
              <th>Газрын зураг</th>
              <th>Бидний</th>
              <th>Тэдний</th>
              <th>Хоорондын</th>
              <th>Бидний хожих магадлал</th>
              <th>Санал</th>
            </tr>
          </thead>
          <tbody>
            {(lab?.maps ?? []).map((m) => {
              const b = board.find((x) => x.map === m.map)
              const [word, color] = CALL[b?.call ?? 'unknown'] ?? CALL.unknown
              const p = m.p == null ? null : Math.round(100 * m.p)
              const pc = p == null ? MUTED : p >= 55 ? GOOD : p >= 45 ? WARN : CRIT
              return (
                <tr key={m.map}>
                  <td className="cond !font-[inherit] text-base font-semibold">{m.map.replace('de_', '')}</td>
                  <td>{rec(b?.mine)}</td>
                  <td className="text-ink-3">{rec(b?.theirs)}</td>
                  <td className="text-ink-3">{rec(b?.h2h)}</td>
                  <td>
                    <div className="flex items-center gap-2">
                      <Bar pct={p} color={pc} className="w-28" />
                      <span className="text-[13px]" style={{ color: pc }}>
                        {p == null ? '—' : `${p}%`}
                      </span>
                    </div>
                  </td>
                  <td>
                    <Tag color={color}>{word}</Tag>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}

function Style({ mine, theirs, map, names }: { mine: number; theirs: number; map: string; names: [string, string] }) {
  const q = $api.useQuery('get', '/gameplan/{mine}/vs/{theirs}/style/{map_name}', { params: { path: { mine, theirs, map_name: map } } })
  const s = q.data
  const rows = (s?.mine.sides ?? []).flatMap((side) =>
    side.metrics.map((m) => {
      const t = s?.theirs.sides.find((x) => x.side === side.side)?.metrics.find((x) => x.key === m.key)
      return { key: `${side.side}-${m.key}`, side: side.side, label: m.label, us: m, them: t }
    }),
  )
  const tags = (s?.theirs.sides ?? []).flatMap((side) =>
    side.metrics.filter((m) => !m.thin && m.pct != null && (m.pct >= 80 || m.pct <= 20)).map((m) => `${side.side.toUpperCase()}: ${m.label} ${m.pct! >= 80 ? 'өндөр' : 'бага'}`),
  )
  const unit = (m?: { value: number; unit: string }) => (m ? `${m.value}${m.unit === '%' ? '%' : 'с'}` : '—')
  return (
    <Panel
      title={`Хэв маягийн харьцуулалт · ${map.replace('de_', '')}`}
      sub="Map дээрх бүх багуудын дундах percentile"
      className="flex-[1_1_380px]"
      right={
        <div className="flex gap-3.5 text-xs text-ink-3">
          <Swatch color={T}>{names[0]}</Swatch>
          <Swatch color="var(--them)">{names[1]}</Swatch>
        </div>
      }
    >
      {!s ? (
        <Empty>{q.isError ? 'Хэв маяг уншиж чадсангүй.' : 'Уншиж байна…'}</Empty>
      ) : (
        rows.slice(0, 9).map((r) => (
          <div key={r.key} className="flex flex-col gap-1.5">
            <div className="flex justify-between gap-2 text-[13px]">
              <span>
                <span style={{ color: r.side === 'ct' ? CT : T }}>{r.side.toUpperCase()}</span> · {r.label}
              </span>
              <span className="num text-xs text-ink-3">
                {unit(r.us)} / {unit(r.them)}
              </span>
            </div>
            <Bar pct={r.us.pct} color={T} h={6} />
            <Bar pct={r.them?.pct} color="var(--them)" h={6} />
          </div>
        ))
      )}
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5 border-t border-line pt-3">
          <span className="lbl w-full">Тэдний төрх</span>
          {tags.map((t) => (
            <span key={t} className="rounded-full border border-line-strong px-2.5 py-1 text-[13px] text-ink-2">
              {t}
            </span>
          ))}
        </div>
      )}
    </Panel>
  )
}

function MapPlan(props: {
  teamId: number
  theirs: number
  maps: TodoPanel['maps']
  map: string | null
  onMap: (m: string) => void
  counters: components['schemas']['CounterPick'][]
}) {
  const { teamId, theirs, maps, map } = props
  const q = $api.useQuery(
    'get',
    '/gameplan/{mine}/vs/{theirs}/playbook/{map_name}',
    { params: { path: { mine: teamId, theirs, map_name: map ?? '' } } },
    { enabled: !!map, retry: false },
  )
  const book = q.data?.data as PlaybookPanel | undefined
  const plan = (side: 'ct' | 't') => (book?.plan ?? []).filter((p) => p.side === side).map((p) => `${p.title} — ${p.counter}`)
  const blocks: [string, string, string[]][] = [
    ['Pistol', WARN, book?.pistol_plan ?? []],
    ['T тал', T, plan('t')],
    ['CT тал', CT, plan('ct')],
    ['Эдийн засаг', '#8FA3B5', [...(book?.economy.habits ?? []).map((h) => `${h.title}${h.counter ? ` — ${h.counter}` : ''}`), ...(book?.economy.choices ?? []).map((c) => c.text)].slice(0, 4)],
  ]
  return (
    <Panel
      title="Газрын зураг бүрийн тоглох төлөвлөгөө"
      right={
        <div role="group" aria-label="Газрын зураг" className="flex flex-wrap gap-1.5">
          {maps.map((m) => (
            <button
              key={m.map}
              type="button"
              aria-pressed={m.map === map}
              onClick={() => props.onMap(m.map)}
              className={`h-11 rounded-md border px-4 text-sm ${m.map === map ? 'border-accent bg-accent-soft text-accent' : 'border-line-strong text-ink-2'}`}
            >
              {m.label} <span className="num text-xs text-ink-3">{m.call_label}</span>
            </button>
          ))}
        </div>
      }
    >
      {!map ? (
        <Empty />
      ) : !book ? (
        <Empty>{q.isError ? 'Playbook уншиж чадсангүй.' : 'Playbook уншиж байна…'}</Empty>
      ) : (
        <>
          <div className="flex flex-wrap items-baseline gap-2.5">
            <span className="cond text-lg font-bold">{book.label}</span>
            <span className="text-sm text-ink-2">
              {book.sample.theirs.maps} Map тэднийх, {book.sample.mine.maps} Map манайх ·{' '}
              <Link to={`/gameplan/${teamId}/vs/${theirs}/sheet/${map}`}>Map sheet</Link> ·{' '}
              <Link to={`/gameplan/${teamId}/vs/${theirs}/s/todo/m/${map}`}>Бүтэн Playbook (v1)</Link>
            </span>
          </div>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(300px,100%),1fr))] gap-3">
            {blocks.map(([title, color, items]) => (
              <Box key={title} className="gap-2.5">
                <div className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-sm" style={{ background: color }} />
                  <span className="cond text-base font-bold">{title}</span>
                </div>
                {items.length === 0 ? (
                  <Empty>Давтагдсан зуршил алга.</Empty>
                ) : (
                  items.map((t, i) => (
                    <div key={t} className="grid grid-cols-[18px_minmax(0,1fr)] items-start gap-2">
                      <span className="num pt-0.5 text-xs" style={{ color }}>
                        {String(i + 1).padStart(2, '0')}
                      </span>
                      <span className="text-sm leading-normal">{t}</span>
                    </div>
                  ))
                )}
              </Box>
            ))}
          </div>
          {props.counters.length > 0 && (
            <div className="flex flex-col gap-2 border-t border-line pt-3">
              <span className="lbl">Скаутингаас сонгосон хариу</span>
              {props.counters.map((c) => (
                <span key={c.key} className="text-sm">
                  <b>{c.title}</b> — <span className="text-ink-2">{c.body}</span>
                </span>
              ))}
            </div>
          )}
        </>
      )}
    </Panel>
  )
}

function Triggers({ mine, theirs, map }: { mine: number; theirs: number; map: string }) {
  const q = $api.useQuery('get', '/gameplan/{mine}/vs/{theirs}/timeout/{map_name}', { params: { path: { mine, theirs, map_name: map } } }, { retry: false })
  const moves = (q.data?.sides ?? []).flatMap((s) => s.moves.map((m) => ({ ...m, side: s.side })))
  return (
    <Panel title="Тоглолтын явцад: хэрэв … бол …" sub="Тэд 2 раунд дараалан алдсан эсвэл timeout авсны дараах раунд (timeout card)">
      {!q.data ? (
        <Empty>{q.isError ? 'Уншиж чадсангүй.' : 'Уншиж байна…'}</Empty>
      ) : moves.length === 0 ? (
        <Empty>Шахалтын дор тодорхой өөрчлөгддөг зүйл алга ({q.data.pressure} раунд).</Empty>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(400px,100%),1fr))] gap-2.5">
          {moves.map((m) => (
            <div key={`${m.side}-${m.key}`} className="grid grid-cols-[minmax(0,1fr)_24px_minmax(0,1fr)] items-center gap-3 rounded-md border border-line-soft bg-surface-2 p-3.5">
              <div className="flex flex-col gap-1">
                <span className="lbl !text-warn">Хэрэв</span>
                <span className="text-sm leading-snug">
                  Шахалтын дор ({m.side.toUpperCase()}): {m.label} {m.usual}% → {m.pressed}%
                </span>
              </div>
              <svg width="22" height="14" viewBox="0 0 22 14" fill="none" stroke="var(--ink-3)" strokeWidth="2" aria-hidden="true">
                <path d="M1 7h18M14 2l5 5-5 5" />
              </svg>
              <div className="flex flex-col gap-1">
                <span className="lbl !text-good">Бид</span>
                <span className="text-sm leading-snug">{m.counter}</span>
                <span className="num text-[11px] text-ink-3">{m.rounds} раунд</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </Panel>
  )
}

function Duels({ mine, theirs, map }: { mine: number; theirs: number; map: string }) {
  const q = $api.useQuery('get', '/gameplan/{mine}/vs/{theirs}/playbook/{map_name}', { params: { path: { mine, theirs, map_name: map } } }, { retry: false })
  const players = (q.data?.data as PlaybookPanel | undefined)?.players ?? []
  return (
    <Panel title="Тоглогчийн тулаан" sub="Тэдний тоглогч бүр: байрлал, нээлт, бидэнтэй хийсэн duel" className="flex-[999_1_640px]">
      {players.length === 0 ? (
        <Empty>{q.isPending ? 'Уншиж байна…' : 'Мэдээлэл алга.'}</Empty>
      ) : (
        players.map((p) => (
          <div key={p.player} className="flex flex-col gap-1 border-t border-line py-3">
            <div className="flex flex-wrap items-baseline gap-2.5">
              <span className="cond text-[17px] font-bold">{p.player}</span>
              {p.tags.map((t) => (
                <Tag key={t} color="var(--ink-3)">
                  {t}
                </Tag>
              ))}
            </div>
            {p.lines.map((l) => (
              <span key={l} className="text-[13px] text-ink-2">
                {l}
              </span>
            ))}
            {p.duels && <span className="text-[13px] text-ink-3">{p.duels}</span>}
            {(p.card ?? []).slice(0, 2).map((l) => (
              <span key={l} className="text-[13px] text-ink-3">
                {l}
              </span>
            ))}
          </div>
        ))
      )}
    </Panel>
  )
}

function Novel({ data }: { data?: components['schemas']['Between'] }) {
  return (
    <Panel title="Тэдэнд шинээр гарсан зүйлс" right={data?.played && <span className="lbl">{data.played.label ?? ''}</span>}>
      {!data ? (
        <Empty>Уншиж байна…</Empty>
      ) : data.lines.length === 0 && data.players.length === 0 ? (
        <Empty>Сүүлийн Map-д ердийнхөөсөө ялгарах зүйл алга (90%-ийн итгэлтэйгээр).</Empty>
      ) : (
        <>
          {data.lines.slice(0, 4).map((l) => (
            <span key={`${l.side}-${l.key}`} className="border-t border-line pt-2.5 text-sm leading-snug">
              {l.text}
            </span>
          ))}
          {data.players.filter((p) => p.hot || p.cold).slice(0, 3).map((p) => (
            <span key={p.sid} className="border-t border-line pt-2.5 text-[13px] text-ink-2">
              {p.name} {p.hot ? 'халуун' : p.cold ? 'хүйтэн' : ''}: Swing/раунд {(100 * p.here).toFixed(1)}% (ердийн{' '}
              {(100 * p.usual).toFixed(1)}%, {p.rounds} раунд)
            </span>
          ))}
        </>
      )}
    </Panel>
  )
}

function Checklist({ u, teamId, opponent }: { u: Upcoming | null; teamId: number; opponent: { id: number; name: string } }) {
  const invalidate = useInvalidateV2()
  const save = $api.useMutation('patch', '/v2/upcoming/{upcoming_id}', { onSuccess: () => void invalidate() })
  const [adding, setAdding] = useState('')
  const [form, setForm] = useState(false)
  if (!u)
    return (
      <Panel title="Тоглолтын өмнөх шалгах жагсаалт">
        {form ? (
          <UpcomingForm teamId={teamId} opponent={opponent} onDone={() => setForm(false)} />
        ) : (
          <span className="text-[13px] text-ink-3">
            Жагсаалт ирэх тоглолтод хадгалагдана.{' '}
            <button type="button" className="text-ct underline" onClick={() => setForm(true)}>
              Ирэх тоглолт нэмэх
            </button>
          </span>
        )}
      </Panel>
    )
  const items = u.checklist
  const put = (next: typeof items) => save.mutate({ params: { path: { upcoming_id: u.id } }, body: { checklist: next } })
  return (
    <Panel title="Тоглолтын өмнөх шалгах жагсаалт" right={<span className="num text-[13px] text-ink-3">{items.filter((i) => i.done).length}/{items.length}</span>}>
      {items.map((it, i) => (
        <label key={`${i}-${it.text}`} className="flex min-h-11 cursor-pointer items-center gap-3 border-t border-line">
          <input type="checkbox" checked={it.done} onChange={() => put(items.map((x, j) => (j === i ? { ...x, done: !x.done } : x)))} className="h-5 w-5 accent-[var(--accent)]" />
          <span className="flex-1 text-sm" style={{ opacity: it.done ? 0.6 : 1 }}>
            {it.text}
          </span>
          <button type="button" aria-label="Устгах" onClick={() => put(items.filter((_x, j) => j !== i))} className="px-2 text-ink-3 hover:text-crit">
            ×
          </button>
        </label>
      ))}
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (adding.trim()) put([...items, { text: adding.trim(), done: false }])
          setAdding('')
        }}
      >
        <input value={adding} maxLength={200} onChange={(e) => setAdding(e.target.value)} placeholder="Шинэ мөр…" className="h-11 flex-1 rounded-md border border-line-strong bg-surface-2 px-3 text-sm text-ink" />
        <Button type="submit">Нэмэх</Button>
      </form>
      <Link to={at(teamId, 'practice')} className="py-1 text-sm">
        Бэлтгэлийн төлөвлөгөөнд шилжүүлэх
      </Link>
    </Panel>
  )
}

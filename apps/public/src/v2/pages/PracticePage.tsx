// v2 screen 09, the practice week: Team goals (and the five's Development
// goals), the Practice schedule Staff build day by day, the week's Review queue
// watched together, drills from the latest Match's agenda, and past goals.
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { $api } from '../../api/client'
import type { components } from '../../api/schema'
import { LoadError } from '../../ui/LoadError'
import { PageSkeleton } from '../../ui/Skeleton'
import { CRIT, GOOD, MUTED, WARN, countdown, mmss, when } from '../format'
import { useInvalidateV2 } from '../hooks'
import { TeamPicker, type PickedTeam } from '../TeamPicker'
import { at, useTeam } from '../team'
import { Box, Button, Empty, PageHead, Panel, Swatch, Tag } from '../ui'

type Week = components['schemas']['PracticePlan']
type Block = components['schemas']['BlockRead']
type Goal = components['schemas']['TeamGoalRead']

const KINDS: Record<string, [string, string, string]> = {
  scrim: ['Scrim', 'var(--ct)', 'var(--ct-soft)'],
  drill: ['Дадлага', 'var(--accent)', 'var(--accent-soft)'],
  review: ['Демо review', 'var(--ink-2)', 'var(--chip)'],
  match: ['Албан тоглолт', 'var(--good)', 'var(--good-soft)'],
  rest: ['Амралт', 'var(--ink-3)', 'var(--surface)'],
}
const DAYS = ['Даваа', 'Мягмар', 'Лхагва', 'Пүрэв', 'Баасан', 'Бямба', 'Ням']
const VERDICT: Record<string, [string, string]> = {
  reached: ['Хүрсэн ✓', GOOD],
  close: ['Ойрхон', WARN],
  not_yet: ['Хүрээгүй', CRIT],
  no_data: ['Дата алга', MUTED],
}

function iso(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function addDays(day: string, n: number) {
  const d = new Date(`${day}T00:00:00`)
  d.setDate(d.getDate() + n)
  return iso(d)
}
function md(day: string) {
  return `${day.slice(5, 7)}/${day.slice(8, 10)}`
}

export default function PracticePage() {
  const team = useTeam()
  const [params, setParams] = useSearchParams()
  const week = params.get('week') ?? undefined
  const q = $api.useQuery('get', '/v2/teams/{team_id}/practice', { params: { path: { team_id: team.id }, query: { week } } })
  if (q.error) return <LoadError error={q.error} what="Бэлтгэл" retry={() => void q.refetch()} />
  if (!q.data) return <PageSkeleton />
  const d = q.data
  const total = Object.entries(d.hours).reduce((a, [k, v]) => (k === 'rest' || k === 'match' ? a : a + v), 0)
  const go = (n: number) => setParams({ week: addDays(d.week, n) }, { replace: true })
  return (
    <>
      <PageHead
        label="Демо дата-аас үүсгэсэн · дасгалжуулагч баталсан"
        title={`Бэлтгэлийн төлөвлөгөө · ${md(d.week)} – ${md(addDays(d.week, 6))}`}
        sub={
          <>
            {d.upcoming ? (
              <>
                Гол зорилго:{' '}
                <span className="text-ink">
                  vs {d.upcoming.opponent.name} · {when(d.upcoming.starts_at)} BO{d.upcoming.best_of}
                </span>{' '}
                ({countdown(d.upcoming.starts_at)}) ·{' '}
              </>
            ) : (
              'Ирэх тоглолт алга · '
            )}
            {total.toFixed(1)} цагийн бэлтгэл
          </>
        }
        actions={
          <>
            <div className="flex gap-5">
              <Hours label="Scrim" v={d.hours.scrim} />
              <Hours label="Дадлага" v={d.hours.drill} />
              <Hours label="Демо review" v={d.hours.review} />
            </div>
            <div className="flex gap-1.5">
              <Button onClick={() => go(-7)}>‹ Өмнөх</Button>
              <Button onClick={() => setParams({}, { replace: true })}>Энэ 7 хоног</Button>
              <Button onClick={() => go(7)}>Дараах ›</Button>
            </div>
          </>
        }
      />
      <Goals d={d} teamId={team.id} />
      <Schedule d={d} teamId={team.id} />
      <section className="flex flex-wrap gap-4">
        <Queue d={d} teamId={team.id} />
        <div className="flex min-w-0 flex-[1_1_420px] flex-col gap-4">
          <Drills d={d} />
          <History d={d} />
        </div>
      </section>
    </>
  )
}

function Hours({ label, v }: { label: string; v: number | undefined }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="lbl">{label}</span>
      <span className="num text-[22px] font-semibold">{(v ?? 0).toFixed(1)} цаг</span>
    </div>
  )
}

function GoalCard({ g, n }: { g: Goal; n: number }) {
  const invalidate = useInvalidateV2()
  const patch = $api.useMutation('patch', '/v2/goals/{goal_id}', { onSuccess: () => void invalidate() })
  const p = g.progress
  const [word, color] = VERDICT[p.verdict] ?? VERDICT.no_data
  const unit = g.unit
  const lower = g.better === 'lower'
  const scale = (v: number) => (lower ? 100 - Math.min(100, v) : Math.min(100, v))
  return (
    <article className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-4.5">
      <div className="flex justify-between gap-2">
        <span className="lbl">
          Зорилт {n} · {g.map ? g.map.replace('de_', '') : 'Бүх Map'}
          {g.side && ` · ${g.side.toUpperCase()}`}
        </span>
        <Tag color={color}>{word}</Tag>
      </div>
      <h3 className="m-0 text-[17px] leading-snug font-semibold">{g.title || g.label}</h3>
      <div className="flex items-baseline gap-2.5">
        <span className="num text-[30px] font-semibold" style={{ color }}>
          {p.value == null ? '—' : `${p.value}${unit}`}
        </span>
        <svg width="22" height="14" viewBox="0 0 22 14" fill="none" stroke="var(--ink-3)" strokeWidth="2" aria-hidden="true">
          <path d="M1 7h18M14 2l5 5-5 5" />
        </svg>
        <span className="num text-[30px] font-semibold" style={{ color: GOOD }}>
          {g.target}
          {unit}
        </span>
      </div>
      <div className="relative h-2 rounded bg-line">
        <div className="absolute inset-y-0 left-0 rounded" style={{ width: `${p.value == null ? 0 : scale(p.value)}%`, background: 'var(--accent)' }} />
        <div className="absolute -top-1 -bottom-1 w-0.5" style={{ left: `${scale(g.target)}%`, background: GOOD }} />
      </div>
      {g.notes && <span className="text-[13px] leading-normal text-ink-2">{g.notes}</span>}
      <span className="num text-xs text-ink-3">
        {g.kpi === 'vrs'
          ? 'Хэмжилт: VRS-ийн сүүлийн сарын бүсийн байр'
          : `Хэмжилт: ${g.label}, албан тоглолт, ${g.start_on}-аас · ${p.of} тохиолдол`}
        {p.low != null && ` · 80%: ${p.low}–${p.high}${unit}`} · эхлэл {g.baseline == null ? '—' : `${g.baseline}${unit}`} · {g.due_on} хүртэл
        {p.overdue && <span style={{ color: CRIT }}> · хугацаа хэтэрсэн</span>}
      </span>
      <div className="flex gap-3 text-[13px]">
        <button type="button" className="text-ct underline" onClick={() => patch.mutate({ params: { path: { goal_id: g.id } }, body: { status: 'done' } })}>
          Дууссан
        </button>
        <button type="button" className="text-ink-3 underline" onClick={() => patch.mutate({ params: { path: { goal_id: g.id } }, body: { status: 'dropped' } })}>
          Цуцлах
        </button>
      </div>
    </article>
  )
}

function Goals({ d, teamId }: { d: Week; teamId: number }) {
  const [adding, setAdding] = useState(false)
  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="cond m-0 text-[22px] font-bold">Багийн зорилтууд</h2>
        <button type="button" className="text-sm text-ct underline" onClick={() => setAdding((a) => !a)}>
          {adding ? 'Болих' : 'Зорилт нэмэх'}
        </button>
      </div>
      {adding && <GoalForm teamId={teamId} onDone={() => setAdding(false)} />}
      {d.goals.length === 0 && !adding ? (
        <Empty>Идэвхтэй Team goal алга.</Empty>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(320px,100%),1fr))] gap-3">
          {d.goals.map((g, i) => (
            <GoalCard key={g.id} g={g} n={i + 1} />
          ))}
        </div>
      )}
      {d.player_goals.length > 0 && (
        <Panel title="Тоглогчдын Development plan">
          {d.player_goals.map((g) => {
            const [word, color] = VERDICT[g.verdict] ?? VERDICT.no_data
            return (
              <div key={g.id} className="grid grid-cols-[120px_minmax(0,1fr)_auto] items-center gap-3 border-t border-line py-2 text-sm">
                <Link to={at(teamId, 'players', g.steamid)} className="font-semibold">
                  {g.player}
                </Link>
                <span>
                  {g.label}: <span className="num">{g.value ?? '—'}</span> → <span className="num">{g.target}</span>
                  <span className="text-ink-3"> · {g.due_on} хүртэл</span>
                </span>
                <span className="text-xs" style={{ color }}>
                  {word}
                </span>
              </div>
            )
          })}
        </Panel>
      )}
    </section>
  )
}

function GoalForm({ teamId, onDone }: { teamId: number; onDone: () => void }) {
  const invalidate = useInvalidateV2()
  const kpis = $api.useQuery('get', '/v2/goal-kpis')
  const maps = $api.useQuery('get', '/v2/teams/{team_id}/overview', { params: { path: { team_id: teamId }, query: { period: 'all' } } })
  const [kpi, setKpi] = useState('rounds')
  const [map, setMap] = useState('')
  const [side, setSide] = useState<'' | 'ct' | 't'>('')
  const [target, setTarget] = useState('')
  const [due, setDue] = useState('')
  const [title, setTitle] = useState('')
  const [notes, setNotes] = useState('')
  const save = $api.useMutation('post', '/v2/teams/{team_id}/goals', {
    onSuccess: () => {
      void invalidate()
      onDone()
    },
  })
  const input = 'h-11 rounded-md border border-line-strong bg-surface-2 px-3 text-sm text-ink'
  return (
    <form
      className="flex flex-wrap items-end gap-3 rounded-lg border border-line bg-surface p-4"
      onSubmit={(e) => {
        e.preventDefault()
        if (!target || !due) return
        save.mutate({ params: { path: { team_id: teamId } }, body: { kpi, map, side, target: Number(target), due_on: due, title, notes } })
      }}
    >
      <label className="flex flex-col gap-1.5">
        <span className="lbl">Хэмжүүр</span>
        <select value={kpi} onChange={(e) => setKpi(e.target.value)} className={input}>
          {(kpis.data ?? []).map((k) => (
            <option key={k.kpi} value={k.kpi}>
              {k.label}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="lbl">Map</span>
        <select value={map} onChange={(e) => setMap(e.target.value)} className={input}>
          <option value="">Бүгд</option>
          {(maps.data?.maps ?? []).map((m) => (
            <option key={m.map} value={m.map}>
              {m.label}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="lbl">Тал</span>
        <select value={side} onChange={(e) => setSide(e.target.value as '' | 'ct' | 't')} className={input}>
          <option value="">Хоёулаа</option>
          <option value="t">T</option>
          <option value="ct">CT</option>
        </select>
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="lbl">Зорилт</span>
        <input type="number" step="0.1" required value={target} onChange={(e) => setTarget(e.target.value)} className={`${input} w-28`} />
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="lbl">Хугацаа</span>
        <input type="date" required value={due} onChange={(e) => setDue(e.target.value)} className={input} />
      </label>
      <label className="flex min-w-60 flex-1 flex-col gap-1.5">
        <span className="lbl">Гарчиг</span>
        <input value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} className={input} />
      </label>
      <label className="flex w-full flex-col gap-1.5">
        <span className="lbl">Яаж (тэмдэглэл)</span>
        <input value={notes} maxLength={4000} onChange={(e) => setNotes(e.target.value)} className={input} />
      </label>
      <Button type="submit" primary disabled={save.isPending}>
        Хадгалах
      </Button>
    </form>
  )
}

function Schedule({ d, teamId }: { d: Week; teamId: number }) {
  const [editing, setEditing] = useState<{ day: string; block?: Block } | null>(null)
  const days = DAYS.map((name, i) => ({ name, day: addDays(d.week, i) }))
  return (
    <Panel
      title="7 хоногийн хуваарь"
      right={
        <div className="flex flex-wrap gap-3.5 text-xs text-ink-3">
          {Object.entries(KINDS).map(([k, [l, c]]) => (
            <Swatch key={k} color={c}>
              {l}
            </Swatch>
          ))}
        </div>
      }
    >
      {editing && <BlockForm teamId={teamId} day={editing.day} block={editing.block} onDone={() => setEditing(null)} />}
      <div className="overflow-x-auto">
        <div className="grid min-w-[900px] grid-cols-7 gap-2">
          {days.map(({ name, day }) => {
            const blocks = d.blocks.filter((b) => b.day === day)
            const isToday = day === d.today
            const match = d.upcoming && d.upcoming.starts_at.slice(0, 10) <= day && day <= d.upcoming.starts_at.slice(0, 10)
            return (
              <div key={day} className="flex flex-col gap-1.5">
                <div className="flex justify-between border-b-2 px-1 py-2" style={{ borderColor: match ? GOOD : isToday ? 'var(--accent)' : 'var(--line-strong)' }}>
                  <span className="cond font-bold">{name}</span>
                  <span className="num text-xs text-ink-3">{md(day)}</span>
                </div>
                {blocks.map((b) => {
                  const [, c, bg] = KINDS[b.kind] ?? KINDS.rest
                  return (
                    <button
                      key={b.id}
                      type="button"
                      onClick={() => setEditing({ day, block: b })}
                      className="flex min-h-[70px] flex-col gap-1 rounded-md border p-2.5 text-left"
                      style={{ borderColor: c, background: bg }}
                    >
                      <span className="num text-[11px]" style={{ color: c }}>
                        {b.start}
                        {b.end && `–${b.end}`}
                      </span>
                      <span className="text-[13px] leading-snug font-semibold">{b.title || KINDS[b.kind]?.[0]}</span>
                      <span className="text-xs leading-snug text-ink-3">
                        {b.opponent ? `vs ${b.opponent.name}` : ''}
                        {b.opponent && b.note ? ' · ' : ''}
                        {b.note}
                      </span>
                    </button>
                  )
                })}
                <button type="button" onClick={() => setEditing({ day })} className="h-9 rounded-md border border-dashed border-line-strong text-sm text-ink-3 hover:text-ink">
                  + нэмэх
                </button>
              </div>
            )
          })}
        </div>
      </div>
    </Panel>
  )
}

function BlockForm({ teamId, day, block, onDone }: { teamId: number; day: string; block?: Block; onDone: () => void }) {
  const invalidate = useInvalidateV2()
  const [kind, setKind] = useState(block?.kind ?? 'scrim')
  const [start, setStart] = useState(block?.start ?? '19:00')
  const [end, setEnd] = useState(block?.end ?? '22:00')
  const [title, setTitle] = useState(block?.title ?? '')
  const [note, setNote] = useState(block?.note ?? '')
  const [opponent, setOpponent] = useState<PickedTeam | null>(block?.opponent ?? null)
  const done = { onSuccess: () => { void invalidate(); onDone() } }
  const add = $api.useMutation('post', '/v2/teams/{team_id}/blocks', done)
  const put = $api.useMutation('put', '/v2/blocks/{block_id}', done)
  const del = $api.useMutation('delete', '/v2/blocks/{block_id}', done)
  const input = 'h-11 rounded-md border border-line-strong bg-surface-2 px-3 text-sm text-ink'
  const body = { day, kind: kind as 'scrim', start, end, title, note, opponent_id: kind === 'scrim' ? (opponent?.id ?? null) : null }
  return (
    <form
      className="flex flex-wrap items-end gap-3 rounded-md border border-line-soft bg-surface-2 p-3.5"
      onSubmit={(e) => {
        e.preventDefault()
        if (block) put.mutate({ params: { path: { block_id: block.id } }, body })
        else add.mutate({ params: { path: { team_id: teamId } }, body })
      }}
    >
      <span className="lbl w-full">{md(day)} · {block ? 'засах' : 'шинэ блок'}</span>
      <label className="flex flex-col gap-1.5">
        <span className="lbl">Төрөл</span>
        <select value={kind} onChange={(e) => setKind(e.target.value)} className={input}>
          {Object.entries(KINDS).map(([k, [l]]) => (
            <option key={k} value={k}>
              {l}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="lbl">Эхлэх</span>
        <input type="time" value={start} onChange={(e) => setStart(e.target.value)} className={input} />
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="lbl">Дуусах</span>
        <input type="time" value={end} onChange={(e) => setEnd(e.target.value)} className={input} />
      </label>
      <label className="flex min-w-48 flex-1 flex-col gap-1.5">
        <span className="lbl">Гарчиг</span>
        <input value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} className={input} />
      </label>
      <label className="flex min-w-48 flex-1 flex-col gap-1.5">
        <span className="lbl">Тайлбар</span>
        <input value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} className={input} />
      </label>
      {kind === 'scrim' && (
        <div className="w-56">
          <TeamPicker label="Scrim-ийн өрсөлдөгч" value={opponent} onChange={setOpponent} exclude={[teamId]} />
        </div>
      )}
      <Button type="submit" primary disabled={add.isPending || put.isPending}>
        Хадгалах
      </Button>
      {block && (
        <Button onClick={() => del.mutate({ params: { path: { block_id: block.id } } })} disabled={del.isPending}>
          Устгах
        </Button>
      )}
      <Button onClick={onDone}>Болих</Button>
    </form>
  )
}

function Queue({ d, teamId }: { d: Week; teamId: number }) {
  const invalidate = useInvalidateV2()
  const patch = $api.useMutation('patch', '/v2/queue/{item_id}', { onSuccess: () => void invalidate() })
  const later = $api.useMutation('post', '/v2/queue/{item_id}/next-week', { onSuccess: () => void invalidate() })
  const del = $api.useMutation('delete', '/v2/queue/{item_id}', { onSuccess: () => void invalidate() })
  const watched = d.queue.filter((q) => q.watched).length
  const minutes = Math.round(d.queue.reduce((a, q) => a + q.seconds, 0) / 60)
  const first = d.queue.find((q) => !q.watched)
  const replay = (q: Week['queue'][number]) => `${at(teamId, 'replay', q.match_id, q.map_number)}?round=${q.round}&t=${Math.floor(q.t)}`
  return (
    <Panel
      title="Демо review жагсаалт"
      className="flex-[1_1_520px]"
      right={
        <span className="num text-[13px] text-ink-3">
          {watched}/{d.queue.length} үзсэн · {minutes} мин
        </span>
      }
    >
      {d.queue.length === 0 ? (
        <Empty>Энэ 7 хоногт нэмсэн агшин алга. 2D Replay, Тойм, Скаутинг хуудаснаас «Review жагсаалтад нэмэх».</Empty>
      ) : (
        d.queue.map((q) => (
          <div key={q.id} className="grid grid-cols-[24px_64px_minmax(0,1fr)_auto] items-center gap-3 border-t border-line py-2.5">
            <input
              type="checkbox"
              aria-label="Үзсэн"
              checked={q.watched}
              onChange={() => patch.mutate({ params: { path: { item_id: q.id } }, body: { watched: !q.watched } })}
              className="h-5 w-5 accent-[var(--accent)]"
            />
            <span className="num rounded bg-chip px-1.5 py-1 text-center text-xs">{mmss(q.seconds)}</span>
            <span className="flex min-w-0 flex-col gap-0.5">
              <Link to={replay(q)} className="text-sm font-semibold" style={{ opacity: q.watched ? 0.6 : 1 }}>
                R{q.round} {q.map} — {q.title || 'агшин'}
              </Link>
              <span className="text-xs text-ink-3">
                {mmss(q.t)}-ээс{q.source && ` · ${q.source}`}
              </span>
            </span>
            <span className="flex items-center gap-2">
              {q.tag && <Tag color="var(--ct)">{q.tag}</Tag>}
              {!q.watched && (
                <button type="button" title="Дараа 7 хоногт" aria-label="Дараа 7 хоногт шилжүүлэх" onClick={() => later.mutate({ params: { path: { item_id: q.id } } })} className="px-1 text-ink-3 hover:text-ink">
                  ↷
                </button>
              )}
              <button type="button" aria-label="Устгах" onClick={() => del.mutate({ params: { path: { item_id: q.id } } })} className="px-1 text-ink-3 hover:text-crit">
                ×
              </button>
            </span>
          </div>
        ))
      )}
      {first && (
        <Link to={replay(first)} className="py-1.5 text-sm">
          Үзээгүй эхний агшнаас 2D replay-д тоглуулах
        </Link>
      )}
    </Panel>
  )
}

function Drills({ d }: { d: Week }) {
  return (
    <Panel title="Сценари дасгал" sub="Сүүлийн албан тоглолтын Review agenda-аас (Focus point-ийн зөвлөмж)">
      {d.drills.length === 0 ? (
        <Empty />
      ) : (
        d.drills.map((x) => (
          <Box key={x.text}>
            <span className="text-[15px] font-semibold">{x.text}</span>
            <Link to={`/matches/${x.match_id}/agenda`} className="text-xs">
              {x.source} · agenda
            </Link>
          </Box>
        ))
      )}
    </Panel>
  )
}

function History({ d }: { d: Week }) {
  return (
    <Panel title="Өмнөх зорилтуудын үр дүн">
      {d.history.length === 0 ? (
        <Empty>Дууссан зорилт алга.</Empty>
      ) : (
        d.history.map((g) => {
          const [word, color] = VERDICT[g.progress.verdict] ?? VERDICT.no_data
          return (
            <div key={g.id} className="grid grid-cols-[86px_minmax(0,1fr)_auto] items-center gap-3 border-t border-line py-2">
              <span className="num text-xs text-ink-3">{g.due_on}</span>
              <span className="text-sm">
                {g.title || g.label} → {g.target}
                {g.unit} {g.status === 'dropped' && <span className="text-ink-3">(цуцалсан)</span>}
              </span>
              <span className="num text-[13px] font-semibold" style={{ color }}>
                {g.progress.value ?? '—'}
                {g.unit} {word}
              </span>
            </div>
          )
        })
      )}
    </Panel>
  )
}

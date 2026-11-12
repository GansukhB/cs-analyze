// The Playbook in v2 (grilled 2026-11-12): one Map of a Fixture with every
// section v1's «Юу хийх» tab shows (their habits with counters and Rounds, Levers
// and Cautions, how others beat them, the five slots, utility, pistols, economy,
// Players, Self-scout), led by both Teams' Tells (CONTEXT.md). The pieces are
// shared with the Self-scout screen: habit cards, Tells and Veto histories.
import { useState, type ReactNode } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { $api } from '../api/client'
import type { components } from '../api/schema'
import type { Advice, AdviceSide, Evidence, Habit, PlaybookPanel, Slot, Tell } from '../gameplan/types'
import UtilityMap from '../gameplan/UtilityMap'
import { usePaths } from '../paths'
import { CRIT, CT, GOOD, MUTED, T, WARN, ghostLink } from './format'
import { type NoteBook, STRENGTH, useNoteBook, viewQuery } from './playbookData'
import { Bar, Box, Empty, Panel, Tag } from './ui'

type VetoHistory = components['schemas']['VetoHistory']

const STALE = 5 * 60_000

const sideColor = (side: string) => (side === 'ct' ? CT : T)

/** A line's evidence: its strength, how many Rounds of how many, and every Round. */
export function Proof({ e, label }: { e: Evidence; label?: string }) {
  const paths = usePaths()
  const [word, color] = STRENGTH[e.strength] ?? STRENGTH.weak
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-3">
      {label && <span>{label}:</span>}
      <Tag color={color}>{word}</Tag>
      <span className="num">
        {e.n}/{e.of} {e.unit ?? 'раунд'} · {e.maps} Map{e.h2h ? ` · ${e.h2h} нь хоорондын` : ''}
      </span>
      {e.refs.map((r) => (
        <Link
          key={`${r.match}-${r.map}-${r.round}`}
          to={paths.match(r.match, r.map, r.round)}
          className="num"
          title={`Replay · тоглолт ${r.match}, ${r.map}-р Map, ${r.round}-р раунд`}
        >
          R{r.round}
        </Link>
      ))}
      {e.refs.length > 1 && (
        <Link to={ghostLink(e.refs)} title="Бүх раундыг давхарлаж үзэх">
          ⧉ давхар
        </Link>
      )}
    </div>
  )
}

function HabitNote({ habit, book }: { habit: Habit; book: NoteBook }) {
  const key = habit.key ?? ''
  const note = book.notes[key]
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const save = $api.useMutation('put', '/playbook-notes', {
    onSuccess: () => {
      setOpen(false)
      book.refresh()
    },
  })
  if (!key) return null
  if (!open)
    return (
      <div className="flex flex-wrap items-baseline gap-2 text-[13px]">
        {note && (
          <span className="text-ink-2">
            <b className="text-accent">Тэмдэглэл:</b> {note.text} <span className="text-ink-3">— {note.by}</span>
          </span>
        )}
        <button
          type="button"
          className="text-xs text-ink-3 underline hover:text-ink"
          onClick={() => {
            setText(note?.text ?? '')
            setOpen(true)
          }}
        >
          {note ? 'засах' : '+ тэмдэглэл'}
        </button>
      </div>
    )
  return (
    <div className="flex flex-col gap-2">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={2}
        maxLength={1000}
        aria-label="Тэмдэглэл"
        className="rounded-md border border-line-strong bg-surface p-2 text-sm text-ink"
      />
      <div className="flex gap-2">
        <button
          type="button"
          disabled={save.isPending}
          onClick={() => save.mutate({ body: { team_id: book.team, map_name: book.map, key, text } })}
          className="h-9 rounded-md bg-accent px-3 text-[13px] font-semibold text-[#0A0D10] disabled:opacity-50"
        >
          Хадгалах
        </button>
        <button type="button" onClick={() => setOpen(false)} className="h-9 rounded-md border border-line-strong px-3 text-[13px] text-ink-2">
          Болих
        </button>
      </div>
    </div>
  )
}

// SB-2: a Set play found in the data becomes a written Strat. Ours keeps its
// grenades and Rounds; theirs becomes our answer on the other Side.
export interface StratFrom {
  whose: 'mine' | 'theirs'
  team: number
  map: string
}

function StratButton({ habit, from }: { habit: Habit; from: StratFrom }) {
  const navigate = useNavigate()
  const paths = usePaths()
  const create = $api.useMutation('post', '/strats', { onSuccess: (s) => navigate(paths.strat(s.id)) })
  const side = habit.spec?.side ?? 't'
  const ours = from.whose === 'mine'
  const mySide = ours ? side : side === 't' ? 'ct' : 't'
  const make = () =>
    create.mutate({
      body: {
        team_id: from.team,
        map_name: from.map,
        side: mySide,
        name: (ours ? habit.title : `Эсрэг: ${habit.title}`).slice(0, 120),
        kind: ours ? (side === 't' ? 'execute' : 'setup') : mySide === 'ct' ? 'setup' : 'default',
        description: ours ? habit.detail : `Тэдний set play: ${habit.title}. ${habit.counter}`,
        roles: [],
        grenades: ours
          ? (habit.spec?.grenades ?? []).map((g) => ({
              slot: null,
              type: (['smoke', 'flash', 'he', 'inferno', 'decoy'].includes(g.type) ? g.type : 'smoke') as 'smoke',
              place: g.place,
              at: g.at,
              note: '',
              lineup: null,
            }))
          : [],
        timings: '',
        variations: '',
        calls: '',
        tags: ['set play'],
        status: 'draft',
        visibility: 'staff',
        examples: habit.evidence.refs.slice(0, 8).map((r) => ({ match_id: r.match, map_number: r.map, round: r.round, note: '' })),
      },
    })
  return (
    <button type="button" className="self-start text-[13px] text-accent underline disabled:opacity-50" disabled={create.isPending} onClick={make}>
      {ours ? 'Strat болгох' : 'Эсрэг Strat бичих'}
      {create.isError && <span className="text-crit"> — зөвхөн манай багийн Strat бичнэ</span>}
    </button>
  )
}

export function HabitCard({ h, book, strat }: { h: Habit; book?: NoteBook; strat?: StratFrom }) {
  const [, color] = STRENGTH[h.evidence?.strength ?? 'weak'] ?? STRENGTH.weak
  return (
    <div className="flex min-w-0 flex-col gap-1.5 rounded-md border border-l-[3px] border-line-soft bg-surface-2 p-3.5" style={{ borderLeftColor: color }}>
      <span className="text-[15px] font-semibold">{h.title}</span>
      {h.detail && <span className="text-[13px] text-ink-2">{h.detail}</span>}
      {h.counter && (
        <span className="text-sm leading-snug">
          <span className="lbl mr-1.5 !text-good">Хариу</span>
          {h.counter}
        </span>
      )}
      {h.review && <span className="text-[13px] text-ink-3">{h.review}</span>}
      {h.evidence && <Proof e={h.evidence} />}
      {strat && h.kind === 'set_play' && <StratButton habit={h} from={strat} />}
      {book && <HabitNote habit={h} book={book} />}
    </div>
  )
}

export function HabitList(props: { habits: Habit[]; book?: NoteBook; strat?: StratFrom; empty?: string }) {
  if (!props.habits.length) return <Empty>{props.empty ?? '4-өөс доошгүй раундад давтагдсан зуршил алга.'}</Empty>
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(min(340px,100%),1fr))] gap-2.5">
      {props.habits.map((h, i) => (
        <HabitCard key={`${h.kind}-${h.key ?? i}`} h={h} book={props.book} strat={props.strat} />
      ))}
    </div>
  )
}

/** One decision point: its top option's share against the Pool's bar. */
function TellRow({ t, whose }: { t: Tell; whose: 'theirs' | 'mine' }) {
  const share = Math.round(100 * t.share)
  const bar = t.pool_p75 == null ? null : Math.round(100 * t.pool_p75)
  const color = t.tell ? (whose === 'theirs' ? GOOD : WARN) : MUTED
  return (
    <div className={`flex flex-col gap-1.5 border-t-1 border-line py-3 ${t.tell ? '' : 'opacity-75'}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="flex flex-wrap items-baseline gap-2">
          <Tag color={sideColor(t.side)}>{t.side.toUpperCase()}</Tag>
          <span className="lbl">{t.label}</span>
          <span className="text-[15px] font-semibold">{t.title}</span>
        </span>
        {t.tell && <Tag color={color} solid>{whose === 'theirs' ? 'Ашиглах' : 'Таагдахуйц'}</Tag>}
      </div>
      <div className="relative">
        <Bar pct={share} color={color} h={6} />
        {bar != null && (
          <span className="absolute -top-1 h-3.5 w-0.5 bg-ink" style={{ left: `${bar}%` }} title={`Pool-д дөрвөн багийн нэг нь ${bar}%+`} />
        )}
      </div>
      <span className="text-[13px] text-ink-2">{t.detail}</span>
      {t.mix.length > 1 && (
        <span className="text-xs text-ink-3">
          Бусад: {t.mix.slice(1).map((m) => `${m.text} ${m.n}`).join(' · ')}
        </span>
      )}
      {t.counter && <span className="text-sm leading-snug">{t.counter}</span>}
      <Proof e={t.evidence} />
    </div>
  )
}

export function TellList({ tells, whose, empty }: { tells: Tell[]; whose: 'theirs' | 'mine'; empty?: string }) {
  const [all, setAll] = useState(false)
  if (!tells.length) return <Empty>{empty ?? 'Шийдвэрийн цэг уншихад хангалттай раунд алга.'}</Empty>
  const found = tells.filter((t) => t.tell)
  const shown = all ? tells : found
  return (
    <div className="flex flex-col">
      {found.length === 0 && !all && (
        <Empty>
          {whose === 'theirs'
            ? 'Pool-ийн багуудаас илүү таамаглагдах сонголт алга.'
            : 'Бид Pool-ийн багуудаас илүү таамаглагдахгүй байна.'}
        </Empty>
      )}
      {shown.map((t) => (
        <TellRow key={`${t.point}-${t.side}`} t={t} whose={whose} />
      ))}
      {tells.length > found.length && (
        <button type="button" onClick={() => setAll(!all)} className="self-start pt-2 text-[13px] text-ink-3 underline">
          {all ? 'Зөвхөн таамаглагдахыг' : `Бусад ${tells.length - found.length} шийдвэрийн цэг`}
        </button>
      )}
    </div>
  )
}

const ACTION: Record<string, [string, string]> = { ban: ['Ban', CRIT], pick: ['Pick', GOOD], decider: ['Decider', WARN] }

/** A Team's Veto history (CONTEXT.md: Veto): per format its Maps and Tells, then its latest. */
export function VetoHistoryView({ v, whose }: { v: VetoHistory; whose: 'theirs' | 'mine' }) {
  const [fmt, setFmt] = useState<number | null>(null)
  const formats = v.formats
  const chosen = formats.find((f) => f.best_of === fmt) ?? formats.find((f) => f.best_of === 3) ?? formats[0]
  if (!chosen) return <Empty>{v.since}-аас хойш veto бүртгэгдээгүй (HLTV-ийн хуудсанд байхгүй эсвэл Scout уншаагүй).</Empty>
  const max = Math.max(1, ...chosen.maps.map((m) => Math.max(m.banned, m.picked, m.left)))
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-[13px] text-ink-3">
          {v.since}-аас хойш (Active Duty өөрчлөгдсөнөөс) {v.vetoes} veto
        </span>
        {formats.length > 1 && (
          <div role="group" aria-label="Формат" className="flex gap-1.5">
            {formats.map((f) => (
              <button
                key={f.best_of}
                type="button"
                aria-pressed={f === chosen}
                onClick={() => setFmt(f.best_of)}
                className={`h-9 rounded-md border px-3 text-[13px] ${f === chosen ? 'border-accent bg-accent-soft text-accent' : 'border-line-strong text-ink-2'}`}
              >
                Bo{f.best_of} <span className="num text-ink-3">{f.vetoes}</span>
              </button>
            ))}
          </div>
        )}
      </div>
      {chosen.tells.length > 0 && (
        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(260px,100%),1fr))] gap-2">
          {chosen.tells.map((t) => (
            <Box key={t.point}>
              <div className="flex items-baseline justify-between gap-2">
                <span className="lbl">{t.label}</span>
                {t.tell && <Tag color={whose === 'theirs' ? GOOD : WARN} solid>{whose === 'theirs' ? 'Ашиглах' : 'Таагдахуйц'}</Tag>}
              </div>
              <span className="cond text-lg font-bold">{t.title}</span>
              <span className="text-[13px] text-ink-2">{t.detail}</span>
              {t.counter && <span className="text-sm">{t.counter}</span>}
            </Box>
          ))}
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="grid-table nums">
          <thead>
            <tr>
              <th>Map</th>
              <th>Эхний ban</th>
              <th>Ban</th>
              <th>Pick</th>
              <th>Decider</th>
            </tr>
          </thead>
          <tbody>
            {chosen.maps.map((m) => (
              <tr key={m.map}>
                <td className="cond !font-[inherit] font-semibold">{m.label}</td>
                <td>{m.first_ban || '—'}</td>
                {(
                  [
                    [m.banned, CRIT],
                    [m.picked, GOOD],
                    [m.left, WARN],
                  ] as const
                ).map(([n, color], i) => (
                  <td key={i}>
                    <div className="flex items-center gap-2">
                      <Bar pct={(100 * n) / max} color={color} h={6} className="w-16" />
                      <span>{n || '—'}</span>
                    </div>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details>
        <summary className="cursor-pointer text-[13px] text-ink-3">Сүүлийн {v.recent.length} veto</summary>
        <div className="mt-2 flex flex-col gap-2">
          {v.recent.map((r) => (
            <div key={r.match_id} className="flex flex-wrap items-center gap-1.5 text-xs">
              <span className="num w-20 text-ink-3">{r.played_at}</span>
              <span className="w-28 truncate text-ink-2" title={r.opponent}>
                vs {r.opponent}
              </span>
              <span className="num text-ink-3">Bo{r.best_of ?? '?'}</span>
              {r.steps.map((s) => {
                const [word, color] = ACTION[s.action] ?? ACTION.ban
                return (
                  <span
                    key={s.step}
                    title={`${s.step}. ${s.mine ? v.team.name : s.action === 'decider' ? '' : r.opponent} ${word}`}
                    className="rounded border px-1.5 py-0.5"
                    style={{ borderColor: s.mine ? color : 'var(--line-strong)', color: s.mine ? color : 'var(--ink-3)' }}
                  >
                    {s.label}
                  </span>
                )
              })}
            </div>
          ))}
        </div>
        <p className="mt-2 text-xs text-ink-3">Өнгөтэй нь {v.team.name}-ийн алхам: улаан ban, ногоон pick, шар decider.</p>
      </details>
    </div>
  )
}

function SlotList({ slots, title, side }: { slots: Slot[] | null | undefined; title: string; side: 'ct' | 't' }) {
  return (
    <Box>
      <div className="flex items-center gap-2">
        <Tag color={sideColor(side)}>{side.toUpperCase()}</Tag>
        <span className="text-sm font-semibold">{title}</span>
      </div>
      {!slots?.length ? (
        <Empty>20 с-д таваараа амьд 8+ раунд алга.</Empty>
      ) : (
        slots.map((s, i) => (
          <div key={i} className="flex flex-wrap items-baseline gap-x-2 border-t-1 border-line-soft pt-1.5 text-[13px]">
            <b>{s.name || '?'}</b>
            {s.lean && s.lean !== 'mid' && <span className="text-ink-3">({s.lean})</span>}
            <span className="text-ink-2">{s.players.map((p) => `${p.name} ${Math.round(p.share * 100)}%`).join(', ')}</span>
          </div>
        ))
      )}
    </Box>
  )
}

export function Slots(props: { slots?: Record<string, Record<string, Slot[] | null> | undefined>; names: Record<string, string> }) {
  const whose = Object.keys(props.names)
  return (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(300px,100%),1fr))] gap-2.5">
        {whose.flatMap((w) =>
          (['ct', 't'] as const).map((side) => (
            <SlotList key={`${w}-${side}`} slots={props.slots?.[w]?.[side]} title={props.names[w]} side={side} />
          )),
        )}
      </div>
      <span className="text-xs text-ink-3">
        20 с-д бүгд амьд раунд бүрийн таван тоглогчийг багийн таван байрлалд Hungarian аргаар тааруулав; хувь нь хэн тэр
        slot-ыг хэдэн раундад эзэлснийг заана.
      </span>
    </div>
  )
}

function AdviceCard({ a }: { a: Advice }) {
  const [word, color] = STRENGTH[a.strength] ?? STRENGTH.weak
  return (
    <div className="flex flex-col gap-1.5 rounded-md border border-line-soft bg-surface-2 p-3.5">
      <div className="flex flex-wrap items-center gap-2">
        {a.pair && <Tag color="var(--accent)">Хос</Tag>}
        <Tag color={color}>{word}</Tag>
        <span className="num text-xs text-ink-3">{a.weight_label}</span>
      </div>
      <span className="text-[15px] font-semibold">{a.title}</span>
      {a.facts.map((f) => (
        <span key={f} className="text-[13px] text-ink-2">
          {f}
        </span>
      ))}
      {a.counter && <span className="text-sm">{a.counter}</span>}
      {a.proofs.map((p) => (
        <Proof key={p.whose} e={p.evidence} label={a.proofs.length > 1 ? p.label : undefined} />
      ))}
    </div>
  )
}

function AdviceColumn({ title, color, entries, none }: { title: string; color: string; entries: Advice[]; none: string }) {
  const [all, setAll] = useState(false)
  const shown = all ? entries : entries.slice(0, 4)
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <span className="lbl" style={{ color }}>
        {title}
      </span>
      {entries.length === 0 ? <Empty>{none}</Empty> : shown.map((a, i) => <AdviceCard key={`${a.title}-${i}`} a={a} />)}
      {entries.length > 4 && (
        <button type="button" onClick={() => setAll(!all)} className="self-start text-[13px] text-ink-3 underline">
          {all ? 'Хураах' : `Бусад ${entries.length - 4}`}
        </button>
      )}
    </div>
  )
}

function AdviceSideView({ side }: { side: AdviceSide }) {
  return (
    <Box className="gap-3">
      <div className="flex items-center gap-2">
        <Tag color={sideColor(side.side)}>{side.label}</Tag>
      </div>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(300px,100%),1fr))] gap-3">
        <AdviceColumn title="Ашиглах" color={GOOD} entries={side.levers} none="Энэ талд ашиглах тод давуу тал гарсангүй." />
        <AdviceColumn title="Анхаарах" color={WARN} entries={side.cautions} none="Энэ талд онцгой анхааруулга гарсангүй." />
      </div>
    </Box>
  )
}

// GP-9: read the habits over some Rounds only; the choice rides in the URL.
const BUY_VIEW: [string, string][] = [
  ['', 'Бүх buy'],
  ['full', 'Full buy'],
  ['light', 'Eco/force'],
]
const DAYS_VIEW: [string, string][] = [
  ['', 'Бүх хугацаа'],
  ['180', '180 хоног'],
  ['90', '90 хоног'],
  ['30', '30 хоног'],
]
const SCORE_VIEW: [string, string][] = [
  ['', 'Бүх оноо'],
  ['ahead', 'Тэргүүлж'],
  ['close', 'Ойр'],
  ['behind', 'Хоцорч'],
]

function Chips(props: { options: [string, string][]; value: string; onChange: (v: string) => void; label: string }) {
  return (
    <div role="group" aria-label={props.label} className="flex flex-wrap gap-1.5">
      {props.options.map(([k, text]) => (
        <button
          key={k || 'all'}
          type="button"
          aria-pressed={k === props.value}
          onClick={() => props.onChange(k)}
          className={`h-9 rounded-md border px-3 text-[13px] ${k === props.value ? 'border-accent bg-accent-soft text-accent' : 'border-line-strong text-ink-2 hover:text-ink'}`}
        >
          {text}
        </button>
      ))}
    </div>
  )
}

/** The GP-9 view chips (buy, days, score) on the page URL. */
export function ViewChips({ score = true, note }: { score?: boolean; note?: ReactNode }) {
  const [search, setSearch] = useSearchParams()
  const pick = (key: string, value: string) => {
    const next = new URLSearchParams(search)
    if (value) next.set(key, value)
    else next.delete(key)
    setSearch(next, { replace: true })
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="lbl">Раунд</span>
      <Chips label="Худалдан авалт" options={BUY_VIEW} value={search.get('buy') ?? ''} onChange={(v) => pick('buy', v)} />
      <Chips label="Хугацаа" options={DAYS_VIEW} value={search.get('days') ?? ''} onChange={(v) => pick('days', v)} />
      {score && <Chips label="Оноо" options={SCORE_VIEW} value={search.get('score') ?? ''} onChange={(v) => pick('score', v)} />}
      {note && <span className="num text-xs text-ink-3">{note}</span>}
    </div>
  )
}

function Section(props: { title: string; sub?: string; children: ReactNode; id?: string }) {
  return (
    <Panel title={props.title} sub={props.sub}>
      <div id={props.id} className="flex flex-col gap-3">
        {props.children}
      </div>
    </Panel>
  )
}

/** One Map of the Fixture, the whole Playbook, in the design's panels. */
export function MapPlaybook(props: {
  mine: number
  theirs: number
  map: string
  query: Record<string, string>
  names: { mine: string; theirs: string }
  sheet: string
}) {
  const { mine, theirs, map } = props
  const [search] = useSearchParams()
  const view = viewQuery(search)
  const q = $api.useQuery(
    'get',
    '/gameplan/{mine}/vs/{theirs}/playbook/{map_name}',
    { params: { path: { mine, theirs, map_name: map }, query: { ...props.query, ...view } } },
    { staleTime: STALE, retry: false },
  )
  const theirBook = useNoteBook(theirs, map)
  const ourBook = useNoteBook(mine, map)
  if (q.isError) return <Panel><Empty>Энэ Map-ын Playbook-ийг тооцоолж чадсангүй.</Empty></Panel>
  if (!q.data) return <Panel><Empty>Playbook-ийг тооцоолж байна…</Empty></Panel>
  const d = q.data.data as unknown as PlaybookPanel
  const { theirs: them, mine: us } = d.sample
  const filtered = Object.keys(view).length > 0
  const caveats: string[] = []
  if (them.all_maps !== undefined && them.all_maps > them.maps)
    caveats.push(`${d.opponent}-ийн зуршлыг одоогийн бүрэлдэхүүний (Lineup-ийн 4+ тоглогч) ${them.maps} Map-аас уншив; хуучин бүрэлдэхүүнтэй ${them.all_maps - them.maps} Map тооцогдоогүй.`)
  if (!them.maps) caveats.push(`${d.opponent} энэ Map-ыг тоглоогүй: зөвхөн Self-scout харагдана.`)
  if (them.maps > 0 && !them.economy) caveats.push('Эдийн засгийн дата алга: эдгээр Map-ыг эдийн засаг хадгалдаг болохоос өмнө parse хийсэн.')
  if (!d.sites_known) caveats.push('Энэ Map-ын цэгүүдийн байрлал тодорхойгүй тул A / төв / B хуваарь гарахгүй.')
  caveats.push(...d.advice.limits)
  const sections = Object.fromEntries(d.sections.map((s) => [s.key, s]))
  return (
    <>
      <Panel
        title={`${d.label} · Playbook`}
        sub={`${d.opponent}: ${them.maps} Map (${them.h2h_maps} нь хоорондын), T ${them.rounds.t} · CT ${them.rounds.ct} раунд · ${d.my_team}: ${us.maps} Map`}
        right={
          <span className="flex flex-wrap gap-3 text-[13px]">
            <Link to={props.sheet}>Map хуудас (хэвлэх)</Link>
          </span>
        }
      >
        <ViewChips note={filtered && d.view ? `${d.view.rounds}/${d.view.of} раунд — эдийн засаг, pistol бүх раундаар` : undefined} />
        {caveats.map((c) => (
          <span key={c} className="text-[13px] text-warn">
            {c}
          </span>
        ))}
      </Panel>

      <section className="grid grid-cols-[repeat(auto-fit,minmax(min(440px,100%),1fr))] gap-4">
        <Panel title="Тэдний таамаглагдах зуршил" sub="Pool-ийн багуудаас илүү давтан хийдэг сонголт: үүнд бэлдэж ашиглана">
          <TellList tells={d.tells?.theirs ?? []} whose="theirs" />
        </Panel>
        <Panel title="Манай таамаглагдах зуршил" sub="Өрсөлдөгч анзаарвал anti-strat хийж чадах сонголт">
          <TellList tells={d.tells?.mine ?? []} whose="mine" />
        </Panel>
      </section>

      {d.plan.length > 0 && (
        <Section title="Гол төлөвлөгөө" sub="Тэдний хамгийн хүчтэй зуршил тус бүрийн хариу">
          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(300px,100%),1fr))] gap-2.5">
            {d.plan.map((p, i) => (
              <Box key={i}>
                <div className="flex items-center gap-2">
                  <Tag color={sideColor(p.side)}>Манай {p.side.toUpperCase()}</Tag>
                  <Tag color={STRENGTH[p.strength][1]}>{STRENGTH[p.strength][0]}</Tag>
                </div>
                <span className="text-[15px] font-semibold">{p.title}</span>
                <span className="text-sm text-ink-2">{p.counter}</span>
              </Box>
            ))}
          </div>
        </Section>
      )}

      <Section
        title="Ашиглах ба анхаарах"
        sub="Хоёр багийн Review-г Pool-той харьцуулав: манай давуу тал тэдний сул талтай тулгарсан нь эхэнд. Жин нь хагас тутамд ердийн багаас хэдэн раундын зөрүү гаргадгийг заана."
      >
        {d.advice.sides.map((s) => (
          <AdviceSideView key={s.side} side={s} />
        ))}
      </Section>

      {(['their_t', 'their_ct'] as const).map((key) =>
        sections[key] ? (
          <Section key={key} title={sections[key].title}>
            <HabitList habits={sections[key].habits} book={theirBook} strat={{ whose: 'theirs', team: mine, map }} />
          </Section>
        ) : null,
      )}

      {d.beaten_by.length > 0 && (
        <Section title="Бусад баг тэднийг яаж хожсон" sub="Тэднийг ердийнхөөсөө доош барьсан хариунууд">
          {d.beaten_by.map((b, i) => (
            <Box key={i}>
              <span className="flex items-baseline gap-2 text-sm">
                <Tag color={sideColor(b.side)}>{b.side.toUpperCase()}</Tag>
                {b.text}
              </span>
              <Proof e={b.evidence} />
            </Box>
          ))}
        </Section>
      )}

      {d.slots && (
        <Section title="Хэн хаана: 20 с-д таван slot">
          <Slots slots={d.slots} names={{ theirs: props.names.theirs, mine: props.names.mine }} />
        </Section>
      )}

      <Section title="Utility-ийн зураг">
        <div className="text-sm">
          <UtilityMap mine={mine} theirs={theirs} map={map} />
        </div>
      </Section>

      <Section title="Pistol раунд">
        {d.conversion.length > 0 && (
          <div className="overflow-x-auto">
            <table className="grid-table nums">
              <thead>
                <tr>
                  <th>Баг</th>
                  <th>Pistol хожсон</th>
                  <th>Дараагийн 2-ыг хожсон</th>
                  <th>Алдаад 2-оос 1-ийг авсан</th>
                  <th>2 pistol → Map</th>
                </tr>
              </thead>
              <tbody>
                {d.conversion.map((c) => (
                  <tr key={c.team}>
                    <td>{c.team}</td>
                    <td>{c.pistols}</td>
                    <td>{c.converted}</td>
                    <td>{c.broken}</td>
                    <td>{c.both}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {(d.pistol_plan ?? []).map((line) => (
          <span key={line} className="text-sm">
            {line}
          </span>
        ))}
        <PistolRounds pistols={d.pistols} />
      </Section>

      <Section title="Эдийн засаг (бүх Map-аар)">
        {d.economy.known && d.economy.buys ? (
          <>
            <div className="flex flex-wrap gap-4 text-sm">
              {(['eco', 'force', 'full'] as const).map((b) => (
                <span key={b}>
                  <b>{b}</b> <span className="num">{d.economy.buys?.[b].n}</span> раунд,{' '}
                  <span className="num">{d.economy.buys?.[b].won}</span> хожсон
                </span>
              ))}
            </div>
            <HabitList habits={d.economy.habits} book={theirBook} empty="Эдийн засгийн давтагдсан зуршил алга." />
            {(d.economy.choices ?? []).map((c) => (
              <span key={c.text} className="flex items-baseline gap-2 text-sm">
                {c.costly && <Tag color={GOOD}>Ашиглах</Tag>}
                {c.text}
              </span>
            ))}
          </>
        ) : (
          <Empty>Эдийн засгийн дата алга.</Empty>
        )}
      </Section>

      <Section title="Тоглогчид ба matchup" sub="Тэдний тоглогч бүр: байрлал, нээлт, бидэнтэй хийсэн duel, Review-ийн дүгнэлт">
        {d.players.length === 0 ? (
          <Empty>Тоглогчийн дата алга.</Empty>
        ) : (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(min(320px,100%),1fr))] gap-2.5">
            {d.players.map((p) => (
              <Box key={p.player}>
                <div className="flex flex-wrap items-baseline gap-2">
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
                {(p.card ?? []).map((l) => (
                  <span key={l} className="text-[13px] text-ink-3">
                    Review: {l}
                  </span>
                ))}
              </Box>
            ))}
          </div>
        )}
      </Section>

      <Section title="Self-scout: манай зуршил" sub="Тэдэнд бидний талаар ижил аргаар харагдах зуршил; хариу нь өрсөлдөгч яаж ашиглаж болохыг хэлнэ">
        {d.self_scout.map((s) => (
          <div key={s.side} className="flex flex-col gap-2">
            <Tag color={sideColor(s.side)}>{s.label}</Tag>
            <HabitList habits={s.habits} book={ourBook} strat={{ whose: 'mine', team: mine, map }} />
          </div>
        ))}
      </Section>
    </>
  )
}

function PistolRounds({ pistols }: { pistols: PlaybookPanel['pistols'] }) {
  const paths = usePaths()
  if (!pistols.length) return <Empty>Энэ Map дээр тэдний pistol раунд алга.</Empty>
  return (
    <div className="flex flex-col gap-1">
      {pistols.map((p) => (
        <span key={`${p.ref.match}-${p.ref.map}-${p.ref.round}`} className="flex flex-wrap items-baseline gap-2 text-[13px]">
          <Link className="num" to={paths.match(p.ref.match, p.ref.map, p.ref.round)}>
            R{p.ref.round}
          </Link>
          {p.h2h && <Tag color="var(--them)">h2h</Tag>}
          <span>{p.text}</span>
          {p.next && <span className="text-ink-3">· {p.next}</span>}
        </span>
      ))}
    </div>
  )
}

// One Map on one page (docs/plans/06 GP-3): the Playbook, the style, the
// timeout card and the cautions cut to the two or three weightiest lines a
// section, every line with its Evidence strength, for paper or a phone.
import { useMemo } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { $api } from '../api/client'
import { lineupQuery, readLineups } from '../gameplan/lineup'
import type { Habit, PlaybookPanel, Strength } from '../gameplan/types'

const LINES = 3
const STRENGTH: Record<Strength, string> = { weak: 'сул', medium: 'дунд', strong: 'хүчтэй' }
const ORDER: Record<Strength, number> = { strong: 0, medium: 1, weak: 2 }

const top = (habits: Habit[]) =>
  [...habits].sort((a, b) => ORDER[a.evidence.strength] - ORDER[b.evidence.strength]).slice(0, LINES)

function Tag({ s }: { s: Strength }) {
  return (
    <span className={`mr-1 rounded border px-1 text-[10px] uppercase ${s === 'weak' ? 'border-line text-ink-3' : 'border-ink-3 text-ink-2'}`}>
      {STRENGTH[s]}
    </span>
  )
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="break-inside-avoid space-y-1">
      <h2 className="border-b border-line pb-0.5 text-sm font-semibold text-ink">{title}</h2>
      {children}
    </section>
  )
}

function Habits({ habits }: { habits: Habit[] }) {
  if (!habits.length) return <p className="text-xs text-ink-3">Давтагдсан зүйл алга.</p>
  return (
    <ul className="space-y-1 text-xs text-ink-2">
      {top(habits).map((h, i) => (
        <li key={i}>
          <Tag s={h.evidence.strength} />
          <b className="text-ink">{h.title}</b> — {h.counter}
        </li>
      ))}
    </ul>
  )
}

const EVIDENCE: [string, string][] = [
  ['metrics', 'Үзүүлэлт'],
  ['h2h', 'Хоорондын тоглолт'],
  ['players', 'Тоглогчид'],
  ['roles', 'Үүрэг'],
  ['duels', 'Дуэль'],
  ['edge', 'Тулгуур ба тоо'],
]

export default function MapSheetPage() {
  const params = useParams()
  const mine = Number(params.mine)
  const theirs = Number(params.theirs)
  const map = params.map ?? ''
  const [search] = useSearchParams()
  const query = useMemo(() => lineupQuery(readLineups(search)), [search])
  const path = { mine, theirs, map_name: map }
  const pb = $api.useQuery('get', '/gameplan/{mine}/vs/{theirs}/playbook/{map_name}', { params: { path, query } })
  const card = $api.useQuery('get', '/gameplan/{mine}/vs/{theirs}/timeout/{map_name}', { params: { path } })
  const style = $api.useQuery('get', '/gameplan/{mine}/vs/{theirs}/style/{map_name}', { params: { path } })
  if (pb.isError) return <p className="text-ink-2">Энэ map-ын Playbook-ийг тооцоолж чадсангүй.</p>
  if (!pb.data) return <p className="text-ink-3">Playbook-ийг тооцоолж байна…</p>
  const d = pb.data.data as unknown as PlaybookPanel
  const section = (key: string) => d.sections.find((s) => s.key === key)?.habits ?? []
  const lever = (side: 'ct' | 't') => d.advice.sides.find((s) => s.side === side)
  const theirStyle = style.data?.theirs.sides ?? []
  const pressed = (card.data?.sides ?? []).flatMap((s) => s.moves.map((m) => ({ ...m, side: s.side })))

  return (
    <article className="mx-auto max-w-[1024px] space-y-4 text-sm print:text-[11px]">
      <header className="flex flex-wrap items-baseline gap-x-4">
        <h1 className="text-xl font-semibold text-ink">
          {d.label} — {d.my_team} vs {d.opponent}
        </h1>
        <span className="text-xs text-ink-3">
          {d.opponent}: {d.sample.theirs.maps} map ({d.sample.theirs.h2h_maps} хоорондын) · {d.my_team}:{' '}
          {d.sample.mine.maps} map
        </span>
        <span className="ml-auto flex flex-wrap gap-3 text-xs print:hidden">
          <Link to={`/gameplan/${mine}/vs/${theirs}/s/todo/m/${map}?${search}`} className="text-ct hover:underline">
            Playbook
          </Link>
          {/* GP-14: the evidence behind the page, one click away. */}
          {EVIDENCE.map(([key, label]) => (
            <Link key={key} to={`/gameplan/${mine}/vs/${theirs}/s/${key}?${search}`} className="text-ink-3 hover:text-ct">
              {label}
            </Link>
          ))}
          <button type="button" onClick={() => window.print()} className="text-ct underline">
            Хэвлэх
          </button>
        </span>
      </header>

      <div className="grid gap-4 md:grid-cols-2">
        <Block title={`Тэдний T → манай CT`}>
          <Habits habits={section('their_t')} />
        </Block>
        <Block title={`Тэдний CT → манай T`}>
          <Habits habits={section('their_ct')} />
        </Block>
        <Block title="Эдийн засаг ба pistol">
          <Habits habits={d.economy.habits} />
          <ul className="space-y-0.5 text-xs text-ink-2">
            {d.conversion.slice(0, 2).map((c) => (
              <li key={c.team}>
                <b className="text-ink">{c.team}</b>: {c.pistols}
              </li>
            ))}
          </ul>
        </Block>
        <Block title="Тоглогчид">
          <ul className="space-y-0.5 text-xs text-ink-2">
            {d.players.slice(0, 5).map((p) => (
              <li key={p.player}>
                <b className="text-ink">{p.player}</b> {p.tags.join(', ')} — {p.lines[0] ?? p.duels}
              </li>
            ))}
          </ul>
        </Block>
        <Block title="Манай төлөвлөгөө">
          <ul className="space-y-1 text-xs text-ink-2">
            {(['ct', 't'] as const).map((side) =>
              (lever(side)?.levers ?? []).slice(0, 2).map((a, i) => (
                <li key={`${side}-${i}`}>
                  <span className="mr-1 font-mono text-ink-3">{side.toUpperCase()}</span>
                  <Tag s={a.strength} />
                  <b className="text-ink">{a.title}</b> — {a.counter}
                </li>
              )),
            )}
          </ul>
        </Block>
        <Block title="Бусад баг тэднийг яаж хожсон">
          <ul className="space-y-0.5 text-xs text-ink-2">
            {d.beaten_by.slice(0, LINES).map((b, i) => (
              <li key={i}>
                <span className="mr-1 font-mono text-ink-3">{b.side.toUpperCase()}</span>
                {b.text}
              </li>
            ))}
            {!d.beaten_by.length && <li className="text-ink-3">Тодорхой хариу илрээгүй.</li>}
          </ul>
        </Block>
        <Block title="Дарамтанд (timeout card)">
          <ul className="space-y-0.5 text-xs text-ink-2">
            {pressed.slice(0, LINES).map((m) => (
              <li key={`${m.side}-${m.key}`}>
                <span className="mr-1 font-mono text-ink-3">{m.side.toUpperCase()}</span>
                {m.label}: {m.usual}% → {m.pressed}% — {m.counter}
              </li>
            ))}
            {!pressed.length && <li className="text-ink-3">Тогтвортой өөрчлөлт алга.</li>}
          </ul>
        </Block>
        <Block title="Хэв маяг (percentile)">
          <ul className="space-y-0.5 text-xs text-ink-2">
            {theirStyle
              .flatMap((s) => s.metrics)
              .filter((m) => m.pct != null && !m.thin && (m.pct >= 80 || m.pct <= 20))
              .slice(0, 4)
              .map((m) => (
                <li key={m.key}>
                  {m.label}: {m.unit === 's' ? `${m.value} с` : `${Math.round(m.value)}%`} ·{' '}
                  <b className="text-ink">{m.pct}-р percentile</b>
                </li>
              ))}
          </ul>
        </Block>
      </div>

      {d.advice.limits.length > 0 && (
        <Block title="Анхааруулга">
          <ul className="space-y-0.5 text-xs text-warn">
            {d.advice.limits.slice(0, LINES).map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </Block>
      )}
    </article>
  )
}

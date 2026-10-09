import { useState } from 'react'
import type { components } from '../api/schema'
import { TEAM_DOT, weightText } from './format'

type Item = components['schemas']['SummaryItem']
type Ref = components['schemas']['SummaryRef']
type NumberRow = components['schemas']['SummaryNumber']

/** Opens a Summary line's moment: in the Replay on a Map, on its Map's page from a Match. */
export type OnRef = (ref: Ref) => void

const TONE: Record<string, string> = { good: 'text-good', bad: 'text-crit' }

/**
 * One Team's Summary (CONTEXT.md): its numbers, its Focus points with what to
 * work on, then what went well and what else went wrong. Every line opens the
 * Rounds behind it.
 */
export function TeamSummaryCard(props: {
  name: string
  teamIndex: number
  /** "13–5" over the Map, or the Match's Rounds. */
  score?: string
  numbers?: NumberRow[]
  focus: Item[]
  strengths: Item[]
  problems: Item[]
  onRef: OnRef
  /** Across a Match: Map labels for the Rounds' chips. */
  mapLabels?: Record<number, string>
  empty?: string
}) {
  const { name, teamIndex, score, numbers = [], focus, strengths, problems, onRef, mapLabels, empty } = props
  const inFocus = new Set(focus.map((f) => f.key))
  const rest = problems.filter((p) => !inFocus.has(p.key))
  const nothing = !focus.length && !strengths.length && !rest.length
  return (
    <article className="flex min-w-0 flex-col gap-4 rounded-xl border border-line bg-surface p-4">
      <header className="flex items-baseline gap-2">
        <span className={`size-2.5 self-center rounded-full ${TEAM_DOT[teamIndex] ?? 'bg-ink-3'}`} />
        <h3 className="truncate text-base font-semibold text-ink">{name}</h3>
        {score && <span className="ml-auto font-mono text-lg tabular-nums text-ink">{score}</span>}
      </header>

      {numbers.length > 0 && (
        <dl className="grid grid-cols-3 gap-1.5 sm:grid-cols-4 2xl:grid-cols-5">
          {numbers
            .filter((n) => n.key !== 'rounds')
            .map((n) => (
              <div key={n.key} className="rounded-md bg-surface-2 px-2 py-1.5">
                <dt className="truncate text-[11px] text-ink-3" title={n.label}>
                  {n.label}
                </dt>
                <dd className={`font-mono text-sm tabular-nums ${TONE[n.tone] ?? 'text-ink'}`}>{n.value}</dd>
              </div>
            ))}
        </dl>
      )}

      {focus.length > 0 && (
        <section className="space-y-2">
          <h4 className="text-xs font-medium tracking-wide text-warn uppercase">Анхаарах</h4>
          <ol className="space-y-2">
            {focus.map((item, i) => (
              <li key={item.key} className="rounded-lg border border-warn/30 bg-surface-2 p-2.5">
                <div className="flex gap-2.5">
                  <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-warn/15 font-mono text-xs text-warn">
                    {i + 1}
                  </span>
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex flex-wrap items-baseline gap-x-2">
                      <span className="font-medium text-ink">{item.label}</span>
                      <span className="ml-auto font-mono text-xs text-crit">{weightText(item.weight, false)}</span>
                    </div>
                    <p className="text-sm text-ink-2">{item.text}</p>
                    <p className="text-sm text-ink">→ {item.advice}</p>
                    <RefChips refs={item.refs} onRef={onRef} mapLabels={mapLabels} />
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

      <ItemList title="Сайн" items={strengths} good onRef={onRef} mapLabels={mapLabels} />
      <ItemList title={focus.length ? 'Бусад алдаа' : 'Алдаа'} items={rest} onRef={onRef} mapLabels={mapLabels} />
      {nothing && <p className="text-sm text-ink-3">{empty ?? 'Босго давсан зүйл алга — тоонууд дунджийн хүрээнд.'}</p>}
    </article>
  )
}

const SHOWN = 4

function ItemList(props: { title: string; items: Item[]; good?: boolean; onRef: OnRef; mapLabels?: Record<number, string> }) {
  const { title, items, good = false, onRef, mapLabels } = props
  const [all, setAll] = useState(false)
  if (!items.length) return null
  const shown = all ? items : items.slice(0, SHOWN)
  return (
    <section className="space-y-1.5">
      <h4 className={`text-xs font-medium tracking-wide uppercase ${good ? 'text-good' : 'text-crit'}`}>{title}</h4>
      <ul className="divide-y divide-line-soft">
        {shown.map((item) => (
          <SummaryLine key={`${item.key}-${item.good}`} item={item} onRef={onRef} mapLabels={mapLabels} />
        ))}
      </ul>
      {items.length > SHOWN && (
        <button type="button" onClick={() => setAll(!all)} className="text-xs text-ink-3 hover:text-ink">
          {all ? 'Цөөнийг харуулах' : `+${items.length - SHOWN} бусад`}
        </button>
      )}
    </section>
  )
}

function SummaryLine({ item, onRef, mapLabels }: { item: Item; onRef: OnRef; mapLabels?: Record<number, string> }) {
  const [open, setOpen] = useState(false)
  return (
    <li className="py-1.5">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-start gap-2 text-left">
        <span className={`mt-1.5 size-1.5 shrink-0 rounded-full ${item.good ? 'bg-good' : 'bg-crit'}`} />
        <span className="min-w-0 flex-1 text-sm text-ink-2">{item.text}</span>
        {item.weight >= 0.05 && (
          <span className={`shrink-0 font-mono text-xs ${item.good ? 'text-good' : 'text-crit'}`}>{weightText(item.weight, item.good)}</span>
        )}
      </button>
      {open && (
        <div className="mt-1.5 pl-3.5">
          {item.texts && item.texts.length > 0 && (
            <ul className="mb-1.5 space-y-0.5 text-xs text-ink-3">
              {item.texts.map((t) => (
                <li key={t.map_number}>
                  <b className="font-medium text-ink-2">{mapLabels?.[t.map_number] ?? `Map ${t.map_number}`}:</b> {t.text}
                </li>
              ))}
            </ul>
          )}
          <RefChips refs={item.refs} onRef={onRef} mapLabels={mapLabels} />
        </div>
      )}
    </li>
  )
}

/** The Rounds behind a line, one chip each, opening the Replay there. */
export function RefChips({ refs, onRef, mapLabels }: { refs: Ref[]; onRef: OnRef; mapLabels?: Record<number, string> }) {
  const seen = new Set<string>()
  const chips = refs.filter((r) => {
    const key = `${r.map_number}-${r.round}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
  if (!chips.length) return null
  return (
    <div className="flex flex-wrap gap-1">
      {chips.slice(0, 16).map((r) => (
        <button
          key={`${r.map_number}-${r.round}`}
          type="button"
          onClick={() => onRef(r)}
          title="Replay-д нээх"
          className="rounded border border-line bg-raised px-1.5 py-px font-mono text-[11px] text-ink-2 hover:border-ink-3 hover:text-ink"
        >
          {mapLabels && r.map_number !== null ? `${(mapLabels[r.map_number] ?? '').slice(0, 3)} ` : ''}R{r.round}
        </button>
      ))}
      {chips.length > 16 && <span className="px-1 text-[11px] text-ink-3">+{chips.length - 16}</span>}
    </div>
  )
}

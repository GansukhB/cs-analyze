import type { ReactNode } from 'react'
import type { components } from '../api/schema'
import { type Buy, type Filters, findingPasses, isActive, type Side } from './filters'
import { BUY, KIND_ORDER, KIND_TONE, TEAM_DOT } from './format'

type Review = components['schemas']['Review']

/**
 * The Review's filters in one bar, kept in the URL: Team and Side pick the
 * Summary shown; Buy, Player and kind narrow the Rounds and Findings, and dim
 * the Rounds they leave out on the Replay's round strip.
 */
export default function FilterBar(props: {
  review: Review
  filters: Filters
  set: (patch: Partial<Filters>) => void
  clear: () => void
  /** Rounds the filters leave, of all. */
  matching: number
}) {
  const { review, filters, set, clear, matching } = props
  const rounds = new Map(review.rounds.map((r) => [r.n, r]))
  // Each kind's count under every other filter, so a chip says what it would add.
  const counts: Record<string, number> = {}
  const others = { ...filters, kinds: new Set<string>(KIND_ORDER) }
  for (const f of review.findings) if (findingPasses(f, others, rounds)) counts[f.kind] = (counts[f.kind] || 0) + 1

  const toggleKind = (k: string) => {
    const next = new Set(filters.kinds)
    if (next.has(k)) next.delete(k)
    else next.add(k)
    set({ kinds: next.size ? next : new Set(KIND_ORDER) })
  }

  return (
    <div className="z-20 -mx-1 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-line bg-surface px-3 py-2 text-sm">
      <Group label="Баг">
        <Chip on={filters.team === null} onClick={() => set({ team: null })}>Хоёулаа</Chip>
        {review.teams.map((t, i) => (
          <Chip key={t.id ?? i} on={filters.team === t.id} onClick={() => set({ team: filters.team === t.id ? null : t.id, player: null })}>
            <span className={`size-2 rounded-full ${TEAM_DOT[i] ?? 'bg-ink-3'}`} />
            {t.name}
          </Chip>
        ))}
      </Group>
      <Group label="Тал">
        {([null, 'ct', 't'] as (Side | null)[]).map((s) => (
          <Chip key={s ?? 'all'} on={filters.side === s} onClick={() => set({ side: s })}>
            {s === null ? 'Хоёр тал' : <span className={s === 'ct' ? 'text-ct' : 'text-t'}>{s.toUpperCase()}</span>}
          </Chip>
        ))}
      </Group>
      <Group label="Buy">
        {([null, 'pistol', 'eco', 'force', 'full'] as (Buy | null)[]).map((b) => (
          <Chip key={b ?? 'all'} on={filters.buy === b} onClick={() => set({ buy: b })}>
            {b === null ? 'Бүгд' : BUY[b]}
          </Chip>
        ))}
      </Group>
      <label className="flex items-center gap-1.5">
        <span className="text-xs text-ink-3">Тоглогч</span>
        <select
          value={filters.player ?? ''}
          onChange={(e) => set({ player: e.target.value || null })}
          className="max-w-40 rounded-md border border-line bg-surface-2 px-2 py-1 text-sm text-ink"
        >
          <option value="">Бүгд</option>
          {review.teams.map((t, i) => (
            <optgroup key={t.id ?? i} label={t.name}>
              {review.players
                .filter((p) => p.team_id === t.id)
                .map((p) => (
                  <option key={p.sid} value={p.sid}>
                    {p.name}
                  </option>
                ))}
            </optgroup>
          ))}
        </select>
      </label>
      <Group label="Дүгнэлт">
        {KIND_ORDER.map((k) => (
          <Chip key={k} on={filters.kinds.has(k)} onClick={() => toggleKind(k)}>
            <span className={`size-2 rounded-full ${KIND_TONE[k].bar}`} />
            {review.kinds[k]}
            <span className="font-mono text-xs text-ink-3">{counts[k] || 0}</span>
          </Chip>
        ))}
      </Group>
      {isActive(filters) && (
        <span className="ml-auto flex items-center gap-2 text-xs text-ink-3">
          {matching}/{review.rounds.length} раунд
          <button type="button" onClick={clear} className="rounded-md border border-line px-2 py-0.5 text-ink-2 hover:text-ink">
            ✕ Цэвэрлэх
          </button>
        </span>
      )}
    </div>
  )
}

function Group({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-1" role="group" aria-label={label}>
      <span className="mr-0.5 text-xs text-ink-3">{label}</span>
      {children}
    </div>
  )
}

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={on}
      className={`flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 ${on ? 'border-ink-3 bg-raised text-ink' : 'border-line-soft text-ink-2 hover:text-ink'}`}
    >
      {children}
    </button>
  )
}

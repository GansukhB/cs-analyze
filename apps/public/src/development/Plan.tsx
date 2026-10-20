// A Player's Development plan (docs/plans/07 RV-9): each goal's KPI, where it
// started, where Staff want it, and where it stands since, with its range over
// his Match Maps and Scrims. Staff add goals (from the suggestions or by hand)
// and close them; the Player reads his own.
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { $api } from '../api/client'
import type { components } from '../api/schema'

type Goal = components['schemas']['GoalRead']

const VERDICT: Record<string, { text: string; tone: string }> = {
  reached: { text: 'хүрсэн', tone: 'text-good' },
  close: { text: 'ойрхон', tone: 'text-warn' },
  not_yet: { text: 'хүрээгүй', tone: 'text-ink-2' },
  no_data: { text: 'дата алга', tone: 'text-ink-3' },
}

const fmt = (v: number | null | undefined, unit: string) =>
  v === null || v === undefined ? '—' : `${unit === '%' ? v.toFixed(1) : v.toFixed(2)}${unit === '%' ? '%' : ''}`

// Baseline, target and the current value with its range on one line.
function Bullet({ g }: { g: Goal }) {
  const p = g.progress
  const values = [g.baseline, g.target, p.value, p.low, p.high].filter((v): v is number => v !== null && v !== undefined)
  if (values.length < 2) return null
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const pad = (hi - lo) * 0.15 || 1
  const x = (v: number) => 8 + ((v - (lo - pad)) / (hi - lo + 2 * pad)) * 284
  return (
    <svg viewBox="0 0 300 26" className="h-7 w-full max-w-sm" role="img" aria-label={`${g.label}: progress`}>
      <line x1={8} x2={292} y1={13} y2={13} stroke="var(--line)" strokeWidth={2} />
      {g.baseline !== null && g.baseline !== undefined && (
        <g>
          <line x1={x(g.baseline)} x2={x(g.baseline)} y1={6} y2={20} stroke="var(--ink-3)" strokeWidth={2} />
          <title>Эхлэх үед: {fmt(g.baseline, g.unit)}</title>
        </g>
      )}
      <g>
        <line x1={x(g.target)} x2={x(g.target)} y1={3} y2={23} stroke="var(--good)" strokeWidth={2} />
        <title>Зорилт: {fmt(g.target, g.unit)}</title>
      </g>
      {p.value !== null && p.value !== undefined && p.low !== null && p.high !== null && (
        <g>
          <line x1={x(p.low!)} x2={x(p.high!)} y1={13} y2={13} stroke="var(--ink-2)" strokeWidth={4} strokeLinecap="round" />
          <circle cx={x(p.value)} cy={13} r={5} fill="var(--ink)" stroke="var(--surface)" strokeWidth={2} />
          <title>
            Одоо: {fmt(p.value, g.unit)} (80%: {fmt(p.low, g.unit)}–{fmt(p.high, g.unit)})
          </title>
        </g>
      )}
    </svg>
  )
}

export default function DevelopmentPlan({ steamid, staff }: { steamid: string; staff: boolean }) {
  const queryClient = useQueryClient()
  const plan = $api.useQuery('get', '/players/{steamid}/goals', { params: { path: { steamid } } })
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['get', '/players/{steamid}/goals'] })
  const add = $api.useMutation('post', '/players/{steamid}/goals', { onSuccess: refresh })
  const change = $api.useMutation('patch', '/goals/{goal_id}', { onSuccess: refresh })
  const remove = $api.useMutation('delete', '/goals/{goal_id}', { onSuccess: refresh })
  const [kpi, setKpi] = useState('')
  const [target, setTarget] = useState('')
  if (!plan.data) return null
  const { goals, kpis } = plan.data
  // A KPI that already has an open goal is not suggested again.
  const suggestions = plan.data.suggestions.filter(
    (s) => !goals.some((g) => g.kpi === s.kpi && g.status === 'active'),
  )
  if (!staff && !goals.length) return null
  const error = (add.error as { detail?: string } | undefined)?.detail

  return (
    <section className="space-y-3">
      <h2 className="font-medium text-ink">Хөгжлийн төлөвлөгөө</h2>
      {goals.length === 0 && <p className="text-sm text-ink-3">Зорилго алга.</p>}
      <ul className="space-y-2">
        {goals.map((g) => {
          const v = VERDICT[g.progress.verdict] ?? VERDICT.no_data
          return (
            <li key={g.id} className="rounded-md border border-line bg-surface px-4 py-3 text-sm">
              <div className="flex flex-wrap items-baseline gap-x-3">
                <span className="font-medium text-ink">{g.label}</span>
                <span className="text-xs text-ink-3">
                  {g.better === 'lower' ? 'бага байх тусам сайн' : 'их байх тусам сайн'} · {g.start_on} → {g.due_on}
                  {g.status !== 'active' && ` · ${g.status === 'done' ? 'дууссан' : 'болиулсан'}`}
                </span>
                <span className={`ml-auto ${v.tone}`}>{v.text}</span>
              </div>
              <p className="text-ink-2">
                Эхлэх үед {fmt(g.baseline, g.unit)} · зорилт {fmt(g.target, g.unit)} · одоо{' '}
                <b className="text-ink">{fmt(g.progress.value, g.unit)}</b>
                {g.progress.maps ? ` (${g.progress.maps} map, ${g.progress.rounds} раунд)` : ''}
                {g.unit === '/24' && g.progress.value !== null && g.progress.value !== undefined && ' — 24 раунд тутамд'}
              </p>
              <Bullet g={g} />
              {g.notes && <p className="text-ink-3">{g.notes}</p>}
              {staff && (
                <div className="mt-1 flex gap-3 text-xs">
                  {g.status === 'active' && (
                    <button
                      type="button"
                      className="text-ink-3 underline hover:text-ink"
                      onClick={() => change.mutate({ params: { path: { goal_id: g.id } }, body: { status: 'done' } })}
                    >
                      Дууссан
                    </button>
                  )}
                  {g.status === 'active' && (
                    <button
                      type="button"
                      className="text-ink-3 underline hover:text-ink"
                      onClick={() =>
                        change.mutate({ params: { path: { goal_id: g.id } }, body: { status: 'dropped' } })
                      }
                    >
                      Болиулах
                    </button>
                  )}
                  <button
                    type="button"
                    className="text-ink-3 underline hover:text-ink"
                    onClick={() => remove.mutate({ params: { path: { goal_id: g.id } } })}
                  >
                    Устгах
                  </button>
                </div>
              )}
            </li>
          )
        })}
      </ul>
      {staff && suggestions.length > 0 && (
        <div className="space-y-1 text-sm">
          <p className="text-ink-3">Санал (сүүлийн 90 хоног, бусад тоглогчдоос тод давсан):</p>
          {suggestions.map((s) => (
            <div key={s.kpi} className="flex flex-wrap items-center gap-3">
              <span className="text-ink">{s.label}</span>
              <span className="text-xs text-ink-3">
                24 раундад {s.baseline} → {s.target} ({s.events} удаа, ~{Math.round(s.excess)} илүү)
              </span>
              <button
                type="button"
                disabled={add.isPending}
                onClick={() =>
                  add.mutate({
                    params: { path: { steamid } },
                    body: { kpi: s.kpi, target: s.target, baseline: s.baseline, notes: '' },
                  })
                }
                className="rounded-md border border-line px-2 py-0.5 text-xs text-ink hover:border-ink-3"
              >
                Зорилго болгох
              </button>
            </div>
          ))}
        </div>
      )}
      {staff && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <select value={kpi} onChange={(e) => setKpi(e.target.value)} className="rounded-md border border-line bg-surface-2 px-2 py-1 text-ink">
            <option value="">KPI сонгох…</option>
            {kpis.map((k) => (
              <option key={k.kpi} value={k.kpi}>
                {k.label}
                {k.unit === '/24' ? ' (24 раундад)' : ''}
              </option>
            ))}
          </select>
          <input
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder="зорилт"
            inputMode="decimal"
            className="w-24 rounded-md border border-line bg-surface-2 px-2 py-1 text-ink"
          />
          <button
            type="button"
            disabled={!kpi || target === '' || add.isPending}
            onClick={() => add.mutate({ params: { path: { steamid } }, body: { kpi, target: Number(target), notes: '' } })}
            className="rounded-md border border-line bg-raised px-3 py-1 text-ink hover:border-ink-3 disabled:opacity-50"
          >
            Нэмэх
          </button>
          {error && <span className="text-crit">{error}</span>}
        </div>
      )}
    </section>
  )
}

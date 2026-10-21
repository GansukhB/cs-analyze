// Writing a Strat (docs/plans/08 SB-1): its name and kind, who does what in
// each slot, its grenades with their timing, and the calls. Staff only.
import { useState } from 'react'
import type { components } from '../api/schema'

import { KINDS, type StratWrite } from './kinds'

type Role = components['schemas']['StratRole']
type Grenade = components['schemas']['StratGrenade']
const GRENADES: Grenade['type'][] = ['smoke', 'flash', 'he', 'inferno', 'decoy']
const field = 'w-full rounded-md border border-line bg-surface-2 px-2 py-1 text-sm text-ink'

export default function StratForm(props: {
  initial: StratWrite
  teams: { id: number; name: string }[]
  maps: string[]
  busy: boolean
  error?: string
  onSave: (body: StratWrite) => void
}) {
  const [s, setS] = useState<StratWrite>(props.initial)
  const roles: Role[] = [1, 2, 3, 4, 5].map((slot) => s.roles?.find((r) => r.slot === slot) ?? { slot, player: '', role: '', does: '' })
  const setRole = (slot: number, patch: Partial<Role>) =>
    setS({ ...s, roles: roles.map((r) => (r.slot === slot ? { ...r, ...patch } : r)).filter((r) => r.role || r.does || r.player) })
  const grenades = s.grenades ?? []
  const setNade = (i: number, patch: Partial<Grenade>) =>
    setS({ ...s, grenades: grenades.map((g, k) => (k === i ? { ...g, ...patch } : g)) })
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault()
        props.onSave(s)
      }}
    >
      <div className="grid gap-3 sm:grid-cols-4">
        <label className="space-y-1 text-xs text-ink-3 sm:col-span-2">
          Нэр
          <input value={s.name} onChange={(e) => setS({ ...s, name: e.target.value })} maxLength={120} required className={field} />
        </label>
        <label className="space-y-1 text-xs text-ink-3">
          Төрөл
          <select value={s.kind} onChange={(e) => setS({ ...s, kind: e.target.value as StratWrite['kind'] })} className={field}>
            {KINDS.map(([k, l]) => (
              <option key={k} value={k}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-xs text-ink-3">
          Баг
          <select value={s.team_id} onChange={(e) => setS({ ...s, team_id: Number(e.target.value) })} className={field}>
            {props.teams.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-xs text-ink-3">
          Map
          <select value={s.map_name} onChange={(e) => setS({ ...s, map_name: e.target.value })} className={field}>
            {props.maps.map((m) => (
              <option key={m} value={m}>
                {m.replace(/^de_/, '')}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-xs text-ink-3">
          Тал
          <select value={s.side} onChange={(e) => setS({ ...s, side: e.target.value as 'ct' | 't' })} className={field}>
            <option value="t">T</option>
            <option value="ct">CT</option>
          </select>
        </label>
        <label className="space-y-1 text-xs text-ink-3">
          Төлөв
          <select value={s.status} onChange={(e) => setS({ ...s, status: e.target.value as StratWrite['status'] })} className={field}>
            <option value="draft">Ноорог</option>
            <option value="active">Идэвхтэй</option>
            <option value="retired">Хуучирсан</option>
          </select>
        </label>
        <label className="space-y-1 text-xs text-ink-3">
          Хэн уншина
          <select
            value={s.visibility}
            onChange={(e) => setS({ ...s, visibility: e.target.value as StratWrite['visibility'] })}
            className={field}
          >
            <option value="staff">Зөвхөн Staff</option>
            <option value="team">Багийн тоглогчид (идэвхтэй үед)</option>
          </select>
        </label>
      </div>
      <label className="block space-y-1 text-xs text-ink-3">
        Тайлбар
        <textarea value={s.description} onChange={(e) => setS({ ...s, description: e.target.value })} rows={3} className={field} />
      </label>
      <div className="space-y-1">
        <p className="text-xs uppercase tracking-wide text-ink-3">Slot бүрийн үүрэг</p>
        {roles.map((r) => (
          <div key={r.slot} className="grid grid-cols-[2rem_8rem_1fr] gap-2">
            <span className="pt-1 font-mono text-ink-3">{r.slot}</span>
            <input placeholder="үүрэг" value={r.role} onChange={(e) => setRole(r.slot, { role: e.target.value })} className={field} />
            <input placeholder="юу хийх" value={r.does} onChange={(e) => setRole(r.slot, { does: e.target.value })} className={field} />
          </div>
        ))}
      </div>
      <div className="space-y-1">
        <p className="text-xs uppercase tracking-wide text-ink-3">Граната</p>
        {grenades.map((g, i) => (
          <div key={i} className="grid grid-cols-[4rem_7rem_1fr_5rem_1fr_2rem] gap-2">
            <input
              type="number"
              min={1}
              max={5}
              placeholder="slot"
              value={g.slot ?? ''}
              onChange={(e) => setNade(i, { slot: e.target.value ? Number(e.target.value) : null })}
              className={field}
            />
            <select value={g.type} onChange={(e) => setNade(i, { type: e.target.value as Grenade['type'] })} className={field}>
              {GRENADES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <input placeholder="хаана буух (Callout)" value={g.place} onChange={(e) => setNade(i, { place: e.target.value })} className={field} />
            <input
              type="number"
              min={0}
              step={0.5}
              placeholder="с"
              value={g.at ?? ''}
              onChange={(e) => setNade(i, { at: e.target.value ? Number(e.target.value) : null })}
              className={field}
            />
            <input placeholder="тэмдэглэл" value={g.note} onChange={(e) => setNade(i, { note: e.target.value })} className={field} />
            <button type="button" onClick={() => setS({ ...s, grenades: grenades.filter((_x, k) => k !== i) })} className="text-ink-3 hover:text-crit">
              ✕
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={() => setS({ ...s, grenades: [...grenades, { slot: null, type: 'smoke', place: '', at: null, note: '', lineup: null }] })}
          className="text-sm text-ct hover:underline"
        >
          + граната
        </button>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {(['timings', 'variations', 'calls'] as const).map((k) => (
          <label key={k} className="space-y-1 text-xs text-ink-3">
            {{ timings: 'Timing', variations: 'Хувилбарууд', calls: 'Дуудлага' }[k]}
            <textarea value={s[k] ?? ''} onChange={(e) => setS({ ...s, [k]: e.target.value })} rows={3} className={field} />
          </label>
        ))}
      </div>
      <div className="flex items-center gap-3">
        <button type="submit" disabled={props.busy} className="rounded-md bg-ct px-4 py-2 text-sm font-medium text-ground disabled:opacity-50">
          Хадгалах
        </button>
        {props.error && <span className="text-sm text-crit">{props.error}</span>}
      </div>
    </form>
  )
}

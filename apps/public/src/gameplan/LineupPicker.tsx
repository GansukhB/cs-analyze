import { useState } from 'react'
import { $api } from '../api/client'
import type { components } from '../api/schema'

type Candidate = components['schemas']['LineupPlayer']
type Known = { steamid: string; name: string; elsewhere?: string }

const MAX = 5

/**
 * One side's Lineup: who has played for the team, most recent first, with the
 * five from its latest match ticked until the user changes it; anyone else is
 * found by name (a stand-in, a new signing). `value` is null while it is still
 * that default five, so an untouched side stays out of the URL.
 */
export function LineupPicker({
  team,
  label,
  value,
  onChange,
  known = [],
  taken = [],
}: {
  team: { id: number; name: string }
  label: string
  value: string[] | null
  onChange: (next: string[] | null) => void
  /** Players already named elsewhere (the page header), so a picked stranger has a name. */
  known?: Known[]
  /** Picked on the other side: one Player cannot play for both. */
  taken?: string[]
}) {
  const candidates = $api.useQuery('get', '/gameplan/teams/{team_id}/players', {
    params: { path: { team_id: team.id } },
  })
  const [text, setText] = useState('')
  const [extra, setExtra] = useState<Known[]>([])
  const q = text.trim()
  const found = $api.useQuery(
    'get',
    '/gameplan/players',
    { params: { query: { q } } },
    { enabled: q.length >= 2, staleTime: 60_000 },
  )

  const list = candidates.data?.players ?? []
  const defaults = list.filter((p) => p.default).map((p) => p.steamid)
  const picked = value ?? defaults
  const listed = new Set(list.map((p) => p.steamid))
  const names = new Map<string, Known>([...known, ...extra].map((k) => [k.steamid, k]))
  const strangers = picked.filter((id) => !listed.has(id))

  function set(next: string[]) {
    const same = next.length === defaults.length && next.every((id) => defaults.includes(id))
    onChange(same ? null : next)
  }
  function toggle(id: string) {
    if (picked.includes(id)) set(picked.filter((x) => x !== id))
    else if (picked.length < MAX) set([...picked, id])
  }
  function add(p: Candidate) {
    if (!listed.has(p.steamid)) setExtra((e) => [...e, { steamid: p.steamid, name: p.name, elsewhere: p.team }])
    if (!picked.includes(p.steamid) && picked.length < MAX) set([...picked, p.steamid])
    setText('')
  }

  const full = picked.length >= MAX
  return (
    <div className="lu-pick">
      <div className="lu-head">
        <span className="cap">{label}</span>
        <b>{team.name}</b>
        <span className={`lu-count ${picked.length ? '' : 'empty'}`}>{picked.length}/5</span>
        {value !== null && (
          <button type="button" className="lu-reset" onClick={() => onChange(null)}>
            сүүлийн тоглолтын 5
          </button>
        )}
      </div>

      {candidates.isPending && <p className="none">Тоглогчдыг уншиж байна…</p>}
      <ul className="lu-list">
        {strangers.map((id) => (
          <li key={id}>
            <label>
              <input type="checkbox" checked onChange={() => toggle(id)} />
              <span className="lu-name">{names.get(id)?.name ?? id}</span>
              <span className="lu-meta">
                {names.get(id)?.elsewhere ? `шинэ · ${names.get(id)?.elsewhere}` : 'энэ багт тоглоогүй'}
              </span>
            </label>
          </li>
        ))}
        {list.map((p) => {
          const on = picked.includes(p.steamid)
          const blocked = taken.includes(p.steamid)
          return (
            <li key={p.steamid} className={on ? 'on' : undefined}>
              <label>
                <input
                  type="checkbox"
                  checked={on}
                  disabled={blocked || (!on && full)}
                  onChange={() => toggle(p.steamid)}
                />
                <span className="lu-name">{p.name}</span>
                <span className="lu-meta">
                  {p.maps} map{p.last_played ? ` · ${new Date(p.last_played).toLocaleDateString('en-CA')}` : ''}
                  {blocked ? ' · нөгөө талд' : ''}
                </span>
              </label>
            </li>
          )
        })}
      </ul>

      <div className="lu-search">
        <input
          type="search"
          placeholder={full ? '5 тоглогч сонгогдсон — нэгийг хасаад нэмнэ' : 'Өөр тоглогч нэрээр хайх (stand-in, шинэ гэрээ)…'}
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={full}
        />
        {q.length >= 2 && (
          <ul className="lu-found">
            {found.isPending && <li className="none">Хайж байна…</li>}
            {found.data?.players.length === 0 && <li className="none">Олдсонгүй.</li>}
            {found.data?.players
              .filter((p) => !picked.includes(p.steamid) && !taken.includes(p.steamid))
              .map((p) => (
                <li key={p.steamid}>
                  <button type="button" onClick={() => add(p)}>
                    <span className="lu-name">{p.name}</span>
                    <span className="lu-meta">
                      {p.team || 'баггүй'} · {p.maps} map
                    </span>
                  </button>
                </li>
              ))}
          </ul>
        )}
      </div>
    </div>
  )
}

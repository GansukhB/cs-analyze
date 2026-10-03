import { useState } from 'react'
import { useNavigate } from 'react-router'
import { $api } from '../api/client'
import type { components } from '../api/schema'
import '../gameplan/gameplan.css'

type Team = components['schemas']['GameplanTeam']

// Choose the two teams, then go straight to their plan (cstat's gameplan_pick).
// Two comboboxes rather than a grid of every team crossed with every opponent,
// which is n² links and unreadable by the twentieth team.
export default function GameplanPickPage() {
  const navigate = useNavigate()
  const pick = $api.useQuery('get', '/gameplan/teams')
  const [mine, setMine] = useState<Team | null>(null)
  const [theirs, setTheirs] = useState<Team | null>(null)
  const [error, setError] = useState('')

  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!mine || !theirs) return setError('Pick both teams from the list.')
    // The whole plan is the difference between the two sides.
    if (mine.id === theirs.id) return setError('Pick two different teams.')
    navigate(`/gameplan/${mine.id}/vs/${theirs.id}`)
  }

  const teams = pick.data?.teams ?? []
  return (
    <div className="gp-page">
      <h1>Game plan</h1>
      <p className="lede">
        Pick your team and the opponent. Everything on the plan is computed from parsed demos — only teams
        with demos in the database can be picked.
      </p>

      {pick.isPending && <p className="text-ink-3">Уншиж байна…</p>}
      {pick.error && <p className="text-crit">Багуудыг уншиж чадсангүй.</p>}

      {pick.data &&
        (teams.length > 1 ? (
          <form onSubmit={submit} className="mt-6 rounded-xl border border-line bg-surface p-6">
            <div className="vs">
              <TeamCombo label="My team" teams={teams} value={mine} onChange={setMine} autoFocus />
              <div className="sep">VS</div>
              <TeamCombo label="Opponent" teams={teams} value={theirs} onChange={setTheirs} />
            </div>
            {error && <p className="mt-3 text-sm text-crit">{error}</p>}
            <div className="mt-6 flex flex-wrap items-center gap-4">
              <button
                type="submit"
                className="rounded-md bg-ct px-6 py-2.5 font-semibold text-ground hover:brightness-110"
              >
                Build the plan
              </button>
              <span className="text-sm text-ink-3">Read straight from the parsed database — nothing is downloaded.</span>
            </div>
            <div className="mt-4 flex flex-wrap gap-6 font-mono text-xs text-ink-3">
              <span>{teams.length} team(s) with parsed demos</span>
              <span>{pick.data.parsed_maps} map(s) parsed</span>
            </div>
          </form>
        ) : (
          <div className="mt-6 rounded-xl border border-line bg-surface p-6">
            <h3>Nothing to compare yet</h3>
            <p className="text-ink-2">
              A plan needs two teams with parsed maps; the database has {teams.length}. Run an analysis on more
              matches first — the plan is read entirely from demos, not from HLTV.
            </p>
          </div>
        ))}
    </div>
  )
}

function TeamCombo({
  label,
  teams,
  value,
  onChange,
  autoFocus,
}: {
  label: string
  teams: Team[]
  value: Team | null
  onChange: (t: Team | null) => void
  autoFocus?: boolean
}) {
  const [text, setText] = useState(value?.name ?? '')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const query = text.trim().toLowerCase()
  const shown = teams.filter((t) => !query || t.name.toLowerCase().includes(query))

  function choose(t: Team | undefined) {
    if (!t) return
    setText(t.name)
    onChange(t)
    setOpen(false)
  }

  function onKey(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      if (!open) return setOpen(true)
      if (!shown.length) return
      const step = e.key === 'ArrowDown' ? 1 : -1
      setActive((active + step + shown.length) % shown.length)
    } else if (e.key === 'Enter') {
      // Only while a suggestion is highlighted; otherwise Enter submits the form.
      if (open && shown[active]) {
        e.preventDefault()
        choose(shown[active])
      }
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className="combo">
      <label>{label}</label>
      <input
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-autocomplete="list"
        autoComplete="off"
        placeholder="Start typing a team…"
        autoFocus={autoFocus}
        value={text}
        onChange={(e) => {
          setText(e.target.value)
          onChange(null)
          setActive(0)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onKeyDown={onKey}
      />
      {open && (
        <ul className="combo-list" role="listbox" onMouseDown={(e) => e.preventDefault()}>
          {shown.length ? (
            shown.map((t, i) => (
              <li
                key={t.id}
                role="option"
                aria-selected={i === active}
                onMouseEnter={() => setActive(i)}
                onClick={() => choose(t)}
              >
                <span>
                  <Highlight name={t.name} query={query} />
                </span>
                <span className="n">
                  {t.maps} {t.maps === 1 ? 'map' : 'maps'}
                </span>
              </li>
            ))
          ) : (
            <li className="none">No team with parsed demos matches that.</li>
          )}
        </ul>
      )}
    </div>
  )
}

// The name split around what was typed, so the match is visible in the row.
function Highlight({ name, query }: { name: string; query: string }) {
  const at = query ? name.toLowerCase().indexOf(query) : -1
  if (at < 0) return <>{name}</>
  return (
    <>
      {name.slice(0, at)}
      <b>{name.slice(at, at + query.length)}</b>
      {name.slice(at + query.length)}
    </>
  )
}

// The Fixture's Lineups and window bars (TM-3), on v1's Game Plan and v2's: both
// ride on the page URL (gameplan/lineup.ts), so applying one is a new URL.
import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { $api } from '../api/client'
import type { components } from '../api/schema'
import { lineupSearch, readLineups } from './lineup'
import { LineupPicker } from './LineupPicker'

type Header = components['schemas']['GameplanHeader']

// TM-3: the window the Teams' Maps are read in, on the URL with the Lineups. The
// Pool stays whole; the Playbook's patch chip sets the same day.
const DAY_MS = 86_400_000
const daysAgo = (n: number) => new Date(Date.now() - n * DAY_MS).toISOString().slice(0, 10)

export function WindowBar() {
  const navigate = useNavigate()
  const location = useLocation()
  const lineups = readLineups(new URLSearchParams(location.search))
  const latest = $api.useQuery('get', '/patches', {}, { staleTime: Infinity }).data?.patches[0]
  const go = (since?: string) => navigate(`${location.pathname}${lineupSearch({ ...lineups, since })}`)
  const choices: [string | undefined, string][] = [
    [undefined, 'Бүх цаг'],
    [daysAgo(180), 'Сүүлийн 180 хоног'],
    [daysAgo(90), 'Сүүлийн 90 хоног'],
  ]
  if (latest) choices.push([latest.date, `${latest.name}-аас хойш`])
  const shown = new Set(choices.map(([d]) => d))
  return (
    <div className="filters" role="group" aria-label="Хугацаа">
      <span className="cap">Хугацаа</span>
      {choices.map(([day, label]) => (
        <button key={label} type="button" className={`chip ${lineups.since === day ? 'on' : ''}`} onClick={() => go(day)}>
          {label}
        </button>
      ))}
      {lineups.since && !shown.has(lineups.since) && (
        <button type="button" className="chip on" onClick={() => go(undefined)}>
          {lineups.since}-аас хойш ✕
        </button>
      )}
    </div>
  )
}

// Both Lineups the plan was built with, and an editor for them: applying it is
// a new URL, so the plan recomputes (or comes from cache) for that pair.
export function LineupBar({ header }: { header: Header }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [editing, setEditing] = useState(false)
  const { mine, theirs } = header.lineups
  const [myFive, setMyFive] = useState<string[] | null>(null)
  const [theirFive, setTheirFive] = useState<string[] | null>(null)

  function open() {
    setMyFive(mine.picked ? mine.players.map((p) => p.steamid) : null)
    setTheirFive(theirs.picked ? theirs.players.map((p) => p.steamid) : null)
    setEditing(true)
  }
  function apply() {
    setEditing(false)
    const since = readLineups(new URLSearchParams(location.search)).since
    navigate(`${location.pathname}${lineupSearch({ mine: myFive ?? [], theirs: theirFive ?? [], since })}`)
  }

  const sides = [
    ['mine', header.my_team.name, mine],
    ['theirs', header.opponent.name, theirs],
  ] as const
  return (
    <div className="lu-bar">
      {sides.map(([scope, name, side]) => (
        <div key={scope} className="lu-side">
          <span className={`tag ${scope}`}>{name}</span>
          {side.players.map((p) => (
            <span key={p.steamid} className="lu-member" title={p.elsewhere ? `Тоо нь ${p.elsewhere}-аас` : undefined}>
              {p.name}
              {p.elsewhere && <small> · шинэ</small>}
            </span>
          ))}
          {!side.picked && <small className="lu-auto">сүүлийн тоглолтын 5</small>}
        </div>
      ))}
      {editing ? (
        <div className="lu-sides">
          <LineupPicker
            team={header.my_team}
            label="Манай Lineup"
            value={myFive}
            onChange={setMyFive}
            known={mine.players}
            taken={theirFive ?? []}
          />
          <LineupPicker
            team={header.opponent}
            label="Тэдний Lineup"
            value={theirFive}
            onChange={setTheirFive}
            known={theirs.players}
            taken={myFive ?? []}
          />
          <div className="lu-actions">
            <button
              type="button"
              className="lu-apply"
              disabled={myFive?.length === 0 || theirFive?.length === 0}
              onClick={apply}
            >
              Lineup-аар дахин тооцоолох
            </button>
            <button type="button" className="lu-reset" onClick={() => setEditing(false)}>
              болих
            </button>
          </div>
        </div>
      ) : (
        <button type="button" className="lu-reset" onClick={open}>
          Lineup засах
        </button>
      )}
    </div>
  )
}

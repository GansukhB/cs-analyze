import { useCallback, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'
import { $api } from '../api/client'
import type { components } from '../api/schema'
import type { ReplayBridge } from '../replay/player'
import Replay from '../replay/Replay'
import RoundTimeline from '../replay/RoundTimeline'
import { applyFilters, type Filters, isActive, useFilters } from './filters'
import FilterBar from './FilterBar'
import { NotesProvider, RoundNotes } from './Notes'
import { TEAM_DOT } from './format'
import PlayersTable, { PlayerFocus } from './PlayersTable'
import RoundPanel from './RoundPanel'
import { TeamSummaryCard } from './Summary'

type Review = components['schemas']['Review']

export type Goto = (round: number, t: number, sid: string | null, play?: boolean) => void

/**
 * One Match Map's tab: the filters, both Teams' Summaries of the Map, the
 * Replay with the Round beside it, and the Players. The Replay and the Review
 * talk through the bridge: the Review's links call the Replay's `goto`, and the
 * Replay says which Round it is showing.
 */
export default function MapReview(props: { matchId: number; mapNumber: number; staff?: boolean }) {
  return (
    <NotesProvider matchId={props.matchId} mapNumber={props.mapNumber} staff={!!props.staff}>
      <MapReviewBody matchId={props.matchId} mapNumber={props.mapNumber} />
    </NotesProvider>
  )
}

function MapReviewBody({ matchId, mapNumber }: { matchId: number; mapNumber: number }) {
  const path = { params: { path: { match_id: matchId, map_number: mapNumber } } }
  const detail = $api.useQuery('get', '/matches/{match_id}/maps/{map_number}', path)
  const reviewQuery = $api.useQuery('get', '/matches/{match_id}/maps/{map_number}/review', path, {
    staleTime: 5 * 60_000,
    retry: false,
    enabled: !!detail.data?.parsed,
  })
  const startRound = Number(useSearchParams()[0].get('round')) || undefined
  const [round, setRound] = useState<number | null>(startRound ?? null)
  const bridge = useMemo<ReplayBridge>(() => ({ onRound: setRound }), [])
  const replayBox = useRef<HTMLElement>(null)
  const goto = useCallback<Goto>(
    (n, t, sid, play = true) => {
      if (bridge.goto) bridge.goto(n, t, sid, play)
      else setRound(n)
      const box = replayBox.current?.getBoundingClientRect()
      // Bring the Replay into view only when its top is off screen or far down.
      if (play && box && (box.top < 0 || box.top > window.innerHeight * 0.4)) {
        replayBox.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    },
    [bridge],
  )
  const [filters, set, clear] = useFilters()
  const review = reviewQuery.data ?? null
  const view = useMemo(() => (review ? applyFilters(review, filters) : null), [review, filters])
  // A filter that leaves out the Round on the canvas moves it to the first Round it keeps.
  const change = useCallback(
    (patch: Partial<Filters>) => {
      set(patch)
      if (!review) return
      const next = applyFilters(review, { ...filters, ...patch })
      const shown = round ?? review.rounds[0]?.n
      if (shown !== undefined && next.matching.has(shown)) return
      const first = review.rounds.find((r) => next.matching.has(r.n))
      if (first) goto(first.n, 0, null, false)
    },
    [set, review, filters, round, goto],
  )

  if (detail.error) return <p className="text-crit">Энэ тоглолтод {mapNumber}-р мап байхгүй.</p>
  if (!detail.data) return <p className="text-ink-3">Replay бэлтгэж байна…</p>
  const { label, scene, rounds, scoreboard, parsed } = detail.data
  // The scoreboard lists the Match Map's team1 first, the order the rounds' `mine` follows.
  const team1 = { name: scoreboard[0]?.team.name ?? 'Team 1', score: scoreboard[0]?.score ?? null }
  const team2 = { name: scoreboard[1]?.team.name ?? 'Team 2', score: scoreboard[1]?.score ?? null }
  const dim = review && view && isActive(filters) ? new Set(review.rounds.map((r) => r.n).filter((n) => !view.matching.has(n))) : undefined
  const onPlayer = (sid: string | null) => change({ player: sid, team: null })

  return (
    <div className="space-y-6">
      {review && view && <FilterBar review={review} filters={filters} set={change} clear={clear} matching={view.matching.size} />}
      {review && filters.player && <Focus review={review} sid={filters.player} filters={filters} set={change} goto={goto} />}

      {parsed && (
        <section className="space-y-2">
          <h2 className="font-medium text-ink">
            Map-ийн тойм — {label}
            {filters.side && <span className="ml-2 text-sm text-ink-3">({filters.side.toUpperCase()} тал)</span>}
          </h2>
          {reviewQuery.isError ? (
            <p className="rounded-xl border border-line bg-surface p-4 text-sm text-ink-3">
              Энэ map-ийн дүн шинжилгээг гаргаж чадсангүй (tick дата байхгүй байж магадгүй).
            </p>
          ) : review ? (
            <MapSummary review={review} team={filters.team} side={filters.side} onGoto={goto} />
          ) : (
            <p className="text-sm text-ink-3">Тойм бэлтгэж байна…</p>
          )}
          {review?.missing && (
            <p className="rounded-lg border border-warn/40 bg-surface px-3 py-2 text-sm text-ink-2">
              <span className="mr-1 text-warn">!</span>
              {review.missing}
            </p>
          )}
        </section>
      )}

      <div className={`grid items-start gap-4 ${review ? 'min-[1440px]:grid-cols-[minmax(0,1fr)_400px]' : ''}`}>
        <section className="min-w-0 scroll-mt-4 space-y-2" ref={replayBox}>
          {scene ? (
            <Replay
              key={`${matchId}-${mapNumber}`}
              matchId={matchId}
              mapNumber={mapNumber}
              scene={scene}
              rounds={rounds}
              startRound={startRound}
              team1={team1}
              team2={team2}
              bridge={bridge}
              dim={dim}
            />
          ) : (
            <>
              <p className="rounded-xl border border-line bg-surface p-6 text-ink-2">
                {parsed
                  ? `${label} is parsed, but has no stored tick data to replay — run a scout that includes this match to parse it again.`
                  : `${label} has not been parsed, so there is nothing to replay.`}
              </p>
              {rounds.length > 0 && <RoundTimeline rounds={rounds} team1={team1} team2={team2} dim={dim} />}
            </>
          )}
        </section>
        {review && view && (
          <div className="min-w-0 min-[1440px]:sticky min-[1440px]:top-4 min-[1440px]:max-h-[calc(100vh-2rem)] min-[1440px]:overflow-y-auto min-[1440px]:pr-1">
            <RoundPanel
              review={review}
              round={review.rounds.find((r) => r.n === round) ?? review.rounds[0] ?? null}
              matching={view.matching}
              filters={filters}
              findings={view.findings}
              names={Object.fromEntries(review.players.map((p) => [p.sid, p.name]))}
              teamIndex={new Map(review.teams.map((t, i) => [t.id, i]))}
              onGoto={goto}
              onPlayer={(sid) => onPlayer(filters.player === sid ? null : sid)}
            />
            <div className="mt-3">
              <RoundNotes
                round={round ?? review.rounds[0]?.n ?? null}
                bridge={bridge}
                names={Object.fromEntries(review.players.map((p) => [p.sid, p.name]))}
                onGoto={goto}
              />
            </div>
          </div>
        )}
      </div>

      {scoreboard.length > 0 && (
        <section className="space-y-2">
          <h2 className="font-medium text-ink">Тоглогчид — {label}</h2>
          <PlayersTable scoreboard={scoreboard} review={review} team={filters.team} player={filters.player} onPlayer={onPlayer} />
        </section>
      )}
    </div>
  )
}

/** Both Teams' Summaries of the Map side by side, or the one the filter picks. */
function MapSummary(props: { review: Review; team: number | null; side: 'ct' | 't' | null; onGoto: Goto }) {
  const { review, team, side, onGoto } = props
  const teams = review.summary[side ?? 'all'].filter((s) => team === null || s.team_id === team)
  const index = (id: number | null) => Math.max(0, review.teams.findIndex((t) => t.id === id))
  const name = (id: number | null) => review.teams.find((t) => t.id === id)?.name ?? '?'
  return (
    <div className={`grid gap-4 ${teams.length > 1 ? 'lg:grid-cols-2' : ''}`}>
      {teams.map((s) => (
        <TeamSummaryCard
          key={s.team_id ?? 'x'}
          name={name(s.team_id)}
          teamIndex={index(s.team_id)}
          score={`${s.won}–${s.rounds - s.won}`}
          numbers={s.numbers}
          focus={s.focus}
          strengths={s.strengths}
          problems={s.problems}
          onRef={(r) => onGoto(r.round, r.t, r.sid)}
        />
      ))}
    </div>
  )
}

function Focus(props: {
  review: Review
  sid: string
  filters: Filters
  set: (patch: Partial<Filters>) => void
  goto: Goto
}) {
  const { review, sid, filters, set, goto } = props
  const player = review.players.find((p) => p.sid === sid)
  if (!player) return null
  const i = review.teams.findIndex((t) => t.id === player.team_id)
  return (
    <PlayerFocus
      player={player}
      dot={TEAM_DOT[Math.max(0, i)]}
      involved={filters.involved}
      setInvolved={(v) => set({ involved: v })}
      onGoto={goto}
      onClose={() => set({ player: null, involved: false })}
    />
  )
}

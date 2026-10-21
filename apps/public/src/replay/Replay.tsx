import { useEffect, useMemo, useRef } from 'react'
import { fetchClient } from '../api/client'
import type { components } from '../api/schema'
import { mountReplay, type ReplayBridge, type RoundData } from './player'
import RoundTimeline, { type TimelineTeam } from './RoundTimeline'
import './replay.css'

type Scene = components['schemas']['Scene']
type RoundStripRow = components['schemas']['RoundStripRow']

/**
 * The replay's markup, cstat's ids and classes kept as they were, so the ported
 * player (player.ts) drives it unchanged. Remounted per map: the key on the
 * caller's side makes a new map a fresh player.
 */
export default function Replay(props: {
  matchId: number
  mapNumber: number
  scene: Scene
  rounds: RoundStripRow[]
  /** The round to open on (a Playbook's evidence link); the first one otherwise. */
  startRound?: number
  /** The Match Map's two teams, in the rounds' `mine` order, for the round strip. */
  team1: TimelineTeam
  team2: TimelineTeam
  /** Filled with the replay's `goto`, and told which round is on the canvas. */
  bridge?: ReplayBridge
  /** Rounds the Review's filters leave out, faint on the round strip. */
  dim?: Set<number>
}) {
  const { matchId, mapNumber, scene, rounds, startRound, team1, team2, bridge, dim } = props
  const root = useRef<HTMLDivElement>(null)
  // The map's score as each round began: every round before it, by its winner.
  const before = useMemo(() => {
    const won: Record<string, number> = {}
    const out = new Map<number, Record<string, number>>()
    for (const r of rounds) {
      out.set(r.number, { ...won })
      if (r.winner) won[r.winner] = (won[r.winner] || 0) + 1
    }
    return out
  }, [rounds])

  useEffect(() => {
    if (!root.current) return
    return mountReplay(root.current, scene, async (number) => {
      const { data, error } = await fetchClient.GET(
        '/matches/{match_id}/maps/{map_number}/rounds/{number}',
        // Always revalidated (ETag): a round's URL outlives its content.
        { params: { path: { match_id: matchId, map_number: mapNumber, number } }, cache: 'no-cache' },
      )
      if (error || !data) throw new Error(`round ${number} is not available`)
      return data as unknown as RoundData
    }, startRound, (n) => before.get(n) || {}, bridge)
  }, [matchId, mapNumber, scene, startRound, before, bridge])

  return (
    <div ref={root} className="rp">
      <div className="replay">
        <div className="rp-score">
          <span className="rp-score-side ct">
            <span className="nm" id="rp-team-ct">CT</span>
            <b className="rp-score-n" id="rp-ct">0</b>
          </span>
          <span className="rp-score-mid">
            <span className="clock" id="rp-clock">0:00</span>
            <span className="cap" id="rp-round-no">round</span>
          </span>
          <span className="rp-score-side t">
            <span className="nm" id="rp-team-t">T</span>
            <b className="rp-score-n" id="rp-t">0</b>
          </span>
        </div>

        <div className="rp-arena">
          <div className="rp-roster ct" id="rp-roster-ct" />
          <div className="rp-main">
            <div className="stage">
              <canvas id="rp-canvas" width={scene.plate.width} height={scene.plate.height} />
              <div className="loading" id="rp-loading">loading round…</div>
              <div className="feed" id="rp-feed" aria-label="Round log" />
            </div>

            <div className="hud">
              <span className="transport" role="group" aria-label="Playback">
                <button type="button" className="tp" id="rp-prev" aria-label="Previous round" title="Previous round ([)">
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 5h2v14H6zM20 5v14L9 12z" /></svg>
                </button>
                <button type="button" className="tp play" id="rp-play" aria-label="Play" title="Play (space)">
                  <svg className="i-play" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4.5v15L19.5 12z" /></svg>
                  <svg className="i-pause" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 5h4v14H6zM14 5h4v14h-4z" /></svg>
                </button>
                <button type="button" className="tp" id="rp-next" aria-label="Next round" title="Next round (])">
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16 5h2v14h-2zM4 5v14l11-7z" /></svg>
                </button>
              </span>
              <span className="time" id="rp-time">0:00 / 0:00</span>
              <span className="alive" id="rp-note" />
              <span className="sp" id="rp-speeds" />
            </div>

            <div className="track">
              <div className="marks" id="rp-marks" />
              <input type="range" id="rp-seek" min={0} max={1000} defaultValue={0} step={1} aria-label="Round timeline" />
            </div>

            <div className="toggles">
              <label><input type="checkbox" id="rp-names" defaultChecked /> names</label>
              <label><input type="checkbox" id="rp-trails" defaultChecked /> trails</label>
              <label><input type="checkbox" id="rp-util" defaultChecked /> utility</label>
              <label><input type="checkbox" id="rp-shots" defaultChecked /> shots</label>
              <label><input type="checkbox" id="rp-dmg" /> damage</label>
              <label><input type="checkbox" id="rp-vision" /> vision</label>
              <label title="Бусад сонсож болох хөлийн чимээ"><input type="checkbox" id="rp-steps" /> footsteps</label>
              <label><input type="checkbox" id="rp-labels" /> callouts</label>
              {scene.levels.length > 0 && (
                <span className="floors" id="rp-floors" role="group" aria-label="Floor">
                  <b>floor</b>
                  <button type="button" data-floor="auto" className="on">auto</button>
                  {scene.levels.map((level, i) => (
                    <button key={level.key} type="button" data-floor={i}>{level.key}</button>
                  ))}
                </span>
              )}
              <span>
                space = play · ← → = 5s · [ ] = round{scene.levels.length > 0 && ' · v = floor'} · wheel = zoom ·
                shift+click = follow · double-click = reset
              </span>
            </div>
          </div>
          <div className="rp-strip">
            <RoundTimeline rounds={rounds} team1={team1} team2={team2} replay dim={dim} />
          </div>
          <div className="rp-roster t" id="rp-roster-t" />
        </div>
      </div>
    </div>
  )
}

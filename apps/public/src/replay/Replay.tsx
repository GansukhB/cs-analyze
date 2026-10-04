import { useEffect, useMemo, useRef } from 'react'
import { fetchClient } from '../api/client'
import type { components } from '../api/schema'
import { mountReplay, type RoundData } from './player'
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
}) {
  const { matchId, mapNumber, scene, rounds, startRound } = props
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
    }, startRound, (n) => before.get(n) || {})
  }, [matchId, mapNumber, scene, startRound, before])

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
            </div>

            <div className="hud">
              <button type="button" className="play" id="rp-play">Play</button>
              <span className="sp" id="rp-speeds" />
              <span className="alive" id="rp-note" />
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
              <span>space = play · ← → = 5s · [ ] = round{scene.levels.length > 0 && ' · v = floor'}</span>
            </div>

            <div className="rounds" id="rp-rounds">
              {rounds.map((r) => (
                <span key={r.number} style={{ display: 'contents' }}>
                  {r.half_break && <div className="brk" />}
                  <button
                    type="button"
                    className={`r ${r.winner_side}`}
                    data-round={r.number}
                    title={`${r.score} — ${r.winner || '?'} by ${r.reason}${r.planted ? ` (plant ${r.site})` : ''}`}
                  >
                    {r.number}
                  </button>
                </span>
              ))}
            </div>
          </div>
          <div className="rp-roster t" id="rp-roster-t" />
        </div>

        <div className="feed">
          <h4>
            Round log
            <label className="fopt"><input type="checkbox" id="rp-dmg" defaultChecked /> damage</label>
          </h4>
          <div className="rhead" id="rp-round-head" />
          <div id="rp-feed"><p className="help">Pick a round.</p></div>
        </div>
      </div>
    </div>
  )
}

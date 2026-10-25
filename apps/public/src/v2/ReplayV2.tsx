// The Replay in the v2 layout (the DEMOLAB design): the same ids and player
// (replay/player.ts) as v1's Replay.tsx, laid out as the design's screen 02 —
// the score and clock on top, layer buttons over the map, both fives beside it,
// the rounds under it. player.ts finds its elements by id inside this root, so
// keep every id it reads (see Replay.tsx) when moving things around.
import { useEffect, useMemo, useRef, type ReactNode } from 'react'
import { fetchClient } from '../api/client'
import type { components } from '../api/schema'
import { mountReplay, type ReplayBridge, type RoundData } from '../replay/player'
import RoundTimeline, { type TimelineTeam } from '../replay/RoundTimeline'
import '../replay/replay.css'

type Scene = components['schemas']['Scene']
type RoundStripRow = components['schemas']['RoundStripRow']

// The design's layers, each the v1 checkbox player.ts reads.
const LAYERS: [string, string, boolean][] = [
  ['rp-trails', 'Траектор', true],
  ['rp-util', 'Utility', true],
  ['rp-vision', 'Харах чиглэл', false],
  ['rp-names', 'Нэр', true],
  ['rp-shots', 'Буудлага', true],
  ['rp-dmg', 'Damage', false],
  ['rp-steps', 'Хөлийн чимээ', false],
  ['rp-labels', 'Callout', false],
]

export default function ReplayV2(props: {
  matchId: number
  mapNumber: number
  scene: Scene
  rounds: RoundStripRow[]
  startRound?: number
  team1: TimelineTeam
  team2: TimelineTeam
  bridge: ReplayBridge
  /** The page's heading, buttons and badges, beside the clock. */
  head: ReactNode
  actions: ReactNode
  /** Under both fives: the Round's notes and drawing. */
  aside: ReactNode
}) {
  const { matchId, mapNumber, scene, rounds, startRound, team1, team2, bridge } = props
  const root = useRef<HTMLDivElement>(null)
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
    return mountReplay(
      root.current,
      scene,
      async (number) => {
        const { data, error } = await fetchClient.GET('/matches/{match_id}/maps/{map_number}/rounds/{number}', {
          params: { path: { match_id: matchId, map_number: mapNumber, number } },
          cache: 'no-cache',
        })
        if (error || !data) throw new Error(`round ${number} is not available`)
        return data as unknown as RoundData
      },
      startRound,
      (n) => before.get(n) || {},
      bridge,
    )
  }, [matchId, mapNumber, scene, startRound, before, bridge])

  return (
    <div ref={root} className="rp v2rp flex flex-col gap-4">
      <section className="flex flex-wrap items-center justify-between gap-3.5">
        <div className="flex flex-wrap items-center gap-4.5">
          <div className="flex flex-col gap-0.5">
            {props.head}
            <h1 className="cond m-0 text-[26px] font-bold">
              <span id="rp-team-ct" className="text-ct">CT</span> <b id="rp-ct" className="num text-ct">0</b>
              <span className="text-ink-3"> : </span>
              <b id="rp-t" className="num text-t">0</b> <span id="rp-team-t" className="text-t">T</span>
            </h1>
          </div>
          <span id="rp-round-no" className="cond rounded bg-chip px-2.5 py-1.5 text-sm font-semibold">
            round
          </span>
          {props.actions}
        </div>
        <div className="flex items-baseline gap-2.5">
          <span className="lbl">Үлдсэн хугацаа</span>
          <span id="rp-clock" className="num text-[30px] font-semibold">
            0:00
          </span>
        </div>
      </section>

      <section className="flex flex-wrap items-start gap-4">
        <div className="flex min-w-0 flex-[999_1_640px] flex-col rounded-lg border border-line bg-surface-2">
          <div className="flex flex-wrap justify-between gap-2.5 border-b border-line px-3 py-2.5">
            <div role="group" aria-label="Давхаргууд" className="v2-layers flex flex-wrap gap-1.5">
              {LAYERS.map(([id, label, on]) => (
                <label key={id}>
                  <input type="checkbox" id={id} defaultChecked={on} className="sr-only" />
                  <span>{label}</span>
                </label>
              ))}
            </div>
            {scene.levels.length > 0 && (
              <span className="floors flex items-center gap-1 text-[13px]" id="rp-floors" role="group" aria-label="Давхар">
                <b className="lbl">давхар</b>
                <button type="button" data-floor="auto" className="on">
                  auto
                </button>
                {scene.levels.map((level, i) => (
                  <button key={level.key} type="button" data-floor={i}>
                    {level.key}
                  </button>
                ))}
              </span>
            )}
          </div>
          <div className="p-3">
            <div className="stage">
              <canvas id="rp-canvas" width={scene.plate.width} height={scene.plate.height} />
              <div className="loading" id="rp-loading">
                раунд уншиж байна…
              </div>
              <div className="feed" id="rp-feed" aria-label="Kill feed" />
            </div>
            <div className="hud">
              <span className="transport" role="group" aria-label="Тоглуулах">
                <button type="button" className="tp" id="rp-prev" aria-label="Өмнөх раунд" title="Өмнөх раунд ([)">
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M6 5h2v14H6zM20 5v14L9 12z" />
                  </svg>
                </button>
                <button type="button" className="tp play" id="rp-play" aria-label="Тоглуулах" title="Тоглуулах (space)">
                  <svg className="i-play" viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M7 4.5v15L19.5 12z" />
                  </svg>
                  <svg className="i-pause" viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M6 5h4v14H6zM14 5h4v14h-4z" />
                  </svg>
                </button>
                <button type="button" className="tp" id="rp-next" aria-label="Дараагийн раунд" title="Дараагийн раунд (])">
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M16 5h2v14h-2zM4 5v14l11-7z" />
                  </svg>
                </button>
              </span>
              <span className="time" id="rp-time">
                0:00 / 0:00
              </span>
              <span className="alive" id="rp-note" />
              <span className="sp" id="rp-speeds" />
            </div>
            <div className="track">
              <div className="marks" id="rp-marks" />
              <input type="range" id="rp-seek" min={0} max={1000} defaultValue={0} step={1} aria-label="Раундын цаг" />
            </div>
            <p className="m-0 mt-1 text-xs text-ink-3">
              space = тоглуулах · ← → = 5с · [ ] = раунд · дугуй = томруулах · shift+click = дагах · давхар дарах = буцаах
            </p>
          </div>
        </div>
        <aside className="flex min-w-0 flex-[1_1_380px] flex-col gap-3">
          <div className="rp-roster t" id="rp-roster-t" />
          <div className="rp-roster ct" id="rp-roster-ct" />
          {props.aside}
        </aside>
      </section>

      <section className="flex flex-col gap-2 rounded-lg border border-line bg-surface px-4 py-3.5">
        <span className="lbl">Раундууд · дарж шилжинэ</span>
        <RoundTimeline rounds={rounds} team1={team1} team2={team2} replay />
      </section>
    </div>
  )
}

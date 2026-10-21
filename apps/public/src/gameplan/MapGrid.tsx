// A filtered map grid -- map x team x player x side (x floor) -- drawn one
// selection at a time. Ported from cstat's _mapgrid.html. The index key is the
// string app/services/heatmap_groups.key() builds; the two must stay identical.
import { keepPreviousData, useQueries } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { fetchClient } from '../api/client'
import { useElapsed } from './useElapsed'
import { drawHeatmap, type HeatData } from './heatmap'
import { mountScene } from './scene'
import type { GridIndex, GridWords, Shot, TableSpec, Track } from './types'

type Kind = 'heatmap' | 'movement'

interface Selection {
  map: string
  team: string
  player: string
  side: string
  level: string
  // VIZ-9, heatmaps only: when in the Round, on what buy, against the Pool.
  phase: string
  buy: string
  compare: boolean
}

const PHASES: [string, string][] = [
  ['all', 'Бүх хугацаа'],
  ['0-15', '0–15с'],
  ['15-30', '15–30с'],
  ['30-60', '30–60с'],
  ['60+', '60с+'],
  ['post', 'Plant-ын дараа'],
]
const BUYS: [string, string][] = [
  ['all', 'Бүх buy'],
  ['full', 'Full'],
  ['light', 'Eco/force/pistol'],
]

export default function MapGrid({
  index,
  words,
  mine,
  theirs,
  kind,
}: {
  index: GridIndex
  words: GridWords
  mine: number
  theirs: number
  kind: Kind
}) {
  const [sel, setSel] = useState<Selection>(() => {
    const team = String(index.teams[0]?.id ?? '')
    return {
      map: firstMap(index, team) ?? index.maps[0] ?? '',
      team,
      player: 'all',
      side: index.sides[0]?.key ?? 'all',
      level: 'all',
      phase: 'all',
      buy: 'all',
      compare: false,
    }
  })
  const played = playedMaps(index, sel.team)
  const levels = index.levels[sel.map] ?? []
  const players = index.teams.find((t) => String(t.id) === sel.team)?.players ?? []

  function change(patch: Partial<Selection>) {
    setSel((cur) => {
      const next = { ...cur, ...patch }
      if (patch.team !== undefined) {
        // The player picker belongs to the team above it, and the map list is the
        // union of both teams' maps: move off whatever this team cannot answer.
        const roster = index.teams.find((t) => String(t.id) === next.team)?.players ?? []
        if (next.player !== 'all' && !roster.some((p) => String(p.id) === next.player)) next.player = 'all'
        if (!playedMaps(index, next.team).has(next.map)) next.map = firstMap(index, next.team) ?? next.map
      }
      // A floor the new map does not have falls back to both.
      const keys = index.levels[next.map] ?? []
      if (next.level !== 'all' && !keys.includes(next.level)) next.level = 'all'
      return next
    })
  }

  const shots = useQueries({
    queries: index.kinds.map((k) => {
      const n = index.available[[sel.map, sel.team, sel.player, sel.side, k.key].join('|')] ?? 0
      return {
        // Each cell is fetched at most once; re-selecting a view is free.
        queryKey: ['gameplan-grid', kind, mine, theirs, sel.map, sel.team, sel.player, sel.side, k.key, sel.level, sel.phase, sel.buy, sel.compare],
        queryFn: () => drawCell(kind, mine, theirs, sel, k.key),
        enabled: n > 0,
        staleTime: Infinity,
        placeholderData: keepPreviousData,
        meta: { n },
      }
    }),
  })
  // Only the first kind's response fills the tables, so two shots answering at
  // different times cannot fight over one region.
  const tables: TableSpec[] = (shots[0]?.data?.tables as TableSpec[] | undefined) ?? []

  return (
    <>
      <div className="filters mapgrid">
        <Row label={words.map}>
          {index.maps.map((m) => (
            <Chip key={m} on={m === sel.map} off={!played.has(m)} mono onClick={() => change({ map: m })}>
              {m}
            </Chip>
          ))}
        </Row>
        <Row label={words.team}>
          {index.teams.map((t) => (
            <Chip key={t.id} on={String(t.id) === sel.team} onClick={() => change({ team: String(t.id) })}>
              {t.name}
            </Chip>
          ))}
        </Row>
        <Row label={words.player}>
          <Chip on={sel.player === 'all'} onClick={() => change({ player: 'all' })}>
            {words.all_players}
          </Chip>
          {players.map((p) => (
            <Chip key={p.id} on={String(p.id) === sel.player} onClick={() => change({ player: String(p.id) })}>
              {p.name}
            </Chip>
          ))}
        </Row>
        <Row label={words.side}>
          {index.sides.map((s) => (
            <Chip key={s.key} on={s.key === sel.side} mono onClick={() => change({ side: s.key })}>
              {s.label}
            </Chip>
          ))}
        </Row>
        {levels.length > 0 && (
          <Row label={words.floor}>
            {words.floors.map((f) => {
              const ok = f.key === 'all' || levels.includes(f.key)
              return (
                <Chip key={f.key} on={f.key === sel.level} off={!ok} mono onClick={() => ok && change({ level: f.key })}>
                  {f.label}
                </Chip>
              )
            })}
          </Row>
        )}
        {kind === 'heatmap' && (
          <>
            <Row label="Хугацаа">
              {PHASES.map(([key, label]) => (
                <Chip key={key} on={sel.phase === key} mono onClick={() => change({ phase: key })}>
                  {label}
                </Chip>
              ))}
            </Row>
            <Row label="Buy">
              {BUYS.map(([key, label]) => (
                <Chip key={key} on={sel.buy === key} mono onClick={() => change({ buy: key })}>
                  {label}
                </Chip>
              ))}
              <Chip on={sel.compare} onClick={() => change({ compare: !sel.compare })}>
                Pool-той харьцуулах
              </Chip>
            </Row>
          </>
        )}
      </div>
      {kind === 'heatmap' && sel.compare && (
        <p className="lede">Улаан: бусад багаас олон, цэнхэр: цөөн (тухайн map, тал, хугацаа, buy дээр).</p>
      )}

      <div className="shots">
        {index.kinds.map((k, i) => {
          const q = shots[i]
          const n = index.available[[sel.map, sel.team, sel.player, sel.side, k.key].join('|')] ?? 0
          return (
            <ShotCard
              key={k.key}
              kind={kind}
              label={k.label}
              n={n}
              data={n ? q.data : undefined}
              fetching={n > 0 && q.isFetching}
              failed={n > 0 && q.isError}
              words={words}
              loadTracks={() => fetchTracks(mine, theirs, sel)}
            />
          )
        })}
      </div>

      {tables.length > 0 && (
        <div className="gx-tables">
          {tables.map((spec) => (
            <div key={spec.title}>
              <h3>{spec.title}</h3>
              {spec.note && <p className="note">{spec.note}</p>}
              <div className="tw">
                <table className="setup">
                  <thead>
                    <tr>
                      {spec.columns.map((c) => (
                        <th key={c.label} className={c.num ? 'num' : undefined}>
                          {c.label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {spec.rows.map((cells, r) => (
                      <tr key={r}>
                        {cells.map((cell, c) => (
                          <td key={c} className={[spec.columns[c]?.num ? 'num' : '', cell.tone ?? ''].join(' ').trim() || undefined}>
                            {cell.v}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  )
}

function ShotCard({
  label,
  kind,
  n,
  data,
  fetching,
  failed,
  words,
  loadTracks,
}: {
  label: string
  kind: Kind
  n: number
  data: Shot | undefined
  fetching: boolean
  failed: boolean
  words: GridWords
  loadTracks: () => Promise<Track[]>
}) {
  const frame = useRef<HTMLDivElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const sceneHost = useRef<HTMLDivElement>(null)
  const below = useRef<HTMLDivElement>(null)
  const usable = data && !data.empty ? data : null
  const scene = kind === 'movement' && usable ? usable.scene ?? null : null
  const heat = kind === 'heatmap' && usable?.points?.length ? usable : null
  // Drawing a heatmap is the page's own work (the overview composite, then the
  // density); until it lands the previous picture stays under the loader.
  const [drawn, setDrawn] = useState<Shot | null>(null)
  const drawing = !!heat && drawn !== heat
  const elapsed = useElapsed(fetching || drawing)

  useEffect(() => {
    if (!scene || !sceneHost.current || !below.current) return
    return mountScene(sceneHost.current, below.current, scene, words, loadTracks)
    // A new response object is a new selection; loadTracks closes over it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene, words])

  useEffect(() => {
    if (!heat || !canvas.current || !frame.current) return
    let live = true
    const width = Math.min(frame.current.clientWidth || 640, 900)
    // A frame later, so the loader paints before the density is computed.
    const id = requestAnimationFrame(() => {
      drawHeatmap(canvas.current!, heat as HeatData, width)
        .catch((err) => console.error('heatmap: could not draw', err))
        .finally(() => live && setDrawn(heat))
    })
    return () => {
      live = false
      cancelAnimationFrame(id)
    }
  }, [heat])

  const nothing = !n || (data && (data.empty || (kind === 'heatmap' ? !heat : !scene)))
  const note = failed ? words.failed : nothing ? words.nothing : !data ? words.pick : null
  const busy = fetching || drawing

  return (
    <div className="shot">
      <div className="hm-frame" ref={frame}>
        <div ref={sceneHost} style={{ width: '100%', display: scene && !nothing ? 'block' : 'none' }} />
        <canvas
          ref={canvas}
          className={busy ? 'heat loading' : 'heat'}
          style={{ display: kind === 'heatmap' && (heat || drawn) && !nothing ? 'block' : 'none' }}
          role="img"
          aria-label={usable?.title ?? label}
        />
        {note && !busy && <div className="hm-note">{note}</div>}
        {busy && (
          <div className="hm-loader">
            <span className="hm-spinner" aria-hidden="true" />
            <span>
              {fetching ? words.drawing.replace('%n', String(n)) : 'Зурж байна…'}
            </span>
            <small>{elapsed.toFixed(1)}с</small>
          </div>
        )}
      </div>
      <div ref={below} />
      <div className="cap">
        <b>{usable && !nothing && usable.title ? usable.title : label}</b>
        <span className="sub">
          {usable && !nothing && usable.subtitle ? usable.subtitle : ''}
          {usable?.renderer === 'density' ? ` · ${words.no_background}` : ''}
        </span>
      </div>
    </div>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="frow">
      <span className="flabel">{label}</span>
      {children}
    </div>
  )
}

function Chip({
  on,
  off,
  mono,
  onClick,
  children,
}: {
  on: boolean
  off?: boolean
  mono?: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      aria-pressed={on}
      disabled={off}
      className={['chip', mono ? 'mono' : '', on ? 'on' : '', off ? 'off' : ''].join(' ')}
      onClick={onClick}
    >
      {children}
    </button>
  )
}

function playedMaps(index: GridIndex, team: string): Set<string> {
  const out = new Set<string>()
  for (const k of Object.keys(index.available)) {
    const parts = k.split('|')
    if (parts[1] === team) out.add(parts[0])
  }
  return out
}

function firstMap(index: GridIndex, team: string): string | undefined {
  const played = playedMaps(index, team)
  return index.maps.find((m) => played.has(m))
}

async function drawCell(kind: Kind, mine: number, theirs: number, sel: Selection, cell: string): Promise<Shot> {
  const path = { mine, theirs }
  const query = { team: Number(sel.team), map: sel.map, player: sel.player, side: sel.side, level: sel.level, kind: cell }
  const res =
    kind === 'heatmap'
      ? await fetchClient.GET('/gameplan/{mine}/vs/{theirs}/heatmap', {
          params: { path, query: { ...query, phase: sel.phase, buy: sel.buy, compare: sel.compare } },
        })
      : await fetchClient.GET('/gameplan/{mine}/vs/{theirs}/movement', { params: { path, query } })
  if (res.error || !res.data) throw new Error('draw failed')
  return res.data as Shot
}

async function fetchTracks(mine: number, theirs: number, sel: Selection): Promise<Track[]> {
  const res = await fetchClient.GET('/gameplan/{mine}/vs/{theirs}/tracks', {
    params: {
      path: { mine, theirs },
      query: { team: Number(sel.team), map: sel.map, player: sel.player, side: sel.side, level: sel.level },
    },
  })
  return ((res.data as { tracks?: Track[] } | undefined)?.tracks ?? []) as Track[]
}

// VIZ-10: where a Team's utility lands on a Map and Side, from where and when,
// and the lineups it repeats, drawn over the overview in the browser.
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { $api } from '../api/client'
import { drawHeatmap, type HeatData, type HeatPlate } from './heatmap'

// One hue per grenade, apart from both Sides' colours.
const TYPES: [string, string, string][] = [
  ['smoke', 'Smoke', '#c8d2dc'],
  ['inferno', 'Molotov', '#e0854a'],
  ['flash', 'Flash', '#e8e0a0'],
  ['he', 'HE', '#cf6a56'],
]
const colour = (t: string) => TYPES.find(([k]) => k === t)?.[2] ?? '#a2acb6'
const clock = (t: number | null) => (t == null ? '—' : `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`)

interface Lineup {
  type: string
  throws: number
  maps: number
  from: [number, number]
  land: [number, number]
  from_place: string
  to_place: string
  t: number | null
  setpos: string
  refs: { match: number; map: number; round: number }[]
}

export default function UtilityMap({ mine, theirs, map }: { mine: number; theirs: number; map: string }) {
  const [side, setSide] = useState<'t' | 'ct'>('t')
  const [whose, setWhose] = useState<'theirs' | 'mine'>('theirs')
  const [types, setTypes] = useState<string[]>(TYPES.map(([k]) => k))
  const q = $api.useQuery('get', '/gameplan/{mine}/vs/{theirs}/utility/{map_name}', {
    params: { path: { mine, theirs, map_name: map }, query: { side, whose } },
  })
  const canvas = useRef<HTMLCanvasElement>(null)
  const data = q.data as
    | { team: string; throws: { type: string; land: [number, number]; from: [number, number] | null; t: number | null }[]; lineups: Lineup[]; plate: HeatPlate | null; labels: HeatData['labels'] }
    | undefined
  useEffect(() => {
    if (!data || !canvas.current) return
    const shown = data.lineups.filter((l) => types.includes(l.type))
    void drawHeatmap(
      canvas.current,
      {
        cmap: 'inferno',
        points: [],
        heat: false,
        labels: data.labels,
        level: '',
        plate: data.plate,
        marks: data.throws.filter((t) => types.includes(t.type)).map((t) => ({ at: t.land, colour: colour(t.type), r: 0.7 })),
        lines: shown.map((l) => ({ from: l.from, to: l.land, colour: colour(l.type), width: Math.min(3, 1 + l.throws / 6) })),
      },
      Math.min(620, window.innerWidth - 32),
    )
  }, [data, types])
  const flip = (k: string) => setTypes(types.includes(k) ? types.filter((x) => x !== k) : [...types, k])
  return (
    <div className="space-y-2">
      <div className="filters">
        {(['theirs', 'mine'] as const).map((w) => (
          <button key={w} type="button" className={`chip ${whose === w ? 'on' : ''}`} onClick={() => setWhose(w)}>
            {w === 'theirs' ? 'Тэдний' : 'Манай'}
          </button>
        ))}
        {(['t', 'ct'] as const).map((s) => (
          <button key={s} type="button" className={`chip ${side === s ? 'on' : ''}`} onClick={() => setSide(s)}>
            {s.toUpperCase()}
          </button>
        ))}
        {TYPES.map(([k, label, c]) => (
          <button key={k} type="button" className={`chip ${types.includes(k) ? 'on' : ''}`} onClick={() => flip(k)}>
            <span style={{ color: c }}>●</span> {label}
          </button>
        ))}
      </div>
      {!data ? (
        <p className="none">{q.isError ? 'Utility-г уншиж чадсангүй.' : 'Уншиж байна…'}</p>
      ) : data.throws.length === 0 ? (
        <p className="none">Энэ map, талд шидсэн utility алга.</p>
      ) : (
        <>
          <canvas ref={canvas} style={{ maxWidth: '100%', borderRadius: 8 }} />
          <p className="cap">
            {data.team}: {data.throws.length} шидэлт; шугам нь давтагдсан lineup (шидсэн газраас буусан газар хүртэл), цэг нь
            буусан газар.
          </p>
          <ul className="pb-rows">
            {data.lineups
              .filter((l) => types.includes(l.type))
              .map((l, i) => (
                <li key={i}>
                  <span style={{ color: colour(l.type) }}>●</span> {TYPES.find(([k]) => k === l.type)?.[1]}: {l.from_place || '?'} →{' '}
                  {l.to_place || '?'} · {l.throws} удаа · дундаж {clock(l.t)}{' '}
                  <button type="button" className="chip" title={l.setpos} onClick={() => void navigator.clipboard?.writeText(l.setpos)}>
                    setpos
                  </button>{' '}
                  <Link className="mono" to={`/ghost?r=${l.refs.map((r) => `${r.match}.${r.map}.${r.round}`).join(',')}&side=${side}`}>
                    ⧉
                  </Link>
                </li>
              ))}
          </ul>
        </>
      )}
    </div>
  )
}

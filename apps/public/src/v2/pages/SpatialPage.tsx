// v2 screen 05, positions: the my team beside an opponent on one Map and Side,
// in four views — where they stand by the Round's clock, the routes they walk,
// who trades whom, and the lurker. Drawn over the radar by the Game Plan's
// heatmap painter (gameplan/heatmap.ts).
import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'
import { $api } from '../../api/client'
import type { components } from '../../api/schema'
import { drawHeatmap, type HeatData } from '../../gameplan/heatmap'
import { LoadError } from '../../ui/LoadError'
import { PageSkeleton } from '../../ui/Skeleton'
import { CRIT, CT, GOOD, HEX, MUTED, T, THEM, WARN } from '../format'
import { TeamPicker } from '../TeamPicker'
import { useTeam } from '../team'
import { Box, Empty, PageHead, Panel, SideToggle, Swatch, Toggle } from '../ui'

type Spatial = components['schemas']['Spatial']
type SideTeam = components['schemas']['SpatialTeam']
type Mode = 'heat' | 'move' | 'trade' | 'lurk'

const MODES: [Mode, string, string][] = [
  ['heat', 'Heatmap', 'Хаана цаг өнгөрүүлдэг вэ — бүсийн эзэмшил раундын цагаар'],
  ['move', 'Хөдөлгөөн', 'Ямар замаар, хэр олон, ямар үр дүнтэй явдаг вэ'],
  ['trade', 'Trade', 'Хэн хэнийгээ хамгаалдаг, хаана ганцаараа үхдэг вэ'],
  ['lurk', 'Lurk', 'Ганцаараа тоглогч багаасаа хэр хол, хэр үр дүнтэй вэ'],
]

export default function SpatialPage() {
  const team = useTeam()
  const [params, setParams] = useSearchParams()
  const next = $api.useQuery('get', '/v2/upcoming', { params: { query: { team_id: team.id } } })
  const opponent = Number(params.get('opponent')) || next.data?.upcoming[0]?.opponent.id || undefined
  const mode = (MODES.find(([k]) => k === params.get('mode'))?.[0] ?? 'heat') as Mode
  const side = (params.get('side') === 'ct' ? 'ct' : 't') as 't' | 'ct'
  const map = params.get('map') ?? undefined
  const [win, setWin] = useState(4)
  const q = $api.useQuery(
    'get',
    '/v2/teams/{team_id}/spatial',
    { params: { path: { team_id: team.id }, query: { opponent, map, side, mode } } },
    { enabled: next.isFetched },
  )
  const set = (key: string, value: string | null) =>
    setParams(
      (p) => {
        if (value === null) p.delete(key)
        else p.set(key, value)
        return p
      },
      { replace: true },
    )
  if (q.error) return <LoadError error={q.error} what="Байршил" retry={() => void q.refetch()} />
  if (!q.data) return <PageSkeleton />
  const d = q.data
  const label = d.maps.find((m) => m.map === d.map)?.label ?? '—'
  const panels = [d.us && { t: d.us, mine: true }, d.them && { t: d.them, mine: false }].filter(Boolean) as { t: SideTeam; mine: boolean }[]
  const sideColor = side === 't' ? T : CT
  return (
    <>
      <PageHead
        label="Байршлын шинжилгээ · Бид vs Өрсөлдөгч"
        title={`${label} · ${d.us?.team.name ?? team.name}${d.opponent ? ` vs ${d.opponent.name}` : ''}`}
        sub={panels.map((p) => `${p.mine ? 'Бид' : 'Тэд'}: ${p.t.rounds} раунд`).join(' · ') + ' · Replay-ийн 8 Hz байрлалаас'}
        actions={
          <>
            <SideToggle value={side} onChange={(s) => set('side', s === 't' ? null : s)} />
            <div className="w-56">
              <TeamPicker
                label="Өрсөлдөгч"
                value={d.opponent ?? null}
                onChange={(t) => t && set('opponent', String(t.id))}
                exclude={[team.id]}
                parsedOnly
              />
            </div>
          </>
        }
      />
      <nav aria-label="Газрын зураг" className="flex flex-wrap gap-1.5">
        {d.maps.map((m) => (
          <button
            key={m.map}
            type="button"
            aria-pressed={m.map === d.map}
            onClick={() => set('map', m.map)}
            className={`h-10 rounded-md border px-3.5 text-sm ${m.map === d.map ? 'border-accent bg-accent-soft text-accent' : 'border-line-strong text-ink-2'}`}
          >
            {m.label} <span className="num text-xs text-ink-3">{m.n}</span>
          </button>
        ))}
      </nav>
      <section role="tablist" aria-label="Харах горим" className="grid grid-cols-[repeat(auto-fit,minmax(min(240px,100%),1fr))] gap-2">
        {MODES.map(([k, l, why]) => (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={k === mode}
            onClick={() => set('mode', k === 'heat' ? null : k)}
            className={`flex min-h-[76px] flex-col gap-1 rounded-lg border p-3.5 text-left ${k === mode ? 'border-accent bg-[#1A160F]' : 'border-line bg-surface'}`}
          >
            <span className="cond text-lg font-bold" style={{ color: k === mode ? 'var(--accent)' : 'var(--ink)' }}>
              {l}
            </span>
            <span className="text-[13px] leading-snug text-ink-3">{why}</span>
          </button>
        ))}
      </section>
      {mode === 'heat' && (
        <section className="flex flex-wrap items-center gap-2.5">
          <span className="lbl">Раундын цаг</span>
          <Toggle
            small
            label="Раундын цаг"
            value={String(win)}
            onChange={(k) => setWin(Number(k))}
            options={[...d.windows.map((w, i) => [String(i), w[1] > 900 ? `${w[0]}с+` : `${w[0]}–${w[1]}с`] as const), ['4', 'Бүгд'] as const]}
          />
          <span className="text-[13px] text-ink-3">Нэг цагийн цонхонд хоёр багийг ижил өнгөний хуваариар харьцуулна</span>
        </section>
      )}
      {mode === 'lurk' && side === 'ct' ? (
        <Panel>
          <Empty>Lurk нь T талын дүр: T талыг сонгоно уу.</Empty>
        </Panel>
      ) : (
        <section className="grid grid-cols-[repeat(auto-fit,minmax(min(560px,100%),1fr))] gap-4">
          {panels.map((p) => (
            <TeamPanel key={p.t.team.id} d={d} t={p.t} mine={p.mine} mode={mode} win={win} sideColor={sideColor} />
          ))}
          {!d.them && (
            <Panel>
              <Empty>Харьцуулах өрсөлдөгчөө дээрээс сонгоно уу.</Empty>
            </Panel>
          )}
        </section>
      )}
      {mode === 'heat' && <Zones d={d} win={win} sideColor={sideColor} />}
      {mode === 'move' && <Routes d={d} sideColor={sideColor} />}
      {mode === 'trade' && <Matrices d={d} />}
      {mode === 'lurk' && side === 't' && <LurkChart d={d} sideColor={sideColor} />}
    </>
  )
}

function points(t: SideTeam, win: number): [number, number][] {
  const all = t.heat?.points ?? []
  const chosen = win >= all.length ? all.flat() : all[win] ?? []
  return chosen as [number, number][]
}

function stats(t: SideTeam, mode: Mode, win: number): [string, string][] {
  if (mode === 'heat') {
    const zones = t.heat?.zones ?? []
    const key = (z: (typeof zones)[number]) => (win >= 4 ? z.all : z.shares[win])
    const top = [...zones].sort((a, b) => key(b) - key(a))[0]
    return [
      ['Хамгийн их бүс', top?.place ?? '—'],
      ['Түүний хувь', top ? `${Math.round(key(top))}%` : '—'],
      ['Раунд', String(t.rounds)],
    ]
  }
  if (mode === 'move') {
    const r = t.routes?.[0]
    return [
      ['Түгээмэл зам', r ? r.label.split(' → ').slice(-1)[0] : '—'],
      ['Түүний хувь', r ? `${Math.round(r.share)}%` : '—'],
      ['Замын тоо', String(t.routes?.length ?? 0)],
    ]
  }
  if (mode === 'trade') {
    const ps = t.trade?.players ?? []
    const deaths = ps.reduce((a, p) => a + p.deaths, 0)
    const traded = ps.reduce((a, p) => a + p.traded, 0)
    return [
      ['Trade хийгдсэн үхэл', deaths ? `${Math.round((100 * traded) / deaths)}%` : '—'],
      ['Ганцаараа үхсэн', String(deaths - traded)],
      ['Үхэл', String(deaths)],
    ]
  }
  const l = t.lurk
  return [
    ['Lurker', l ? l.name : '—'],
    ['30с-д ганцаараа', l ? `${l.share}%` : '—'],
    ['Trade-гүй үхэл', l ? String(l.untraded) : '—'],
  ]
}

function TeamPanel(props: { d: Spatial; t: SideTeam; mine: boolean; mode: Mode; win: number; sideColor: string }) {
  const { d, t, mine, mode, win, sideColor } = props
  const canvas = useRef<HTMLCanvasElement>(null)
  const box = useRef<HTMLDivElement>(null)
  const color = mine ? sideColor : '#8FA3B5'
  const paint = mine ? (d.side === 't' ? HEX.t : HEX.ct) : HEX.them
  useEffect(() => {
    if (!canvas.current || mode === 'lurk') return
    const data: HeatData = { cmap: 'inferno', points: [], heat: false, labels: d.labels, level: '', plate: d.plate ? { ...d.plate, lower: d.plate.lower ?? null, extent: d.plate.extent as [number, number, number, number] } : null }
    if (mode === 'heat') {
      data.points = points(t, win)
      data.heat = data.points.length >= 50
      data.dots = !data.heat
    } else if (mode === 'move') {
      data.lines = (t.routes ?? []).flatMap((r) =>
        r.path.slice(1).map((p, i) => ({ from: r.path[i] as [number, number], to: p as [number, number], colour: paint, width: Math.max(1.5, Math.min(6, r.share / 6)) })),
      )
      data.marks = (t.routes ?? []).map((r) => ({ at: r.path.at(-1) as [number, number], colour: paint, r: 1.2 }))
    } else if (mode === 'trade') {
      data.lines = (t.trade?.segments ?? []).map(([a, b]) => ({ from: a as [number, number], to: b as [number, number], colour: HEX.good, width: 1 }))
      data.marks = (t.trade?.lone ?? []).map((p) => ({ at: p as [number, number], colour: HEX.crit, r: 0.8 }))
    }
    if (data.points.length === 0 && !data.lines?.length && !data.marks?.length && !data.plate) return
    void drawHeatmap(canvas.current, data, Math.min(640, box.current?.clientWidth ?? 560))
  }, [d, t, mode, win, paint])
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2.5">
        <div className="flex items-center gap-2.5">
          <span className="cond rounded px-2 py-0.5 text-xs font-bold text-[#0A0D10]" style={{ background: mine ? sideColor : '#8FA3B5' }}>
            {mine ? 'БИД' : 'ТЭД'}
          </span>
          <span className="cond text-xl font-bold">{t.team.name}</span>
        </div>
        <span className="num text-[13px] text-ink-3">
          {d.side.toUpperCase()} · {t.rounds} раунд
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {stats(t, mode, win).map(([k, v]) => (
          <Box key={k} className="!p-2.5">
            <span className="lbl !text-[11px]">{k}</span>
            <span className="num truncate text-base font-semibold">{v}</span>
          </Box>
        ))}
      </div>
      <div ref={box} className="w-full">
        {mode === 'lurk' ? (
          t.lurk ? (
            <LurkLine l={t.lurk} color={color} />
          ) : (
            <Empty>6+ T раунд тоглосон тоглогч алга.</Empty>
          )
        ) : t.rounds === 0 ? (
          <Empty>Энэ Map, талд раунд алга.</Empty>
        ) : (
          <canvas ref={canvas} className="w-full rounded-md" />
        )}
      </div>
      <div className="flex flex-wrap gap-3.5 text-xs text-ink-3">
        {mode === 'heat' && <span>Өнгө = байрласан нягтрал (2 секунд тутам)</span>}
        {mode === 'move' && <Swatch color={color} line>Зам · зузаан = давтамж</Swatch>}
        {mode === 'trade' && (
          <>
            <Swatch color={GOOD} line>Үхсэн газар → trade хийсэн газар</Swatch>
            <Swatch color={CRIT}>Trade-гүй үхэл</Swatch>
          </>
        )}
      </div>
    </div>
  )
}

function LurkLine({ l, color }: { l: NonNullable<SideTeam['lurk']>; color: string }) {
  return (
    <div className="flex flex-col gap-2">
      <span className="text-sm">
        <b>{l.name}</b> {l.rule ? '' : '(lurk-ийн босгонд хүрээгүй) '}— {l.played} T раундын {l.share}%-д 30 секундэд хамгийн ойр багийн гишүүнээсээ 1400u-аас хол
      </span>
      <Curve series={[[l.curve, color], [l.team_curve, MUTED]]} />
    </div>
  )
}

function Curve({ series }: { series: [(number | null)[], string][] }) {
  const max = Math.max(1500, ...series.flatMap(([v]) => v.filter((x): x is number => x != null)))
  const path = (v: (number | null)[]) =>
    v
      .map((x, i) => (x == null ? null : `${(i * 600) / (v.length - 1)} ${200 - (x / max) * 190}`))
      .filter(Boolean)
      .map((p, i) => `${i ? 'L' : 'M'}${p}`)
      .join(' ')
  return (
    <>
      <svg viewBox="0 0 600 200" width="100%" height="200" preserveAspectRatio="none" role="img" aria-label="Хамгийн ойр багийн гишүүнээс зай, раундын цагаар">
        <path d="M0 50 H600 M0 100 H600 M0 150 H600" stroke="var(--line)" />
        <path d={`M0 ${200 - (1400 / max) * 190} H600`} stroke={WARN} strokeDasharray="5 4" />
        {series.map(([v, c], i) => (
          <path key={i} d={path(v)} fill="none" stroke={c} strokeWidth={3} />
        ))}
      </svg>
      <div className="num flex justify-between text-xs text-ink-3">
        <span>0с</span>
        <span>30с</span>
        <span>60с</span>
        <span>90с</span>
        <span>120с</span>
      </div>
      <span className="text-xs text-ink-3">Тасархай = 1400u (lurk-ийн босго) · саарал = багийн бусад</span>
    </>
  )
}

function Zones({ d, win, sideColor }: { d: Spatial; win: number; sideColor: string }) {
  const us = d.us?.heat?.zones ?? []
  const them = d.them?.heat?.zones ?? []
  const key = (z?: { shares: number[]; all: number }) => (z ? (win >= 4 ? z.all : z.shares[win]) : 0)
  const places = [...new Set([...us, ...them].map((z) => z.place))]
  const rows = places
    .map((p) => ({ p, u: key(us.find((z) => z.place === p)), t: key(them.find((z) => z.place === p)) }))
    .sort((a, b) => b.u + b.t - (a.u + a.t))
    .slice(0, 12)
  const max = Math.max(1, ...rows.flatMap((r) => [r.u, r.t]))
  return (
    <Panel
      title="Бүсийн эзэмшил"
      sub="Тухайн цагийн цонхонд тоглогчдын байрлалын хэдэн хувь нь энэ бүсэд (Callout) байсан"
      right={
        <div className="flex gap-3.5 text-xs text-ink-3">
          <Swatch color={sideColor}>Бид</Swatch>
          <Swatch color={THEM}>Тэд</Swatch>
        </div>
      }
    >
      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(300px,100%),1fr))] gap-x-7 gap-y-2">
        {rows.map((r) => {
          const diff = Math.round(r.u - r.t)
          return (
            <div key={r.p} className="grid grid-cols-[110px_minmax(0,1fr)_44px] items-center gap-2.5">
              <span className="truncate text-sm">{r.p}</span>
              <div className="flex flex-col gap-[3px]">
                <div className="h-[7px] rounded bg-line">
                  <div className="h-[7px] rounded" style={{ width: `${(100 * r.u) / max}%`, background: sideColor }} />
                </div>
                <div className="h-[7px] rounded bg-line">
                  <div className="h-[7px] rounded" style={{ width: `${(100 * r.t) / max}%`, background: THEM }} />
                </div>
              </div>
              <span className="num text-right text-xs" style={{ color: diff > 3 ? GOOD : diff < -3 ? CRIT : MUTED }}>
                {d.them ? `${diff > 0 ? '+' : ''}${diff}` : `${Math.round(r.u)}%`}
              </span>
            </div>
          )
        })}
      </div>
    </Panel>
  )
}

function Routes({ d, sideColor }: { d: Spatial; sideColor: string }) {
  const rows = [d.us && { t: d.us, c: sideColor, who: 'Бид' }, d.them && { t: d.them, c: THEM, who: 'Тэд' }].filter(Boolean) as { t: SideTeam; c: string; who: string }[]
  return (
    <Panel title="Замын үр дүн" sub="Тоглогчдын явсан зам (Callout-аар), таван тоглогчоор нийлүүлсэн">
      <div className="overflow-x-auto">
        <table className="grid-table">
          <thead>
            <tr>
              <th>Баг</th>
              <th>Зам</th>
              <th>Давтамж</th>
              <th>Раундын хожил</th>
              <th>Алалт–үхэл</th>
            </tr>
          </thead>
          <tbody>
            {rows.flatMap(({ t, c, who }) =>
              (t.routes ?? []).map((r) => (
                <tr key={`${who}-${r.label}`}>
                  <td className="font-semibold" style={{ color: c }}>
                    {who}
                  </td>
                  <td className="max-w-[420px] truncate">{r.label}</td>
                  <td>
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-24 rounded bg-line">
                        <div className="h-2 rounded" style={{ width: `${r.share}%`, background: c }} />
                      </div>
                      <span className="num text-[13px]">{Math.round(r.share)}%</span>
                    </div>
                  </td>
                  <td className="num" style={{ color: r.win == null ? MUTED : r.win >= 55 ? GOOD : r.win >= 45 ? WARN : CRIT }}>
                    {r.win == null ? '—' : `${r.win}%`}
                  </td>
                  <td className="num">
                    {r.kills}–{r.deaths}
                  </td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}

function Matrices({ d }: { d: Spatial }) {
  const teams = [d.us, d.them].filter(Boolean) as SideTeam[]
  return (
    <section className="grid grid-cols-[repeat(auto-fit,minmax(min(460px,100%),1fr))] gap-4">
      {teams.map((t) => {
        const tr = t.trade
        if (!tr) return null
        const max = Math.max(1, ...tr.matrix.flat())
        return (
          <Panel key={t.team.id} title={`Trade хос · ${t.team.name}`} sub="Мөр = үхсэн тоглогч · багана = түүнийг 5 секунд дотор trade хийсэн">
            <div className="overflow-x-auto">
              <div className="grid gap-[3px]" style={{ gridTemplateColumns: `90px repeat(${tr.traders.length}, minmax(44px, 1fr)) 64px`, minWidth: 90 + tr.traders.length * 47 + 64 }}>
                <span />
                {tr.traders.map((n) => (
                  <span key={n} className="cond truncate text-center text-xs text-ink-3" title={n}>
                    {n}
                  </span>
                ))}
                <span className="lbl text-center !text-[11px]">trade %</span>
                {tr.players.map((p, i) => (
                  <Row key={p.name} name={p.name} cells={tr.matrix[i]} max={max} pct={p.pct} />
                ))}
              </div>
            </div>
          </Panel>
        )
      })}
    </section>
  )
}

function Row({ name, cells, max, pct }: { name: string; cells: number[]; max: number; pct: number | null }) {
  return (
    <>
      <span className="cond self-center truncate text-[13px]">{name}</span>
      {cells.map((v, j) => (
        <div key={j} className="num grid h-10 place-items-center rounded-[3px] text-[13px]" style={{ background: v ? `rgba(95, 211, 155, ${0.12 + (0.6 * v) / max})` : 'var(--surface-2)', color: v ? 'var(--ink)' : 'var(--ink-3)' }}>
          {v || '·'}
        </div>
      ))}
      <div className="num grid h-10 place-items-center text-[13px]" style={{ color: pct == null ? MUTED : pct >= 25 ? GOOD : pct >= 15 ? WARN : CRIT }}>
        {pct == null ? '—' : `${pct}%`}
      </div>
    </>
  )
}

function LurkChart({ d, sideColor }: { d: Spatial; sideColor: string }) {
  const rows: [string, (l: NonNullable<SideTeam['lurk']>) => string][] = [
    ['Lurk хийсэн раунд', (l) => String(l.rounds)],
    ['Тэр раундын хожил', (l) => (l.rounds ? `${Math.round((100 * l.won) / l.rounds)}%` : '—')],
    ['Алалт / үхэл', (l) => `${l.kills} / ${l.deaths}`],
    ['Trade-гүй үхэл', (l) => String(l.untraded)],
    ['30с-д ганцаараа', (l) => `${l.share}% (${l.played} раунд)`],
  ]
  const us = d.us?.lurk
  const them = d.them?.lurk
  if (!us && !them) return null
  return (
    <section className="flex flex-wrap gap-4">
      <Panel title="Багаас хэр хол вэ · раундын цагаар" className="flex-[999_1_600px]">
        <Curve series={[...(us ? [[us.curve, sideColor] as [(number | null)[], string]] : []), ...(them ? [[them.curve, '#8FA3B5'] as [(number | null)[], string]] : [])]} />
        <div className="flex gap-3.5 text-xs text-ink-3">
          {us && <Swatch color={sideColor} line>{us.name} (бид)</Swatch>}
          {them && <Swatch color="#8FA3B5" line>{them.name} (тэд)</Swatch>}
        </div>
      </Panel>
      <Panel title="Lurk-ийн үр дүн" className="flex-[1_1_380px]">
        <div className="grid grid-cols-[minmax(0,1fr)_90px_90px] gap-2 pb-1.5">
          <span />
          <span className="lbl text-right">{us?.name ?? '—'}</span>
          <span className="lbl text-right">{them?.name ?? '—'}</span>
        </div>
        {rows.map(([k, f]) => (
          <div key={k} className="grid grid-cols-[minmax(0,1fr)_90px_90px] gap-2 border-t border-line py-2.5">
            <span className="text-sm">{k}</span>
            <span className="num text-right font-semibold">{us ? f(us) : '—'}</span>
            <span className="num text-right text-ink-2">{them ? f(them) : '—'}</span>
          </div>
        ))}
      </Panel>
    </section>
  )
}

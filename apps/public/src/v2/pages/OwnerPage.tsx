// v2 screen 10, the management summary: one sentence and the form index, the
// period's KPIs against the one before, six months of results beside practice
// hours, the record by the opponent's tier, each Player's share and steadiness,
// the Team goals, and the risks and openings. Prints as the monthly report.
import { useSearchParams } from 'react-router'
import { $api } from '../../api/client'
import type { components } from '../../api/schema'
import { LoadError } from '../../ui/LoadError'
import { PageSkeleton } from '../../ui/Skeleton'
import { CRIT, GOOD, MUTED, WARN, signed, sparkPath, tone } from '../format'
import { useTeam } from '../team'
import { Bar, Button, Empty, Kpi, PageHead, Panel, Swatch, Tag, Toggle } from '../ui'

type Owner = components['schemas']['Owner']

const PERIODS = [
  ['m', 'Сар'],
  ['q', 'Улирал'],
  ['y', 'Жил'],
] as const
const PALETTE = ['#5EB0F2', '#F0A63A', '#C5CED6', '#8FA3B5', '#6B7F92', '#4F6475']
const WITHIN: Record<string, string> = { m: 'Сүүлийн 30 хоногт', q: 'Сүүлийн 3 сард', y: 'Сүүлийн жилд' }
const MONTH = ['1-р сар', '2-р сар', '3-р сар', '4-р сар', '5-р сар', '6-р сар', '7-р сар', '8-р сар', '9-р сар', '10-р сар', '11-р сар', '12-р сар']

export default function OwnerPage() {
  const team = useTeam()
  const [params, setParams] = useSearchParams()
  const period = (PERIODS.find(([k]) => k === params.get('period'))?.[0] ?? 'q') as 'm' | 'q' | 'y'
  const q = $api.useQuery('get', '/v2/teams/{team_id}/owner', { params: { path: { team_id: team.id }, query: { period } } })
  if (q.error) return <LoadError error={q.error} what="Удирдлагын хураангуй" retry={() => void q.refetch()} />
  if (!q.data) return <PageSkeleton />
  const d = q.data
  const label = PERIODS.find(([k]) => k === period)?.[1] ?? ''
  return (
    <>
      <PageHead
        label="Багийн эзэд · менежмент"
        title="Удирдлагын хураангуй"
        sub={`${d.team.name} · ${label}: ${d.since}-аас хойш, өмнөх ижил хугацаатай харьцуулсан`}
        actions={
          <>
            <Toggle label="Хугацаа" options={PERIODS} value={period} onChange={(p) => setParams(p === 'q' ? {} : { period: p }, { replace: true })} />
            <Button primary onClick={() => window.print()}>
              Тайлан (PDF)
            </Button>
          </>
        }
      />
      <Headline d={d} within={WITHIN[period]} />
      <Kpis d={d} />
      <section className="flex flex-wrap gap-4">
        <Months d={d} />
        <Tiers d={d} />
      </section>
      <section className="flex flex-wrap gap-4">
        <Players d={d} />
        <div className="flex min-w-0 flex-[1_1_340px] flex-col gap-4">
          <Goals d={d} />
          <Risks d={d} />
        </div>
      </section>
    </>
  )
}

function Headline({ d, within }: { d: Owner; within: string }) {
  const s = d.summary
  const up = s.now != null && s.prev != null ? s.now - s.prev : null
  const f = d.form_index
  const angle = Math.PI * (1 - (f ?? 0) / 100)
  const end = [90 + 75 * Math.cos(angle), 100 - 75 * Math.sin(angle)]
  const fc = tone(f, 66, 40)
  return (
    <section className="flex flex-wrap items-center gap-7 rounded-lg border border-line bg-surface p-7">
      <div className="flex min-w-0 flex-[999_1_560px] flex-col gap-3">
        <span className="lbl">Нэг өгүүлбэрээр</span>
        <p className="cond m-0 text-[28px] leading-tight font-semibold">
          {s.now == null ? (
            `${within} албан тоглолтын Map алга.`
          ) : (
            <>
              {within} {s.maps} Map-ийн хожил{' '}
              {s.prev != null && (
                <>
                  <span className="num" style={{ color: tone(s.prev, 60, 50) }}>
                    {Math.round(s.prev)}%
                  </span>{' '}
                  <span className="text-lg text-ink-3">(өмнө {s.prev_maps} Map)</span> →{' '}
                </>
              )}
              <span className="num" style={{ color: tone(s.now, 60, 50) }}>
                {Math.round(s.now)}%
              </span>
              {up != null && (up >= 0 ? ' болж өссөн.' : ' болж буурсан.')}
              {!up && up !== 0 && '.'}
              {s.weakest && (
                <>
                  {' '}
                  Хамгийн сул Map: {s.weakest} ({Math.round(s.weakest_share ?? 0)}% раунд).
                </>
              )}
            </>
          )}
        </p>
      </div>
      <div className="flex flex-[1_1_260px] flex-col items-center gap-1.5">
        <svg width="180" height="110" viewBox="0 0 180 110" role="img" aria-label={`Форм индекс ${f ?? '—'}/100`}>
          <path d="M15 100 A75 75 0 0 1 165 100" fill="none" stroke="var(--line)" strokeWidth="14" strokeLinecap="round" />
          {f != null && f > 0 && <path d={`M15 100 A75 75 0 0 1 ${end[0].toFixed(1)} ${end[1].toFixed(1)}`} fill="none" stroke={fc} strokeWidth="14" strokeLinecap="round" />}
          <text x="90" y="92" textAnchor="middle" fontFamily="IBM Plex Mono, monospace" fontSize="34" fontWeight="600" fill="var(--ink)">
            {f ?? '—'}
          </text>
        </svg>
        <span className="lbl">Форм индекс / 100</span>
        <span className="text-center text-xs text-ink-3">
          {d.rank ? `Багийн хүч ${Math.round(d.rating ?? 0)} · идэвхтэй ${d.ranked} багийн ${d.rank}-д` : 'Rating алга'}
        </span>
      </div>
    </section>
  )
}

function Kpis({ d }: { d: Owner }) {
  const k = d.kpis
  const delta = k.maps.pct != null && k.maps.prev != null ? k.maps.pct - k.maps.prev : null
  return (
    <section className="grid grid-cols-[repeat(auto-fit,minmax(min(200px,100%),1fr))] gap-3">
      <Kpi
        label="Хожлын хувь (Map)"
        value={k.maps.pct == null ? '—' : `${Math.round(k.maps.pct)}%`}
        color={tone(k.maps.pct, 60, 50)}
        sub={delta == null ? `${k.maps.won}/${k.maps.of} Map` : `${signed(delta, 0)} оноо өмнөх хугацаанаас`}
      />
      <Kpi label="Албан тоглолт" value={(k.matches.won ?? 0) + (k.matches.lost ?? 0)} sub={`${k.matches.won} хожил · ${k.matches.lost} ялагдал`} />
      <Kpi
        label="VRS байр"
        value={k.vrs?.regional ? `#${k.vrs.regional}` : '—'}
        sub={k.vrs ? `${k.vrs.region} бүс · дэлхийд #${k.vrs.global} · ${k.vrs.snapshot}` : 'VRS-д алга'}
      />
      <Kpi
        label="Бэлтгэлийн цаг"
        value={k.hours.total}
        sub={k.hours.total ? `Scrim ${k.hours.scrim} · дадлага ${k.hours.drill} · review ${k.hours.review}` : 'Бэлтгэлийн хуваарь оруулаагүй'}
      />
      <Kpi
        label="Боловсруулсан демо"
        value={k.parsed.of ? `${k.parsed.parsed}/${k.parsed.of}` : '—'}
        color={k.parsed.of && k.parsed.parsed === k.parsed.of ? GOOD : WARN}
        sub="Албан тоглолтын Map-уудаас"
      />
    </section>
  )
}

function Months({ d }: { d: Owner }) {
  const max = Math.max(1, ...d.months.map((m) => m.hours))
  const target = d.goals.find((g) => g.kpi === 'maps' && !g.map && !g.side)?.target ?? null
  const pts = d.months.map((m, i) => (m.pct == null ? null : ([50 + i * 100, 240 - (m.pct / 100) * 240] as const)))
  const path = pts
    .filter((p): p is readonly [number, number] => p != null)
    .map((p, i) => `${i ? 'L' : 'M'}${p[0]} ${p[1].toFixed(1)}`)
    .join(' ')
  return (
    <Panel
      title="Сар бүрийн хожлын хувь ба бэлтгэлийн цаг"
      className="flex-[999_1_600px]"
      right={
        <div className="flex gap-3.5 text-xs text-ink-3">
          <Swatch color={GOOD} line>Хожил %</Swatch>
          <Swatch color="#2A3A4A">Бэлтгэлийн цаг</Swatch>
          {target != null && <Swatch color={WARN} line dashed>Зорилт {target}%</Swatch>}
        </div>
      }
    >
      <div className="relative h-60">
        <div className="absolute inset-0 grid items-end gap-[18px] px-[9px]" style={{ gridTemplateColumns: `repeat(${d.months.length}, minmax(0, 1fr))` }}>
          {d.months.map((m) => (
            <div key={m.month} title={`${m.hours} цаг`} className="rounded-t-[3px] bg-[#2A3A4A]" style={{ height: `${(100 * m.hours) / max}%` }} />
          ))}
        </div>
        <svg viewBox="0 0 600 240" width="100%" height="240" preserveAspectRatio="none" className="absolute inset-0" role="img" aria-label="Сар бүрийн Map хожлын хувь">
          {target != null && <path d={`M0 ${240 - (target / 100) * 240} H600`} stroke={WARN} strokeWidth="2" strokeDasharray="6 5" />}
          <path d={path} fill="none" stroke={GOOD} strokeWidth="3" />
        </svg>
      </div>
      <div className="grid gap-[18px] px-[9px]" style={{ gridTemplateColumns: `repeat(${d.months.length}, minmax(0, 1fr))` }}>
        {d.months.map((m) => (
          <div key={m.month} className="flex flex-col items-center gap-0.5">
            <span className="num text-sm font-semibold" style={{ color: tone(m.pct, 60, 50) }}>
              {m.pct == null ? '—' : `${Math.round(m.pct)}%`}
            </span>
            <span className="text-xs text-ink-3">
              {MONTH[Number(m.month.slice(5, 7)) - 1]} · {m.maps} Map
            </span>
          </div>
        ))}
      </div>
      <p className="m-0 text-[13px] leading-normal text-ink-3">Цаг = Бэлтгэлийн хуваарийн scrim, дадлага, review. Хамаарал нь шалтгаан биш: чиг хандлагыг л харуулна.</p>
    </Panel>
  )
}

function Tiers({ d }: { d: Owner }) {
  return (
    <Panel title="Өрсөлдөгчийн түвшнээр" sub="Өрсөлдөгчийн одоогийн Rating-ийн байраар · бүх хадгалсан Map" className="flex-[1_1_340px]">
      {d.tiers.length === 0 ? (
        <Empty>Rating-тай өрсөлдөгчтэй Map алга.</Empty>
      ) : (
        d.tiers.map((t) => {
          const pct = t.maps ? (100 * t.won) / t.maps : null
          const c = tone(pct, 60, 45)
          return (
            <div key={t.tier} className="flex flex-col gap-1.5">
              <div className="flex justify-between gap-2 text-sm">
                <span>{t.tier}</span>
                <span className="num font-semibold" style={{ color: c }}>
                  {pct == null ? '—' : `${Math.round(pct)}%`}{' '}
                  <span className="font-normal text-ink-3">
                    ({t.won}–{t.maps - t.won} · хүлээлт {t.expected})
                  </span>
                </span>
              </div>
              <Bar pct={pct} color={c} h={10} />
            </div>
          )
        })
      )}
    </Panel>
  )
}

function Players({ d }: { d: Owner }) {
  const shown = d.players.filter((p) => p.share != null)
  return (
    <Panel title="Тоглогчдын хувь нэмэр ба тогтвортой байдал" sub="Багийн эерэг Swing-ийн хувь · сар бүрийн Player rating · σ = Map хоорондын хэлбэлзэл" className="flex-[999_1_600px]">
      {shown.length > 0 && (
        <div className="flex h-9 overflow-hidden rounded-md">
          {shown.map((p, i) => (
            <div key={p.steamid} className="cond grid place-items-center truncate text-[13px] font-bold text-[#0A0D10]" style={{ width: `${p.share}%`, background: PALETTE[i % PALETTE.length] }}>
              {p.name} {Math.round(p.share ?? 0)}%
            </div>
          ))}
        </div>
      )}
      {d.players.length === 0 ? (
        <Empty />
      ) : (
        d.players.map((p, i) => {
          const values = p.spark.filter((v): v is number => v != null)
          const trendUp = values.length > 1 && values[values.length - 1] >= values[0]
          return (
            <div key={p.steamid} className="grid grid-cols-[14px_minmax(0,1fr)_100px_60px] items-center gap-3 border-t border-line py-2.5 sm:grid-cols-[14px_110px_110px_70px_minmax(0,1fr)]">
              <span className="h-3 w-3 rounded-[3px]" style={{ background: PALETTE[i % PALETTE.length] }} />
              <span className="truncate font-semibold">{p.name}</span>
              {values.length > 1 ? (
                <svg width="100" height="24" viewBox="0 0 100 24" aria-hidden="true">
                  <path d={sparkPath(values, 100, 24, Math.min(0.8, ...values), Math.max(1.3, ...values))} fill="none" stroke={trendUp ? GOOD : CRIT} strokeWidth="2" />
                </svg>
              ) : (
                <span className="text-xs text-ink-3">—</span>
              )}
              <span className="num text-[13px]" style={{ color: p.sigma != null && p.sigma > 0.3 ? WARN : 'var(--ink-2)' }}>
                σ {p.sigma ?? '—'}
              </span>
              <span className="col-span-full text-[13px] text-ink-2 sm:col-span-1">
                Rating {p.rating ?? '—'} · {p.maps} Map
              </span>
            </div>
          )
        })
      )}
    </Panel>
  )
}

function Goals({ d }: { d: Owner }) {
  const color = (v: string) => (v === 'reached' ? GOOD : v === 'close' ? WARN : v === 'no_data' ? MUTED : CRIT)
  return (
    <Panel title="Улирлын зорилтууд">
      {d.goals.length === 0 ? (
        <Empty>Team goal алга (Бэлтгэл хуудаснаас нэмнэ).</Empty>
      ) : (
        d.goals.map((g) => {
          const p = g.progress
          const share = p.value == null ? 0 : g.better === 'lower' ? Math.min(100, (100 * g.target) / Math.max(p.value, 1)) : Math.min(100, (100 * p.value) / Math.max(g.target, 1))
          return (
            <div key={g.id} className="flex flex-col gap-1.5">
              <div className="flex justify-between gap-2 text-sm">
                <span>{g.title || g.label}</span>
                <span className="num text-[13px]" style={{ color: color(p.verdict) }}>
                  {p.value ?? '—'}
                  {g.unit} / {g.target}
                  {g.unit}
                </span>
              </div>
              <Bar pct={share} color={color(p.verdict)} />
            </div>
          )
        })
      )}
    </Panel>
  )
}

function Risks({ d }: { d: Owner }) {
  return (
    <Panel title="Эрсдэл ба боломж">
      {d.risks.length === 0 ? (
        <Empty>Pool-оос ялгарах зүйл алга.</Empty>
      ) : (
        d.risks.map((r) => (
          <div key={r.text} className="flex items-start gap-2.5 border-t border-line pt-2.5">
            <Tag color={r.kind === 'opening' ? GOOD : r.tone === 'risk' ? CRIT : WARN} solid>
              {r.kind === 'opening' ? 'Боломж' : 'Эрсдэл'}
            </Tag>
            <span className="text-[13px] leading-normal text-ink-2">{r.text}</span>
          </div>
        ))
      )}
    </Panel>
  )
}

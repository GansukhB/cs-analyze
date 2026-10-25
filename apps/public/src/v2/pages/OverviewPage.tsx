// v2 screen 01, the team's command centre: KPIs over a period against the one
// before it, Strengths and Weaknesses against the Pool with their Rounds, the
// Map pool, form, the five's Player rating, the pipeline and the next match.
import { Link, useSearchParams } from 'react-router'
import { $api } from '../../api/client'
import type { components } from '../../api/schema'
import { LoadError } from '../../ui/LoadError'
import { PageSkeleton } from '../../ui/Skeleton'
import { at, initials, useTeam } from '../team'
import { UpcomingBlock } from '../Upcoming'
import { AddToQueue } from '../AddToQueue'
import { CRIT, CT, GOOD, MUTED, T, WARN, ghostLink, insightValue, shortDate, signed, sparkPath, tone } from '../format'
import { Bar, Button, Empty, Panel, PageHead, Spark, Swatch, Tag, Toggle } from '../ui'

type Overview = components['schemas']['Overview']
type Share = components['schemas']['Share']
type Insight = components['schemas']['Insight']

const PERIODS = [
  ['30', '30 хоног'],
  ['90', '90 хоног'],
  ['180', '180 хоног'],
  ['all', 'Бүгд'],
] as const
type Period = (typeof PERIODS)[number][0]

export default function OverviewPage() {
  const team = useTeam()
  const [params, setParams] = useSearchParams()
  const period = (PERIODS.find(([k]) => k === params.get('period'))?.[0] ?? '30') as Period
  const scrims = params.get('scrims') === '1'
  const q = $api.useQuery('get', '/v2/teams/{team_id}/overview', {
    params: { path: { team_id: team.id }, query: { period, scrims } },
  })
  const set = (key: string, value: string | null) =>
    setParams(
      (p) => {
        if (value === null) p.delete(key)
        else p.set(key, value)
        return p
      },
      { replace: true },
    )
  if (q.error) return <LoadError error={q.error} what="Тойм" retry={() => void q.refetch()} />
  if (!q.data) return <PageSkeleton />
  const d = q.data
  const label = PERIODS.find(([k]) => k === period)?.[1]
  return (
    <>
      <PageHead
        label="Багийн командын төв"
        title={`Тойм · ${period === 'all' ? 'Бүх хугацаа' : `Сүүлийн ${label}`}`}
        sub={
          <>
            {d.n_matches} албан ёсны тоглолт{d.scrims ? `, ${d.n_scrims} scrim` : ''} · {d.n_maps} Map задлагдсан
            {d.updated_at && ` · Сүүлд шинэчилсэн ${new Date(d.updated_at).toLocaleString('mn-MN', { timeZone: 'Asia/Ulaanbaatar', hour12: false })}`}
          </>
        }
        actions={
          <>
            <Toggle label="Хугацаа" options={PERIODS} value={period} onChange={(k) => set('period', k === '30' ? null : k)} />
            <Toggle
              label="Тоглолтын төрөл"
              options={[
                ['official', 'Албан'],
                ['all', 'Албан + Scrim'],
              ]}
              value={scrims ? 'all' : 'official'}
              onChange={(k) => set('scrims', k === 'all' ? '1' : null)}
            />
            <Button onClick={() => window.print()}>PDF тайлан</Button>
          </>
        }
      />
      <Kpis d={d} />
      <Insights teamId={team.id} insights={d.insights} />
      <section className="flex flex-wrap gap-4">
        <MapTable d={d} />
        <FormPanel d={d} teamId={team.id} />
      </section>
      <Players d={d} teamId={team.id} />
      <Pipeline d={d} teamId={team.id} />
    </>
  )
}

function Delta({ s }: { s: Share }) {
  if (s.pct == null || s.prev == null) return null
  const d = s.pct - s.prev
  return (
    <span className="num text-[13px]" style={{ color: d > 0 ? GOOD : d < 0 ? CRIT : MUTED }}>
      {signed(d)}
    </span>
  )
}

function KpiTile(props: { label: string; s: Share; sub: string; bar: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2.5 rounded-lg border border-line bg-surface p-4.5">
      <span className="lbl">{props.label}</span>
      <div className="flex items-baseline gap-2.5">
        <span className="num text-[32px] font-semibold">{props.s.pct == null ? '—' : `${props.s.pct}%`}</span>
        <Delta s={props.s} />
      </div>
      {props.bar}
      <span className="text-[13px] text-ink-3">{props.sub}</span>
    </div>
  )
}

function Split(props: { a: number | null | undefined; ca: string; b?: number | null; cb?: string }) {
  return (
    <div className="flex h-1.5 overflow-hidden rounded-full bg-line">
      <div style={{ width: `${props.b === undefined ? (props.a ?? 0) : (props.a ?? 0) / 2}%`, background: props.ca }} />
      {props.b !== undefined && <div style={{ width: `${(props.b ?? 0) / 2}%`, background: props.cb }} />}
    </div>
  )
}

function Kpis({ d }: { d: Overview }) {
  const k = d.kpis
  const of = (s: Share, what: string) => `${s.of}-аас ${s.won} ${what}`
  return (
    <section aria-label="Гол үзүүлэлтүүд" className="grid grid-cols-[repeat(auto-fit,minmax(min(160px,100%),1fr))] gap-3">
      <KpiTile
        label="Газрын зургийн хожил"
        s={k.maps}
        bar={<Split a={k.maps.pct} ca={GOOD} />}
        sub={`${k.maps.won} хожил · ${k.maps.of - k.maps.won} ялагдал`}
      />
      <KpiTile
        label="Round хожил"
        s={k.rounds}
        bar={<Split a={k.rounds_t.pct} ca={T} b={k.rounds_ct.pct} cb={CT} />}
        sub={`T ${k.rounds_t.pct ?? '—'}% · CT ${k.rounds_ct.pct ?? '—'}%`}
      />
      <KpiTile label="Pistol round" s={k.pistol} bar={<Split a={k.pistol.pct} ca={GOOD} />} sub={of(k.pistol, 'хожсон')} />
      <KpiTile
        label="Opening duel"
        s={k.opening}
        bar={<Split a={k.opening.pct} ca={GOOD} />}
        sub={`Эхний алалт хожсон · ${k.opening.of} duel`}
      />
      <KpiTile
        label="Trade хувь"
        s={k.trade}
        bar={<Split a={k.trade.pct} ca={GOOD} />}
        sub={`Үхлийн ${k.trade.won}/${k.trade.of} нь 5 сек дотор trade хийгдсэн`}
      />
      <KpiTile
        label="Post-plant хожил"
        s={k.post_plant}
        bar={<Split a={k.post_plant.pct} ca={T} />}
        sub={`Бөмбөг суулгасны дараа · ${of(k.post_plant, 'хожсон')}`}
      />
    </section>
  )
}

const TONE: Record<Insight['tone'], [string, string]> = {
  strength: ['Давуу тал', GOOD],
  risk: ['Эрсдэл', CRIT],
  watch: ['Анхаар', WARN],
}

function Insights({ teamId, insights }: { teamId: number; insights: Insight[] }) {
  return (
    <section className="flex flex-col gap-3.5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="cond m-0 text-[22px] font-bold">Автомат олдворууд</h2>
        <span className="text-[13px] text-ink-3">Review бүрийн дүнг бусад багуудын (Pool) дүнтэй жишсэн</span>
      </div>
      {insights.length === 0 ? (
        <Empty>Pool-оос ялгарах давуу, сул тал одоохондоо алга (Review хангалтгүй эсвэл бүгд дунджид).</Empty>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(300px,100%),1fr))] gap-3">
          {insights.map((x) => {
            const [tag, color] = TONE[x.tone]
            const first = x.refs[0]
            return (
              <article key={`${x.key}-${x.side}-${x.map}`} className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-4.5">
                <div className="flex items-center justify-between gap-2">
                  <Tag color={color} solid>
                    {tag}
                  </Tag>
                  <span className="num text-xs text-ink-3">
                    {x.map_label ?? 'Бүх газрын зураг'} · {x.side.toUpperCase()}
                  </span>
                </div>
                <h3 className="m-0 text-base leading-snug font-semibold">{x.title}</h3>
                <div className="flex items-baseline gap-2">
                  <span className="num text-[28px] font-semibold" style={{ color }}>
                    {insightValue(x)}
                  </span>
                  <span className="text-[13px] text-ink-3">
                    {x.label} · бусад {insightValue({ kind: x.kind, value: x.pool })} · {x.of} {x.kind === 'rate' ? 'тохиолдол' : 'раунд'}
                  </span>
                </div>
                {x.advice && <p className="m-0 text-sm leading-relaxed text-ink-2">{x.advice}</p>}
                {x.players.length > 0 && <span className="text-xs text-ink-3">Голчлон: {x.players.join(', ')}</span>}
                <div className="mt-auto flex flex-wrap gap-4">
                  {first && (
                    <Link to={`${at(teamId, 'replay', first.match, first.map)}?round=${first.round}`} className="py-1.5 text-sm">
                      2D-д үзэх ({x.refs.length} раунд)
                    </Link>
                  )}
                  {x.map && x.refs.length > 1 && (
                    <Link to={ghostLink(x.refs)} className="py-1.5 text-sm">
                      ⧉ давхарлаж үзэх
                    </Link>
                  )}
                  {first && (
                    <AddToQueue
                      teamId={teamId}
                      label="Бэлтгэлд нэмэх"
                      moment={() => ({ match_id: first.match, map_number: first.map, round: first.round, t: 0 })}
                      title={x.title}
                      tag={x.tone === 'strength' ? 'Давуу тал' : 'Сайжруулах'}
                      source={`Тойм · ${x.map_label ?? 'бүх Map'} ${x.side.toUpperCase()}`}
                    />
                  )}
                </div>
              </article>
            )
          })}
        </div>
      )}
    </section>
  )
}

const STATUS: Record<string, [string, string]> = {
  strong: ['Хүчтэй', GOOD],
  improve: ['Сайжруулах', WARN],
  test: ['Туршилт', CT],
  untested: ['Тоглоогүй', MUTED],
}

function SideBar({ v, color }: { v: number | null | undefined; color: string }) {
  return (
    <div className="flex items-center gap-2">
      <Bar pct={v} color={color} h={6} className="w-20" />
      <span className="num text-[13px]">{v ?? '—'}</span>
    </div>
  )
}

function MapTable({ d }: { d: Overview }) {
  return (
    <Panel
      title="Газрын зургийн сан"
      className="flex-[999_1_640px]"
      right={
        <div className="flex gap-3.5 text-[13px] text-ink-3">
          <Swatch color={T}>T тал</Swatch>
          <Swatch color={CT}>CT тал</Swatch>
        </div>
      }
    >
      <div className="overflow-x-auto">
        <table className="grid-table">
          <thead>
            <tr>
              <th>Газрын зураг</th>
              <th>Тоглосон</th>
              <th>Хожил</th>
              <th>T round %</th>
              <th>CT round %</th>
              <th>Pistol</th>
              <th>Сүүлийн 8 Map</th>
              <th>Төлөв</th>
            </tr>
          </thead>
          <tbody>
            {d.maps.map((m) => {
              const [word, color] = STATUS[m.status]
              const wc = tone(m.win, 60, 50)
              return (
                <tr key={m.map} className={m.active ? '' : 'opacity-60'}>
                  <td className="cond text-base font-semibold">{m.label}</td>
                  <td className="num">{m.played || '—'}</td>
                  <td className="num font-semibold" style={{ color: m.win == null ? MUTED : wc }}>
                    {m.win == null ? '—' : `${Math.round(m.win)}%`}
                  </td>
                  <td>
                    <SideBar v={m.t} color={T} />
                  </td>
                  <td>
                    <SideBar v={m.ct} color={CT} />
                  </td>
                  <td className="num">{m.pistol == null ? '—' : `${Math.round(m.pistol)}%`}</td>
                  <td>
                    {m.trend.length > 1 ? (
                      <Spark values={m.trend} lo={0.2} hi={0.9} base={0.5} color={tone(100 * (m.trend.at(-1) ?? 0.5), 55, 45)} />
                    ) : (
                      <span className="text-ink-3">—</span>
                    )}
                  </td>
                  <td>
                    <Tag color={color}>{word}</Tag>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="m-0 text-xs text-ink-3">
        Хожил, T/CT, pistol нь сонгосон хугацааных; «Төлөв» болон шугам нь бүх албан тоглолтоос (раундын хувь).
      </p>
    </Panel>
  )
}

function FormPanel({ d, teamId }: { d: Overview; teamId: number }) {
  const values = d.trend.map((p) => p.rating)
  const lo = Math.min(0.8, ...values) - 0.05
  const hi = Math.max(1.2, ...values) + 0.05
  const path = sparkPath(values, 320, 120, lo, hi)
  const last = values.at(-1)
  const first = values[0]
  const baseY = 120 - ((1 - lo) / (hi - lo)) * 120
  return (
    <Panel title={`Сүүлийн ${d.form.length} тоглолт`} className="flex-[1_1_360px]">
      {d.form.length === 0 ? (
        <Empty />
      ) : (
        <div className="grid gap-1" style={{ gridTemplateColumns: `repeat(${Math.max(d.form.length, 1)}, minmax(0, 1fr))` }}>
          {d.form.map((f) => (
            <div
              key={f.match_id}
              title={`${shortDate(f.played_at)} ${f.opponent} ${f.ours}–${f.theirs}${f.scrim ? ' (scrim)' : ''}`}
              className="cond grid h-10 place-items-center rounded text-[13px] font-bold text-[#0A0D10]"
              style={{ background: f.won == null ? WARN : f.won ? GOOD : CRIT, opacity: f.scrim ? 0.6 : 1 }}
            >
              {f.won == null ? 'Т' : f.won ? 'Х' : 'Я'}
            </div>
          ))}
        </div>
      )}
      <div className="flex flex-col gap-1.5">
        <div className="flex justify-between">
          <span className="lbl">Багийн дундаж Rating · Map бүрээр</span>
          {last != null && first != null && (
            <span className="num text-[13px]" style={{ color: last >= first ? GOOD : CRIT }}>
              {last.toFixed(2)} {last >= first ? '↑' : '↓'}
            </span>
          )}
        </div>
        {values.length > 1 ? (
          <>
            <svg viewBox="0 0 320 120" width="100%" height="140" preserveAspectRatio="none" role="img"
              aria-label={`Сүүлийн ${values.length} Map-ийн багийн дундаж Player rating, ${Math.min(...values).toFixed(2)}-оос ${Math.max(...values).toFixed(2)} хооронд`}>
              <path d={`M0 ${baseY} H320`} stroke="var(--line-strong)" strokeDasharray="3 4" />
              <path d={`${path} L320 120 L0 120 Z`} fill={GOOD} fillOpacity={0.08} />
              <path d={path} fill="none" stroke={GOOD} strokeWidth={2.5} />
            </svg>
            <div className="num flex justify-between text-xs text-ink-3">
              <span>{shortDate(d.trend[0].played_at)}</span>
              <span>1.00 суурь</span>
              <span>{shortDate(d.trend.at(-1)?.played_at)}</span>
            </div>
          </>
        ) : (
          <Empty />
        )}
      </div>
      <div className="flex flex-col gap-2.5 border-t border-line pt-3.5">
        <span className="lbl">Ирэх тоглолт</span>
        <UpcomingBlock teamId={teamId} upcoming={d.upcoming} />
      </div>
    </Panel>
  )
}

function ratingColor(r: number | null | undefined) {
  if (r == null) return MUTED
  return r >= 1.1 ? GOOD : r >= 0.95 ? 'var(--ink)' : WARN
}

function Players({ d, teamId }: { d: Overview; teamId: number }) {
  return (
    <section className="flex flex-col gap-3.5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="cond m-0 text-[22px] font-bold">Тоглогчид</h2>
        <span className="text-[13px] text-ink-3">Сүүлийн тоглолтын 5 · Rating = HLTV 2.0-ийн ойролцоо томьёо</span>
      </div>
      {d.players.length === 0 ? (
        <Empty />
      ) : (
        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(220px,100%),1fr))] gap-3">
          {d.players.map((p) => (
            <Link
              key={p.steamid}
              to={at(teamId, 'players', p.steamid)}
              className="plain flex flex-col gap-3 rounded-lg border border-line bg-surface p-4 !text-ink hover:border-line-strong"
            >
              <div className="flex items-center gap-3">
                <div className="cond grid h-11 w-11 place-items-center rounded-full border border-line-strong bg-chip font-bold">
                  {initials(p.name)}
                </div>
                <div className="flex flex-col gap-0.5">
                  <span className="cond text-lg font-bold">{p.name}</span>
                  <span className="text-[13px] text-ink-3">{p.maps} Map энэ хугацаанд</span>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <Stat label="Rating" value={p.rating?.toFixed(2)} color={ratingColor(p.rating)} />
                <Stat label="ADR" value={p.adr?.toFixed(1)} />
                <Stat label="KAST" value={p.kast == null ? undefined : `${Math.round(p.kast)}%`} />
              </div>
              {p.note && (
                <span className="text-[13px] leading-snug" style={{ color: p.note.good ? 'var(--ink-2)' : 'var(--warn)' }}>
                  {p.note.text}
                </span>
              )}
            </Link>
          ))}
        </div>
      )}
    </section>
  )
}

function Stat(props: { label: string; value: string | undefined; color?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="lbl !text-[11px]">{props.label}</span>
      <span className="num text-lg font-semibold" style={{ color: props.color }}>
        {props.value ?? '—'}
      </span>
    </div>
  )
}

const STAGE: Record<string, string> = {
  queued: 'Дараалалд',
  resolving: 'Баг тодорхойлж байна',
  fetching: 'Татаж байна',
  unpacking: 'Задалж байна',
  parsing: 'Parse хийж байна',
  analysing: 'Шинжилж байна',
  rendering: 'Зурж байна',
  done: 'Дууссан',
}
const STATUS_COLOR: Record<string, string> = {
  queued: MUTED,
  running: WARN,
  success: GOOD,
  failed: CRIT,
  cancelled: MUTED,
  receiving: WARN,
  parsing: WARN,
  needs_sides: WARN,
  done: GOOD,
}
const UPLOAD: Record<string, string> = {
  receiving: 'Хүлээн авч байна',
  queued: 'Дараалалд',
  parsing: 'Parse хийж байна',
  needs_sides: 'Аль тал нь бид вэ? (сонгох)',
  done: 'Бэлэн',
  failed: 'Алдаа',
}

function Pipeline({ d, teamId }: { d: Overview; teamId: number }) {
  return (
    <Panel
      title="Демо сан ба боловсруулалт"
      sub=".dem файл, архив эсвэл линк · HLTV-ийн Scout"
      right={
        <div className="flex gap-4 text-sm">
          <Link to={at(teamId, 'uploads')}>Демо оруулах</Link>
          <Link to={at(teamId, 'jobs')}>Бүх ажил</Link>
        </div>
      }
    >
      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(220px,100%),1fr))] gap-2">
        {d.jobs.map((j) => (
          <Link
            key={j.public_id}
            to={at(teamId, 'jobs', j.public_id)}
            className="plain flex flex-col gap-1.5 rounded-md border border-line-soft bg-surface-2 p-3 !text-ink"
          >
            <span className="num text-xs text-ink-3">{j.kind === 'scout' ? 'Scout' : j.kind}</span>
            <span className="cond truncate text-base font-semibold">{j.label}</span>
            <span className="num text-[13px]" style={{ color: STATUS_COLOR[j.status] ?? MUTED }}>
              {j.status === 'running' ? `${STAGE[j.stage] ?? j.stage} ${j.progress}%` : j.status === 'success' ? 'Бэлэн' : j.status}
            </span>
          </Link>
        ))}
        {d.uploads.map((u) => (
          <Link key={`u${u.id}`} to={at(teamId, 'uploads')} className="plain flex flex-col gap-1.5 rounded-md border border-line-soft bg-surface-2 p-3 !text-ink">
            <span className="num text-xs text-ink-3">Upload · {u.kind}</span>
            <span className="cond truncate text-base font-semibold">{u.filename}</span>
            <span className="num text-[13px]" style={{ color: STATUS_COLOR[u.status] ?? MUTED }}>
              {UPLOAD[u.status] ?? u.status}
            </span>
          </Link>
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="grid-table">
          <thead>
            <tr>
              <th>Огноо</th>
              <th>Өрсөлдөгч</th>
              <th>Газрын зураг</th>
              <th>Оноо</th>
              <th>Төрөл</th>
              <th>Төлөв</th>
              <th>Үйлдэл</th>
            </tr>
          </thead>
          <tbody>
            {d.demos.map((m) => {
              const won = m.ours != null && m.theirs != null ? m.ours > m.theirs : null
              return (
                <tr key={`${m.match_id}-${m.map_number}`}>
                  <td className="num text-ink-3">{shortDate(m.played_at)}</td>
                  <td className="font-semibold">{m.opponent}</td>
                  <td>{m.map}</td>
                  <td className="num font-semibold" style={{ color: won == null ? MUTED : won ? GOOD : CRIT }}>
                    {m.ours != null ? `${m.ours}–${m.theirs}` : '—'}
                  </td>
                  <td className="text-ink-3">{m.kind === 'scrim' ? 'Scrim' : 'Албан'}</td>
                  <td style={{ color: m.parsed ? GOOD : WARN }}>{m.parsed ? 'Бэлэн' : 'Parse хийгдээгүй'}</td>
                  <td>
                    {m.parsed && (
                      <div className="flex gap-3.5">
                        <Link to={at(teamId, 'replay', m.match_id, m.map_number)}>Replay</Link>
                        <Link to={at(teamId, 'matches', m.match_id, 'm', m.map_number)}>Тайлан</Link>
                      </div>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}

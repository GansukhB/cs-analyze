// v2 screen 03: one Match Map from the my team's side. The Rounds' flow and
// economy, the score's run, what decided it, both scoreboards, the record by buy
// and the Rounds that turned.
import { Link, useParams } from 'react-router'
import { $api } from '../../api/client'
import type { components } from '../../api/schema'
import { LoadError } from '../../ui/LoadError'
import { PageSkeleton } from '../../ui/Skeleton'
import { CRIT, CT, GOOD, MUTED, T, WARN, shortDate } from '../format'
import { at, useTeam } from '../team'
import { Bar, Button, ButtonLink, Empty, PageHead, Panel, Swatch } from '../ui'

type Report = components['schemas']['MatchReport']
type Row = components['schemas']['ReportRound']

const BUY: Record<string, string> = { pistol: 'P', eco: 'E', force: 'F', full: 'B' }

export default function MatchReportPage() {
  const team = useTeam()
  const { matchId = '', mapNumber = '1' } = useParams()
  const q = $api.useQuery('get', '/v2/teams/{team_id}/matches/{match_id}/maps/{map_number}/report', {
    params: { path: { team_id: team.id, match_id: Number(matchId), map_number: Number(mapNumber) } },
  })
  if (q.error) return <LoadError error={q.error} what="Тоглолтын тайлан" retry={() => void q.refetch()} />
  if (!q.data) return <PageSkeleton />
  const d = q.data
  const won = d.ours != null && d.theirs != null ? d.ours > d.theirs : null
  return (
    <>
      <PageHead
        label="Тоглолтын тайлан"
        title={`${d.label} · vs ${d.them?.name ?? '?'}`}
        actions={
          <>
            <ButtonLink to={at(team.id, 'replay', d.match_id, d.map_number)}>2D Replay</ButtonLink>
            <ButtonLink to={`/matches/${d.match_id}/m/${d.map_number}`}>Review (v1)</ButtonLink>
            <Button primary onClick={() => window.print()}>
              PDF тайлан
            </Button>
          </>
        }
      />
      {d.maps.length > 1 && (
        <nav aria-label="Газрын зураг" className="flex flex-wrap gap-1.5">
          {d.maps.map((m) =>
            m.parsed ? (
              <Link
                key={m.map_number}
                to={at(team.id, 'matches', d.match_id, 'm', m.map_number)}
                aria-current={m.map_number === d.map_number ? 'page' : undefined}
                className={`plain flex h-10 items-center gap-2 rounded-md border px-3.5 text-sm ${
                  m.map_number === d.map_number ? 'border-accent bg-accent-soft !text-accent' : 'border-line-strong !text-ink-2'
                }`}
              >
                {m.label} <span className="num text-xs text-ink-3">{m.score}</span>
              </Link>
            ) : (
              <span key={m.map_number} className="flex h-10 items-center px-3.5 text-sm text-ink-3">
                {m.label} {m.score}
              </span>
            ),
          )}
        </nav>
      )}
      <section className="flex flex-wrap items-center justify-between gap-5 rounded-lg border border-line bg-surface p-6">
        <div className="flex flex-col gap-1.5">
          <span className="lbl">
            {d.kind === 'scrim' ? 'Scrim' : 'Албан'}
            {d.kind !== 'scrim' && ` · BO${d.best_of} · Газрын зураг ${d.map_number}/${d.maps.length}`} ·{' '}
            {shortDate(d.played_at)}
            {d.seconds != null && ` · ${Math.round(d.seconds / 60)} мин`}
            {d.tournament && ` · ${d.tournament}`}
          </span>
          <div className="flex flex-wrap items-center gap-5">
            <span className="cond text-[30px] font-bold">{d.us.name}</span>
            <span className="num text-5xl font-semibold">
              <span style={{ color: won == null ? 'var(--ink)' : won ? GOOD : CRIT }}>{d.ours ?? '—'}</span>
              <span className="text-ink-3"> : </span>
              {d.theirs ?? '—'}
            </span>
            <span className="cond text-[30px] font-bold text-ink-2">{d.them?.name}</span>
          </div>
          <span className="text-sm text-ink-3">
            {d.halves.map((h, i) => (
              <span key={i}>
                {i > 0 && ' · '}
                {i === 0 ? '1-р хагас' : i === 1 ? '2-р хагас' : `OT ${i - 1}`}{' '}
                <span style={{ color: h.side === 'ct' ? CT : T }}>
                  {(h.side ?? '').toUpperCase()} {h.ours}–{h.theirs}
                </span>
              </span>
            ))}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-4.5 sm:grid-cols-4">
          <Quick label="Opening" v={`${d.quick.opening[0]}–${d.quick.opening[1]}`} />
          <Quick label="Trade" v={`${d.quick.trade[0]}–${d.quick.trade[1]}`} />
          <Quick label="Clutch" v={`${d.quick.clutch[0]}–${d.quick.clutch[1]}`} />
          <Quick label="Post-plant" v={`${d.quick.post_plant[0]}/${d.quick.post_plant[1]}`} />
        </div>
      </section>
      <Flow d={d} />
      <section className="flex flex-wrap gap-4">
        <DiffPanel d={d} />
        <Factors d={d} />
      </section>
      {d.teams.map((t, i) => (
        <Board key={t.team.id} t={t} mine={i === 0} />
      ))}
      <section className="flex flex-wrap gap-4">
        <Buys d={d} />
        <Turning d={d} teamId={team.id} />
      </section>
    </>
  )
}

function Quick({ label, v }: { label: string; v: string }) {
  return (
    <div className="flex min-w-[90px] flex-col gap-1">
      <span className="lbl">{label}</span>
      <span className="num text-2xl font-semibold">{v}</span>
    </div>
  )
}

function Flow({ d }: { d: Report }) {
  const max = Math.max(26000, ...d.rounds.map((r) => Math.max(r.ours ?? 0, r.theirs ?? 0)))
  const cols = `110px repeat(${d.rounds.length}, minmax(0, 1fr))`
  const half = (r: Row, i: number) => i > 0 && r.side !== d.rounds[i - 1].side
  return (
    <Panel
      title="Раунд бүрийн урсгал ба эдийн засаг"
      right={
        <div className="num flex flex-wrap gap-3.5 text-xs text-ink-3">
          <span>E = бүгдийг устгасан</span>
          <span>B = бөмбөг дэлбэрсэн</span>
          <span>D = тайлсан</span>
          <span>T = хугацаа</span>
        </div>
      }
    >
      <div className="overflow-x-auto">
        <div className="flex flex-col gap-1.5" style={{ minWidth: Math.max(600, 110 + d.rounds.length * 34) }}>
          <div className="grid items-end gap-[3px]" style={{ gridTemplateColumns: cols }}>
            <span className="lbl self-center">Бидний зардал</span>
            {d.rounds.map((r, i) => (
              <div key={r.n} className="flex h-[90px] flex-col justify-end" style={{ borderLeft: half(r, i) ? '2px dashed #3A4652' : undefined }}>
                <div
                  title={`$${r.ours ?? '?'}`}
                  className="rounded-t-sm"
                  style={{ height: `${((r.ours ?? 0) / max) * 100}%`, background: r.side === 'ct' ? CT : T }}
                />
              </div>
            ))}
          </div>
          <div className="grid gap-[3px]" style={{ gridTemplateColumns: cols }}>
            <span className="lbl self-center">Хожил</span>
            {d.rounds.map((r) => (
              <div
                key={r.n}
                title={`R${r.n} ${r.won ? 'хожсон' : 'хожигдсон'}${r.site ? ` · ${r.site}` : ''}`}
                className="flex h-11 flex-col items-center justify-center gap-px rounded"
                style={{
                  background: r.won ? 'var(--good-soft)' : 'var(--crit-soft)',
                  color: r.won ? GOOD : CRIT,
                  outline: r.turning ? `2px solid ${WARN}` : undefined,
                }}
              >
                <span className="num text-[11px] opacity-80">{r.n}</span>
                <span className="num text-[13px] font-bold">{r.end}</span>
              </div>
            ))}
          </div>
          <div className="grid items-start gap-[3px]" style={{ gridTemplateColumns: cols }}>
            <span className="lbl self-center">Эсрэг багийн</span>
            {d.rounds.map((r) => (
              <div key={r.n} className="flex h-[90px] flex-col justify-start">
                <div title={`$${r.theirs ?? '?'}`} className="rounded-b-sm" style={{ height: `${((r.theirs ?? 0) / max) * 100}%`, background: '#3A4652' }} />
              </div>
            ))}
          </div>
          <div className="grid gap-[3px]" style={{ gridTemplateColumns: cols }}>
            <span className="lbl">Худалдан авалт</span>
            {d.rounds.map((r) => (
              <span key={r.n} className="num text-center text-[11px] text-ink-3">
                {BUY[r.our_buy] ?? '·'}
              </span>
            ))}
          </div>
        </div>
      </div>
      <div className="flex flex-wrap gap-4.5 text-[13px] text-ink-3">
        <Swatch color={CT}>Бид CT</Swatch>
        <Swatch color={T}>Бид T</Swatch>
        <Swatch color="#3A4652">Эсрэг баг</Swatch>
        <span className="num">P pistol · E eco · F force · B full buy · Хүрээтэй = эргэлтийн раунд</span>
      </div>
    </Panel>
  )
}

function DiffPanel({ d }: { d: Report }) {
  const n = d.rounds.length
  const w = 460
  const step = w / Math.max(n, 1)
  let diff = 0
  const pts: [number, number][] = [[0, 0]]
  d.rounds.forEach((r, i) => {
    diff += r.won ? 1 : r.won === false ? -1 : 0
    pts.push([(i + 1) * step, diff])
  })
  const span = Math.max(4, ...pts.map(([, v]) => Math.abs(v)))
  const y = (v: number) => 90 - (v / span) * 80
  const path = pts.map(([x, v], i) => `${i ? 'L' : 'M'}${x.toFixed(1)} ${y(v).toFixed(1)}`).join(' ')
  // The halves shaded by our Side.
  const bands: { x: number; w: number; side: string | null }[] = []
  d.rounds.forEach((r, i) => {
    const last = bands.at(-1)
    if (last && last.side === r.side) last.w += step
    else bands.push({ x: i * step, w: step, side: r.side })
  })
  return (
    <Panel title="Онооны зөрүүний урсгал" className="flex-[1_1_520px]">
      <svg viewBox={`0 0 ${w} 180`} width="100%" height="200" preserveAspectRatio="none" role="img"
        aria-label={`Раунд бүрийн дараах онооны зөрүү, эцэст нь ${diff > 0 ? '+' : ''}${diff}`}>
        {bands.map((b, i) => (
          <rect key={i} x={b.x} y={0} width={b.w} height={180} fill={b.side === 'ct' ? CT : T} fillOpacity={0.05} />
        ))}
        <path d={`M0 90 H${w}`} stroke="var(--line-strong)" />
        <path d={path} fill="none" stroke={GOOD} strokeWidth={2.5} />
      </svg>
      <div className="num flex justify-between text-xs text-ink-3">
        <span>R1</span>
        <span>
          ±{span} раунд · сүүдэр = бидний тал (CT цэнхэр, T улбар)
        </span>
        <span>R{n}</span>
      </div>
    </Panel>
  )
}

function Factors({ d }: { d: Report }) {
  return (
    <Panel title="Ялалтын гол хүчин зүйлс" className="flex-[1_1_520px]">
      {d.factors.map((f) => {
        const m = Math.max(f.us, f.them, 1)
        const good = f.us >= f.them
        return (
          <div key={f.key} className="grid grid-cols-[52px_minmax(0,1fr)_130px_minmax(0,1fr)_52px] items-center gap-2.5">
            <span className="num text-right font-semibold" style={{ color: good ? GOOD : CRIT }}>
              {f.us}
            </span>
            <div className="flex h-2 justify-end rounded-full bg-line">
              <div className="rounded-full" style={{ width: `${(f.us / m) * 100}%`, background: good ? GOOD : CRIT }} />
            </div>
            <span className="text-center text-[13px] text-ink-2">{f.label}</span>
            <Bar pct={(f.them / m) * 100} color="#6B7783" />
            <span className="num text-ink-3">{f.them}</span>
          </div>
        )
      })}
      <div className="num flex justify-between text-xs text-ink-3">
        <span>{d.us.name}</span>
        <span>{d.them?.name}</span>
      </div>
    </Panel>
  )
}

function ratingColor(r: number | null | undefined) {
  if (r == null) return MUTED
  return r >= 1.1 ? GOOD : r >= 0.95 ? 'var(--ink)' : CRIT
}

function Board({ t, mine }: { t: Report['teams'][number]; mine: boolean }) {
  return (
    <section className="overflow-hidden rounded-lg border border-line bg-surface">
      <div className="flex justify-between border-b border-line px-4 py-3">
        <span className="cond text-lg font-bold" style={{ color: mine ? GOOD : 'var(--ink-2)' }}>
          {t.team.name}
        </span>
        <span className="num text-[13px] text-ink-3">Багийн дундаж rating {t.rating.toFixed(2)}</span>
      </div>
      <div className="overflow-x-auto">
        <table className="grid-table nums">
          <thead>
            <tr>
              <th>Тоглогч</th>
              <th>K–D–A</th>
              <th>+/−</th>
              <th>ADR</th>
              <th>KAST</th>
              <th title="Эхний алалт – эхний үхэл">Opening</th>
              <th title="2+ алалттай раунд">Multi-kill</th>
              <th title="Хожсон / оролдсон">Clutch</th>
              <th title="Utility damage">UD</th>
              <th title="Flash assist">FA</th>
              <th title="Swing / раунд (Review)">Swing</th>
              <th>Rating</th>
            </tr>
          </thead>
          <tbody>
            {t.players.map((p) => {
              const pm = p.kills - p.deaths
              return (
                <tr key={p.steamid}>
                  <td className="name">{p.name}</td>
                  <td>
                    {p.kills}–{p.deaths}–{p.assists}
                  </td>
                  <td style={{ color: pm >= 0 ? GOOD : CRIT }}>{pm > 0 ? `+${pm}` : pm}</td>
                  <td>{p.adr?.toFixed(1) ?? '—'}</td>
                  <td>{p.kast == null ? '—' : `${Math.round(p.kast)}%`}</td>
                  <td>
                    {p.opening_kills}–{p.opening_deaths}
                  </td>
                  <td>{p.multi}</td>
                  <td>
                    {p.clutch_won}/{p.clutch_of}
                  </td>
                  <td>{p.utility_damage}</td>
                  <td>{p.flash_assists}</td>
                  <td>{p.swing_per_round == null ? '—' : `${(100 * p.swing_per_round).toFixed(1)}%`}</td>
                  <td className="font-semibold" style={{ color: ratingColor(p.rating) }}>
                    {p.rating?.toFixed(2) ?? '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function Buys({ d }: { d: Report }) {
  return (
    <Panel title="Худалдан авалтын төрлөөр" className="flex-[1_1_420px]">
      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(130px,100%),1fr))] gap-2.5">
        {d.buys.map((b) => {
          const pct = b.of ? (100 * b.won) / b.of : null
          const color = pct == null ? MUTED : pct >= 60 ? GOOD : pct >= 40 ? WARN : CRIT
          return (
            <div key={b.buy} className="flex flex-col gap-2 rounded-md border border-line-soft bg-surface-2 p-3.5">
              <span className="lbl">{b.label}</span>
              <span className="num text-2xl font-semibold" style={{ color }}>
                {b.won}–{b.of - b.won}
              </span>
              <Bar pct={pct} color={color} h={6} />
              <span className="text-xs text-ink-3">
                {b.of === 0
                  ? 'Ийм раунд байгаагүй'
                  : `${b.won_rounds.length ? `Хожсон: R${b.won_rounds.join(', R')}` : 'Хожоогүй'}`}
              </span>
            </div>
          )
        })}
      </div>
    </Panel>
  )
}

function Turning({ d, teamId }: { d: Report; teamId: number }) {
  return (
    <Panel title="Эргэлтийн раундууд" sub="Хожих магадлал хамгийн их эргэсэн раундууд (Review)" className="flex-[1_1_520px]">
      {!d.reviewed ? (
        <Empty>Энэ Map-ийн Review алга (Tick Data байхгүй).</Empty>
      ) : d.turning.length === 0 ? (
        <Empty>Хожих магадлал 50 пунктээс илүү эргэсэн раунд байгаагүй.</Empty>
      ) : (
        d.turning.map((m) => (
          <Link
            key={m.n}
            to={`${at(teamId, 'replay', d.match_id, d.map_number)}?round=${m.n}`}
            className="plain grid grid-cols-[56px_minmax(0,1fr)_auto] items-center gap-3.5 rounded-md border border-line-soft bg-surface-2 p-3 !text-ink"
          >
            <span className="num text-base font-semibold text-accent">R{m.n}</span>
            <span className="flex flex-col gap-1">
              <span className="text-sm font-semibold">{m.title}</span>
              <span className="text-[13px] text-ink-3">{m.body}</span>
            </span>
            <span className="num text-[13px]" style={{ color: m.won ? GOOD : CRIT }}>
              {Math.round(100 * m.from_wp)}% → {Math.round(100 * m.to_wp)}%
            </span>
          </Link>
        ))
      )}
    </Panel>
  )
}

// v2 screen 04, one Player: his KPIs and seven axes against his team, the Pool
// or a teammate, his Player rating Map by Map, aim, duels, where he kills and
// dies, his guns, what the evidence settles, and Staff's note and goals.
import { Fragment, useState } from 'react'
import { Link, Navigate, useParams, useSearchParams } from 'react-router'
import { $api } from '../../api/client'
import type { components } from '../../api/schema'
import { LoadError } from '../../ui/LoadError'
import { PageSkeleton } from '../../ui/Skeleton'
import { CRIT, GOOD, MUTED, WARN, shortDate, signed } from '../format'
import { useInvalidateV2 } from '../hooks'
import { at, initials, useTeam } from '../team'
import { Bar, Button, Empty, Panel, SideToggle, Toggle } from '../ui'

type Profile = components['schemas']['PlayerProfile']
type Axes = components['schemas']['ProfileAxes']
type Kpis = components['schemas']['ProfileKpis']

const AXES: [keyof Axes, string][] = [
  ['firepower', 'Firepower'],
  ['entry', 'Entry'],
  ['trade', 'Trade'],
  ['utility', 'Utility'],
  ['clutch', 'Clutch'],
  ['survival', 'Survival'],
  ['opening', 'Opening'],
]

/** /v2/t/:team/players: the my team's first Player. */
export function PlayersIndex() {
  const team = useTeam()
  const q = $api.useQuery('get', '/v2/teams/{team_id}/players', { params: { path: { team_id: team.id } } })
  if (q.error) return <LoadError error={q.error} what="Тоглогчид" retry={() => void q.refetch()} />
  if (!q.data) return <PageSkeleton />
  const first = q.data.players[0]
  return first ? <Navigate to={at(team.id, 'players', first.steamid)} replace /> : <Empty>Тоглогч алга.</Empty>
}

export default function PlayerPage() {
  const team = useTeam()
  const { steamid = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const scrims = params.get('scrims') === '1'
  const map = params.get('map') ?? undefined
  const side = (params.get('side') === 'ct' ? 'ct' : 't') as 't' | 'ct'
  const [cmp, setCmp] = useState('team')
  const q = $api.useQuery('get', '/v2/teams/{team_id}/players/{steamid}/profile', {
    params: { path: { team_id: team.id, steamid }, query: { scrims, map, side } },
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
  if (q.error) return <LoadError error={q.error} what="Тоглогч" retry={() => void q.refetch()} />
  if (!q.data) return <PageSkeleton />
  const d = q.data
  const mate = d.mates.find((m) => m.steamid === cmp)
  const cmpLabel = cmp === 'team' ? 'Багийн дундаж' : cmp === 'pool' ? 'Pool-ын медиан' : (mate?.name ?? '')
  const cmpAxes: Axes | null =
    cmp === 'team' ? d.team_axes : cmp === 'pool' ? Object.fromEntries(AXES.map(([k]) => [k, 50])) : (mate?.axes ?? null)
  const cmpKpis: Kpis | null = cmp === 'team' ? d.team_kpis : cmp === 'pool' ? d.pool_kpis : (mate?.kpis ?? null)
  return (
    <>
      <section className="flex flex-wrap items-center justify-between gap-5">
        <div className="flex items-center gap-4.5">
          <div className="cond grid h-[72px] w-[72px] place-items-center rounded-full border-2 border-accent bg-accent-soft text-2xl font-bold text-accent">
            {initials(d.name)}
          </div>
          <div className="flex flex-col gap-1">
            <h1 className="cond m-0 text-[40px] leading-none font-bold">{d.name}</h1>
            <span className="text-[15px] text-ink-3">
              {d.aliases.length > 0 && `${d.aliases.slice(0, 2).join(', ')} · `}
              {d.team.name} · {d.rounds} раунд · {d.maps} газрын зураг
            </span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="lbl">Харьцуулах</span>
          <Toggle
            label="Харьцуулах"
            value={cmp}
            onChange={setCmp}
            options={[['team', 'Багийн дундаж'], ['pool', 'Pool'], ...d.mates.map((m) => [m.steamid, m.name] as const)]}
          />
          <Toggle
            label="Тоглолтын төрөл"
            options={[
              ['official', 'Албан'],
              ['all', '+ Scrim'],
            ]}
            value={scrims ? 'all' : 'official'}
            onChange={(k) => set('scrims', k === 'all' ? '1' : null)}
          />
        </div>
      </section>
      <KpiRow d={d.kpis} cmp={cmpKpis} label={cmpLabel} />
      <section className="flex flex-wrap gap-4">
        <Radar d={d} cmp={cmpAxes} cmpLabel={cmpLabel} />
        <Form d={d} teamId={team.id} />
      </section>
      <section className="flex flex-wrap gap-4">
        <Mechanics d={d} />
        <Duels d={d} />
        <Positions d={d} map={d.positions.map} side={side} onMap={(m) => set('map', m)} onSide={(s) => set('side', s)} />
      </section>
      <section className="flex flex-wrap gap-4">
        <Weapons d={d} />
        <Summary d={d} />
      </section>
    </>
  )
}

const KPI_DEF: [keyof Kpis, string, (v: number) => string, number][] = [
  ['rating', 'Rating', (v) => v.toFixed(2), 2],
  ['adr', 'ADR', (v) => v.toFixed(1), 1],
  ['kast', 'KAST', (v) => `${Math.round(v)}%`, 0],
  ['opening_pct', 'Opening хожил', (v) => `${Math.round(v)}%`, 0],
  ['hs', 'HS%', (v) => `${Math.round(v)}%`, 0],
  ['traded_pct', 'Trade-д үхсэн', (v) => `${Math.round(v)}%`, 0],
]

function KpiRow({ d, cmp, label }: { d: Kpis; cmp: Kpis | null; label: string }) {
  return (
    <section className="grid grid-cols-[repeat(auto-fit,minmax(min(160px,100%),1fr))] gap-3">
      {KPI_DEF.map(([key, name, fmt, digits]) => {
        const v = d[key]
        const c = cmp?.[key]
        const delta = v != null && c != null ? v - c : null
        return (
          <div key={key} className="flex flex-col gap-1.5 rounded-lg border border-line bg-surface p-4">
            <span className="lbl">{name}</span>
            <span className="num text-[28px] font-semibold">{v == null ? '—' : fmt(v)}</span>
            <span className="num text-xs" style={{ color: delta == null ? MUTED : delta > 0 ? GOOD : delta < 0 ? CRIT : MUTED }}>
              {delta == null ? '—' : `${signed(delta, digits)} ${label}-аас`}
            </span>
          </div>
        )
      })}
    </section>
  )
}

function Radar({ d, cmp, cmpLabel }: { d: Profile; cmp: Axes | null; cmpLabel: string }) {
  const R = 110
  const pt = (i: number, v: number) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / AXES.length
    return [Math.cos(a) * ((R * v) / 100), Math.sin(a) * ((R * v) / 100)]
  }
  const poly = (vals: (number | null | undefined)[]) => vals.map((v, i) => pt(i, v ?? 0).map((x) => x.toFixed(1)).join(',')).join(' ')
  const ring = (v: number) => poly(AXES.map(() => v))
  const mine = AXES.map(([k]) => d.axes[k])
  return (
    <Panel
      title="Дүрийн хээ"
      sub={`${d.pool_players} тоглогчийн дундах percentile (100 = хамгийн сайн)`}
      className="flex-[1_1_420px]"
      right={
        <div className="flex gap-3.5 text-[13px] text-ink-3">
          <span className="flex items-center gap-1.5">
            <span className="h-[3px] w-3.5 bg-accent" />
            {d.name}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3.5 border-t-2 border-dashed border-ink-3" />
            {cmpLabel}
          </span>
        </div>
      }
    >
      <svg viewBox="-170 -150 340 300" width="100%" height="340" role="img"
        aria-label={`Дүрийн хээ: ${AXES.map(([k, l]) => `${l} ${d.axes[k] ?? '—'}`).join(', ')}`}>
        <polygon points={ring(33)} fill="none" stroke="var(--line-soft)" />
        <polygon points={ring(66)} fill="none" stroke="var(--line-soft)" />
        <polygon points={ring(100)} fill="none" stroke="var(--line-strong)" />
        {cmp && <polygon points={poly(AXES.map(([k]) => cmp[k]))} fill="none" stroke="var(--ink-3)" strokeWidth={2} strokeDasharray="5 4" />}
        <polygon points={poly(mine)} fill="var(--accent)" fillOpacity={0.18} stroke="var(--accent)" strokeWidth={2.5} />
        <g fontFamily="IBM Plex Sans Condensed, sans-serif" fontSize={13} fontWeight={600} fill="var(--ink-2)" textAnchor="middle">
          {AXES.map(([k, label], i) => {
            const [x, y] = pt(i, 128)
            return (
              <text key={k} x={x} y={y + 4}>
                {label} {d.axes[k] ?? '—'}
              </text>
            )
          })}
        </g>
      </svg>
    </Panel>
  )
}

function Form({ d, teamId }: { d: Profile; teamId: number }) {
  const f = d.form
  return (
    <Panel
      title={`Сүүлийн ${f.maps.length} газрын зураг · Rating`}
      className="flex-[999_1_560px]"
      right={<span className="num text-[13px] text-ink-3">σ = {f.sigma?.toFixed(2) ?? '—'}</span>}
    >
      {f.maps.length === 0 ? (
        <Empty />
      ) : (
        <>
          <div className="relative grid h-[200px] items-end gap-1 border-b border-line-strong" style={{ gridTemplateColumns: `repeat(${f.maps.length}, minmax(0, 1fr))` }}>
            <div className="absolute inset-x-0 border-t border-dashed border-[#3A4652]" style={{ bottom: `${(1 / 2) * 100}%` }} />
            {f.maps.map((m) => (
              <Link
                key={`${m.match_id}-${m.map_number}`}
                to={at(teamId, 'matches', m.match_id, 'm', m.map_number)}
                title={`${shortDate(m.played_at)} ${m.map.replace('de_', '')} vs ${m.opponent}: ${m.rating.toFixed(2)}${m.scrim ? ' (scrim)' : ''}`}
                className="block rounded-t-[3px]"
                style={{
                  height: `${Math.min(100, (m.rating / 2) * 100)}%`,
                  background: m.rating >= 1 ? GOOD : CRIT,
                  opacity: m.scrim ? 0.5 : 1,
                }}
              />
            ))}
          </div>
          <div className="num flex justify-between text-xs text-ink-3">
            <span>{shortDate(f.maps[0].played_at)}</span>
            <span>тасархай шугам = 1.00 · бүдэг = scrim</span>
            <span>{shortDate(f.maps.at(-1)?.played_at)}</span>
          </div>
        </>
      )}
      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(150px,100%),1fr))] gap-2.5 border-t border-line pt-3.5">
        <Split label="Албан" v={f.official} />
        <Split label="Scrim" v={f.scrim} />
        <Split label="T тал" v={f.t} color="var(--t)" />
        <Split label="CT тал" v={f.ct} color="var(--ct)" />
      </div>
    </Panel>
  )
}

function Split({ label, v, color }: { label: string; v: number | null | undefined; color?: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="lbl">{label}</span>
      <span className="num text-xl font-semibold" style={{ color }}>
        {v == null ? '—' : v.toFixed(2)}
      </span>
    </div>
  )
}

const MECH: [string, string, string, (v: number) => string][] = [
  ['ttd_ms', 'Анх харсанаас damage хүртэл', 'Медиан хугацаа · бага байх тусам сайн', (v) => `${Math.round(v)} мс`],
  ['xhair_deg', 'Crosshair-ийн зөрүү', 'Анх харах үеийн толгойноос өнцөг · бага байх тусам сайн', (v) => `${v.toFixed(1)}°`],
  ['counter_strafe_pct', 'Counter-strafe', 'Зогсож буудсан сумны хувь', (v) => `${v.toFixed(0)}%`],
  ['first_hit_pct', 'Эхний сум оносон', 'Engagement-ийн эхний сум', (v) => `${v.toFixed(0)}%`],
]

function Mechanics({ d }: { d: Profile }) {
  const m = d.mechanics
  return (
    <Panel title="Механик дохио" sub="Харах өнцөг, хурд, Sighting-аас тооцоолсон" className="flex-[1_1_420px]">
      {!m ? (
        <Empty>Sighting-тай Map дээр engagement алга.</Empty>
      ) : !m.enough ? (
        <Empty>{m.engagements} engagement: 100-аас доош тул percentile хэлэхгүй.</Empty>
      ) : (
        MECH.map(([key, label, note, fmt]) => {
          const v = (m as unknown as Record<string, number | null>)[key]
          const rank = m.rank[key]
          const med = m.medians[key]
          const color = rank == null ? MUTED : rank >= 60 ? GOOD : rank >= 40 ? WARN : CRIT
          return (
            <div key={key} className="flex flex-col gap-1.5">
              <div className="flex justify-between gap-2.5 text-sm">
                <span>{label}</span>
                <span className="num font-semibold" style={{ color }}>
                  {v == null ? '—' : fmt(v)}
                </span>
              </div>
              <div className="relative">
                <Bar pct={rank} color={color} />
                <div className="absolute -top-1 -bottom-1 w-0.5 bg-ink" style={{ left: '50%' }} />
              </div>
              <span className="text-xs text-ink-3">
                {note} · {rank ?? '—'}-р percentile · медиан {med == null ? '—' : fmt(med)}
              </span>
            </div>
          )
        })
      )}
      {m?.enough && <span className="text-xs text-ink-3">{m.engagements} engagement, {m.players} тоглогчтой харьцуулсан. Цагаан зураас = медиан.</span>}
    </Panel>
  )
}

const DIST: [string, string][] = [
  ['near', 'Ойр <10м'],
  ['mid', 'Дунд'],
  ['far', 'Хол >25м'],
]
const PHASE: [string, string][] = [
  ['early', '0–30с'],
  ['mid', '30–60с'],
  ['late', '60с+'],
]

function Duels({ d }: { d: Profile }) {
  const cell = (dist: string, phase: string) => d.duels.find((c) => c.distance === dist && c.phase === phase)
  return (
    <Panel title="Duel хожил · зай × үе шат" sub="Нүд бүрт: хожлын % (duel тоо)" className="flex-[1_1_380px]">
      <div className="grid grid-cols-[90px_repeat(3,minmax(0,1fr))] gap-1">
        <span />
        {PHASE.map(([k, l]) => (
          <span key={k} className="lbl text-center">
            {l}
          </span>
        ))}
        {DIST.map(([dk, dl]) => (
          <Fragment key={dk}>
            <span className="cond self-center text-[13px] text-ink-2">
              {dl}
            </span>
            {PHASE.map(([pk]) => {
              const c = cell(dk, pk)
              const n = c ? c.won + c.lost : 0
              const p = n ? (100 * (c?.won ?? 0)) / n : null
              const bg = p == null ? 'var(--surface-2)' : p >= 60 ? '#1F4A36' : p >= 50 ? '#1C3329' : p >= 45 ? '#3A3220' : '#4A2523'
              return (
                <div key={`${dk}-${pk}`} className="flex h-16 flex-col items-center justify-center gap-0.5 rounded" style={{ background: bg }}>
                  <span className="num text-lg font-semibold">{p == null ? '—' : `${Math.round(p)}%`}</span>
                  <span className="num text-[11px] opacity-85">({n})</span>
                </div>
              )
            })}
          </Fragment>
        ))}
      </div>
    </Panel>
  )
}

function Positions(props: { d: Profile; map: string | null; side: 't' | 'ct'; onMap: (m: string) => void; onSide: (s: 't' | 'ct') => void }) {
  const p = props.d.positions
  return (
    <Panel
      title="Алалт / үхлийн байрлал"
      className="flex-[1_1_380px]"
      right={<SideToggle value={props.side} onChange={props.onSide} h={36} />}
    >
      <div className="flex flex-wrap gap-1.5">
        {p.maps.map((m) => (
          <button
            key={m.map}
            type="button"
            onClick={() => props.onMap(m.map)}
            aria-pressed={m.map === p.map}
            className={`h-9 rounded-md border px-2.5 text-[13px] ${m.map === p.map ? 'border-accent text-accent' : 'border-line-strong text-ink-2'}`}
          >
            {m.map.replace('de_', '')} <span className="num text-ink-3">{m.n}</span>
          </button>
        ))}
      </div>
      <div className="relative aspect-square w-full overflow-hidden rounded-md bg-surface-2">
        {p.url && <img src={p.url} alt="" className="absolute inset-0 h-full w-full opacity-60" />}
        {p.kills.map(([x, y], i) => (
          <span key={`k${i}`} className="absolute h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-[#0A0D10]" style={{ left: `${x * 100}%`, top: `${y * 100}%`, background: GOOD }} />
        ))}
        {p.deaths.map(([x, y], i) => (
          <span key={`d${i}`} className="absolute h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-[#0A0D10]" style={{ left: `${x * 100}%`, top: `${y * 100}%`, background: CRIT }} />
        ))}
      </div>
      <div className="flex gap-4 text-[13px] text-ink-3">
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: GOOD }} />
          Алалт {p.kills.length}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: CRIT }} />
          Үхэл {p.deaths.length}
        </span>
      </div>
    </Panel>
  )
}

function Weapons({ d }: { d: Profile }) {
  return (
    <Panel title="Зэвсэг" className="flex-[999_1_560px]">
      {d.weapons.length === 0 ? (
        <Empty />
      ) : (
        <div className="overflow-x-auto">
          <table className="grid-table nums">
            <thead>
              <tr>
                <th>Зэвсэг</th>
                <th>Алалт</th>
                <th>Хувь</th>
                <th>HS%</th>
                <th>Дундаж зай</th>
                <th>Damage / раунд</th>
              </tr>
            </thead>
            <tbody>
              {d.weapons.map((w) => (
                <tr key={w.weapon}>
                  <td className="name">{w.weapon}</td>
                  <td>{w.kills}</td>
                  <td>{w.share}%</td>
                  <td>{w.hs == null ? '—' : `${Math.round(w.hs)}%`}</td>
                  <td>{w.distance == null ? '—' : `${w.distance} м`}</td>
                  <td>{w.dpr ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  )
}

function Summary({ d }: { d: Profile }) {
  const invalidate = useInvalidateV2()
  const [text, setText] = useState<string | null>(null)
  const save = $api.useMutation('put', '/v2/players/{steamid}/note', { onSuccess: () => void invalidate() })
  const value = text ?? d.note?.text ?? ''
  const good = d.lines.filter((l) => l.good)
  const bad = d.lines.filter((l) => !l.good)
  return (
    <Panel title="Дүгнэлт" className="flex-[1_1_360px]">
      <div className="flex flex-col gap-2">
        <span className="lbl !text-good">Давуу тал</span>
        {good.length ? good.map((l) => <span key={l.text} className="text-sm leading-normal">{l.text}</span>) : <Empty>Нотлогдсон давуу тал алга.</Empty>}
      </div>
      <div className="flex flex-col gap-2">
        <span className="lbl !text-crit">Сайжруулах</span>
        {bad.length ? bad.map((l) => <span key={l.text} className="text-sm leading-normal">{l.text}</span>) : <Empty>Нотлогдсон сул тал алга.</Empty>}
      </div>
      <label className="flex flex-col gap-1.5">
        <span className="lbl">Дасгалжуулагчийн тэмдэглэл</span>
        <textarea
          rows={3}
          value={value}
          maxLength={4000}
          onChange={(e) => setText(e.target.value)}
          placeholder="Жишээ нь: pop flash-ийг хүлээж peek хийх…"
          className="resize-y rounded-md border border-line-strong bg-surface-2 p-2.5 text-sm text-ink"
        />
      </label>
      <div className="flex items-center gap-3">
        <Button onClick={() => save.mutate({ params: { path: { steamid: d.steamid } }, body: { text: value } })} disabled={save.isPending || text === null}>
          Тэмдэглэл хадгалах
        </Button>
        {d.note?.updated_at && <span className="text-xs text-ink-3">{shortDate(d.note.updated_at)} шинэчилсэн</span>}
      </div>
      <Goals steamid={d.steamid} />
    </Panel>
  )
}

function Goals({ steamid }: { steamid: string }) {
  const [open, setOpen] = useState(false)
  const plan = $api.useQuery('get', '/players/{steamid}/goals', { params: { path: { steamid } } }, { enabled: open })
  const create = $api.useMutation('post', '/players/{steamid}/goals', { onSuccess: () => void plan.refetch() })
  if (!open)
    return (
      <button type="button" onClick={() => setOpen(true)} className="h-11 rounded-md bg-accent text-sm font-semibold text-[#0A0D10]">
        Бэлтгэлийн даалгавар үүсгэх
      </button>
    )
  if (!plan.data) return <Empty>Уншиж байна…</Empty>
  const active = plan.data.goals.filter((g) => g.status === 'active')
  return (
    <div className="flex flex-col gap-2 border-t border-line pt-3">
      <span className="lbl">Development plan</span>
      {active.map((g) => (
        <span key={g.id} className="text-sm">
          {g.label}: {g.baseline ?? '—'} → <b>{g.target}</b> ({g.due_on} хүртэл)
        </span>
      ))}
      {plan.data.suggestions.length === 0 ? (
        <Empty>Санал болгох зорилт алга.</Empty>
      ) : (
        plan.data.suggestions.slice(0, 3).map((s) => (
          <div key={s.kpi} className="flex items-center justify-between gap-2 rounded-md border border-line-soft bg-surface-2 p-2.5 text-sm">
            <span>
              {s.label}: {s.baseline} → {s.target}
            </span>
            <button
              type="button"
              disabled={create.isPending || active.some((g) => g.kpi === s.kpi)}
              onClick={() => create.mutate({ params: { path: { steamid } }, body: { kpi: s.kpi, target: s.target, notes: '' } })}
              className="text-ct underline disabled:text-ink-3 disabled:no-underline"
            >
              {active.some((g) => g.kpi === s.kpi) ? 'Нэмсэн' : 'Нэмэх'}
            </button>
          </div>
        ))
      )}
    </div>
  )
}

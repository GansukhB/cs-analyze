// v2 screen 06, utility: the my team's KPIs over a window, how soon a fight
// follows our flashes, how tightly our repeated throws land, and each Player's
// grenades.
import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { $api } from '../../api/client'
import type { components } from '../../api/schema'
import { LoadError } from '../../ui/LoadError'
import { PageSkeleton } from '../../ui/Skeleton'
import { CRIT, GOOD, MUTED, WARN, tone } from '../format'
import { useTeam } from '../team'
import { Bar, Box, Empty, Kpi, PageHead, Panel, Tag, Toggle } from '../ui'

type Report = components['schemas']['UtilityReport']

const PERIODS = [
  ['30', '30 хоног'],
  ['90', '90 хоног'],
  ['180', '180 хоног'],
  ['all', 'Бүгд'],
] as const
const KIND: Record<string, [string, string]> = {
  smoke: ['SMOKE', 'var(--ink-2)'],
  flash: ['FLASH', 'var(--ink)'],
  inferno: ['MOLOTOV', 'var(--t)'],
  he: ['HE', 'var(--crit)'],
}

export default function UtilityPage() {
  const team = useTeam()
  const [params, setParams] = useSearchParams()
  const period = (PERIODS.find(([k]) => k === params.get('period'))?.[0] ?? '30') as (typeof PERIODS)[number][0]
  const scrims = params.get('scrims') === '1'
  const map = params.get('map') ?? undefined
  const q = $api.useQuery('get', '/v2/teams/{team_id}/utility', {
    params: { path: { team_id: team.id }, query: { period, scrims, map } },
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
  if (q.error) return <LoadError error={q.error} what="Utility" retry={() => void q.refetch()} />
  if (!q.data) return <PageSkeleton />
  const d = q.data
  const k = d.kpis
  return (
    <>
      <PageHead
        label="Grenade · Smoke · Flash · Molotov · HE"
        title="Utility шинжилгээ"
        sub={`${PERIODS.find(([p]) => p === period)?.[1]} · ${d.maps} Map · ${d.rounds} раунд · ${d.throws.toLocaleString('mn-MN')} шидэлт`}
        actions={
          <>
            <Toggle label="Хугацаа" options={PERIODS} value={period} onChange={(p) => set('period', p === '30' ? null : p)} />
            <Toggle
              label="Тоглолтын төрөл"
              options={[
                ['official', 'Албан'],
                ['all', '+ Scrim'],
              ]}
              value={scrims ? 'all' : 'official'}
              onChange={(v) => set('scrims', v === 'all' ? '1' : null)}
            />
          </>
        }
      />
      <section className="grid grid-cols-[repeat(auto-fit,minmax(min(170px,100%),1fr))] gap-3">
        <Kpi label="Utility damage / раунд" value={k.damage_per_round ?? '—'} sub="Molotov + HE" />
        <Kpi label="Flash assist / Map" value={k.assists_per_map ?? '—'} />
        <Kpi label="Сохорсон дайсан / flash" value={k.blinded_per_flash ?? '—'} color={tone(k.blinded_per_flash == null ? null : k.blinded_per_flash * 100, 80, 50)} sub="1с-ээс удаан сохорсон" />
        <Kpi label="Багаа сохорсон flash" value={k.team_flash_pct == null ? '—' : `${k.team_flash_pct}%`} color={k.team_flash_pct == null ? MUTED : k.team_flash_pct > 20 ? CRIT : k.team_flash_pct > 12 ? WARN : GOOD} sub="Багийн гишүүнийг сохорсон flash-ийн хувь" />
        <Kpi label="Execute utility цаг" value={k.execute_seconds == null ? '—' : `${k.execute_seconds}с`} sub="Plant-аас 15с өмнөх smoke/molotov: эхнийхээс сүүлчийнх хүртэл" />
        <Kpi label="Ашиглаагүй үхсэн" value={k.unused_per24 == null ? '—' : `${k.unused_per24}/24`} color={k.unused_per24 == null ? MUTED : k.unused_per24 > 2 ? CRIT : WARN} sub="Review-ийн Finding, 24 раундад (Loadout-тай Map)" />
      </section>
      <section className="flex flex-wrap gap-4">
        <Sync d={d} />
        <Lineups d={d} onMap={(m) => set('map', m)} />
      </section>
      <PlayersTable d={d} />
    </>
  )
}

function Sync({ d }: { d: Report }) {
  const s = d.sync
  const max = Math.max(1, ...s.bins.map((b) => b.n))
  const quick = s.bins.filter((b) => (b.to ?? 99) <= 0.4)
  const slow = s.bins.filter((b) => b.from >= 1.0)
  const sum = (bs: typeof s.bins) => bs.reduce((a, b) => [a[0] + b.n, a[1] + b.won], [0, 0])
  const [qn, qw] = sum(quick)
  const [sn, sw] = sum(slow)
  return (
    <Panel
      title="Flash → тулаан"
      sub={`Бидний flash дэлбэрснээс 3с дотор бидний оролцсон эхний алалт хүртэлх хугацаа · ${s.fights} тулаан / ${s.flashes} flash`}
      className="flex-[1_1_520px]"
    >
      {s.fights === 0 ? (
        <Empty>Flash-ийн дараах тулаан алга.</Empty>
      ) : (
        <>
          <div className="relative grid h-[180px] items-end gap-1.5 border-b border-line-strong" style={{ gridTemplateColumns: `repeat(${s.bins.length}, minmax(0, 1fr))` }}>
            {s.bins.map((b, i) => {
              const color = i < 2 ? GOOD : i < 4 ? WARN : CRIT
              return (
                <div key={b.from} title={`${b.n} тулаан, ${b.won} нь бидний алалт`} className="relative rounded-t-[3px]" style={{ height: `${(100 * b.n) / max}%`, background: color }}>
                  <span className="num absolute -top-5 right-0 left-0 text-center text-xs text-ink-2">
                    {b.n ? `${Math.round((100 * b.won) / b.n)}%` : ''}
                  </span>
                </div>
              )
            })}
          </div>
          <div className="num grid gap-1.5 text-[11px] text-ink-3" style={{ gridTemplateColumns: `repeat(${s.bins.length}, minmax(0, 1fr))` }}>
            {s.bins.map((b) => (
              <span key={b.from} className="text-center">
                {b.to == null ? `>${b.from}с` : `${b.from}–${b.to}`}
              </span>
            ))}
          </div>
          <span className="text-xs text-ink-3">Баганын дээрх хувь = тэр тулааныг бид хожсон хувь</span>
          <div className="flex flex-wrap gap-5 border-t border-line pt-3">
            <Small label="<0.4с дотор" v={`${Math.round((100 * qn) / s.fights)}%`} color={GOOD} />
            <Small label="Тэр үеийн хожил" v={qn ? `${Math.round((100 * qw) / qn)}%` : '—'} />
            <Small label=">1с хоцорсон үед хожил" v={sn ? `${Math.round((100 * sw) / sn)}%` : '—'} color={CRIT} />
            <Small label="Нийт хожил" v={`${Math.round((100 * s.won) / s.fights)}%`} />
          </div>
        </>
      )}
    </Panel>
  )
}

function Small({ label, v, color }: { label: string; v: string; color?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="lbl">{label}</span>
      <span className="num text-[22px] font-semibold" style={{ color }}>
        {v}
      </span>
    </div>
  )
}

function Lineups({ d, onMap }: { d: Report; onMap: (m: string) => void }) {
  const [pick, setPick] = useState(0)
  const l = d.lineups[Math.min(pick, d.lineups.length - 1)]
  const scale = 46 / (l?.radius ?? 128)
  return (
    <Panel
      title="Lineup нарийвчлал"
      sub="Нэг байрлал (48u), чиглэлээс (20°) 5+ удаа шидсэн · медиан буух цэгээс 128u дотор буусан хувь"
      className="flex-[1_1_420px]"
      right={
        <div className="flex flex-wrap gap-1.5">
          {d.map_choices.map((m) => (
            <button key={m.map} type="button" aria-pressed={m.map === d.map} onClick={() => onMap(m.map)} className={`h-9 rounded-md border px-2.5 text-[13px] ${m.map === d.map ? 'border-accent text-accent' : 'border-line-strong text-ink-2'}`}>
              {m.label}
            </button>
          ))}
        </div>
      }
    >
      {!l ? (
        <Empty>Энэ хугацаанд 5+ давтсан шидэлт алга — хугацааг уртасгана уу.</Empty>
      ) : (
        <>
          <div className="relative aspect-[4/3] w-full overflow-hidden rounded-md bg-surface-2">
            <svg viewBox="0 0 400 300" width="100%" height="100%" className="absolute inset-0" role="img" aria-label={`${l.throws} шидэлтийн ${l.accuracy}% нь зорилтот тойрогт`}>
              <text x="12" y="24" fontFamily="IBM Plex Sans Condensed, sans-serif" fontSize="13" fontWeight="600" fill="var(--ink-3)" letterSpacing="1.5">
                {(l.from_place || '?').toUpperCase()} → {(l.to_place || '?').toUpperCase()}
              </text>
              <circle cx="200" cy="150" r={l.radius * scale} fill="none" stroke={GOOD} strokeWidth="2" strokeDasharray="5 4" />
              <circle cx="200" cy="150" r="3" fill={GOOD} />
              {l.scatter.map(([dx, dy], i) => {
                const inside = Math.hypot(dx, dy) <= l.radius
                return <circle key={i} cx={200 + dx * scale} cy={150 - dy * scale} r="5" fill={inside ? GOOD : CRIT} opacity="0.9" />
              })}
            </svg>
          </div>
          <div className="flex flex-wrap justify-between gap-2.5 text-[13px] text-ink-3">
            <span>
              <span style={{ color: GOOD }}>●</span> Зорилтод {l.accuracy}%
            </span>
            <span>
              <span style={{ color: CRIT }}>●</span> Гадна {100 - l.accuracy}%{l.throwers.length > 0 && ` · ${l.throwers.join(', ')}`}
            </span>
          </div>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(220px,100%),1fr))] gap-2.5">
            {d.lineups.map((x, i) => {
              const [word, color] = KIND[x.type] ?? [x.type, MUTED]
              const c = tone(x.accuracy, 85, 70)
              return (
                <button key={i} type="button" onClick={() => setPick(i)} className={`text-left ${i === pick ? 'ring-1 ring-accent' : ''} rounded-md`}>
                  <Box>
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="text-[15px] font-semibold">
                        {x.from_place || '?'} → {x.to_place || '?'}
                      </span>
                      <Tag color={color}>{word}</Tag>
                    </div>
                    <div className="flex items-center gap-2.5">
                      <Bar pct={x.accuracy} color={c} className="flex-1" />
                      <span className="num text-sm font-semibold" style={{ color: c }}>
                        {x.accuracy}%
                      </span>
                    </div>
                    <span className="text-xs text-ink-3">
                      {x.throws} шидэлт · {x.side.toUpperCase()}
                    </span>
                  </Box>
                </button>
              )
            })}
          </div>
        </>
      )}
    </Panel>
  )
}

function PlayersTable({ d }: { d: Report }) {
  const maxUnused = Math.max(1, ...d.players.map((p) => p.unused))
  return (
    <Panel title="Тоглогч бүрээр">
      <div className="overflow-x-auto">
        <table className="grid-table nums">
          <thead>
            <tr>
              <th>Тоглогч</th>
              <th>Шидэлт / раунд</th>
              <th>Smoke</th>
              <th>Flash</th>
              <th>Molotov</th>
              <th>HE</th>
              <th>Utility damage</th>
              <th>Flash assist</th>
              <th>Сохорсон дайсан</th>
              <th>Багаа сохорсон</th>
              <th>Ашиглаагүй үхсэн</th>
            </tr>
          </thead>
          <tbody>
            {d.players.map((p) => (
              <tr key={p.steamid}>
                <td className="name">{p.name}</td>
                <td>{p.per_round ?? '—'}</td>
                <td>{p.smokes}</td>
                <td>{p.flashes_thrown}</td>
                <td>{p.molotovs}</td>
                <td>{p.hes}</td>
                <td>{p.utility_damage}</td>
                <td>{p.flash_assists}</td>
                <td>{p.enemies_blinded}</td>
                <td style={{ color: p.team_flash_pct == null ? MUTED : p.team_flash_pct > 20 ? CRIT : 'var(--ink)' }}>{p.team_flash_pct == null ? '—' : `${p.team_flash_pct}%`}</td>
                <td>
                  <div className="flex items-center justify-end gap-2">
                    <Bar pct={(100 * p.unused) / maxUnused} color={p.unused > 3 ? CRIT : p.unused > 1 ? WARN : GOOD} h={6} className="w-[70px]" />
                    <span>{p.loadout_rounds ? p.unused : '—'}</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="m-0 text-[13px] text-ink-3">
        «Ашиглаагүй үхсэн» = Review-ийн Finding: алдсан раундад $700+ utility-тай үхсэн тоо (Loadout-тай Map л). «Багаа сохорсон» = багийн гишүүнийг 1с+ сохорсон flash-ийн хувь.
      </p>
    </Panel>
  )
}

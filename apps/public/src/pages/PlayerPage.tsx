import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { $api } from '../api/client'
import type { components } from '../api/schema'
import { day } from '../jobs/format'
import { swingRateText } from '../review/format'

type Page = components['schemas']['PlayerPage']
type FormRow = components['schemas']['PlayerFormRow']

const SIDE = { ct: 'CT', t: 'T' } as const
const KIND = {
  key_play: 'Шийдвэрлэсэн үйлдэл',
  mistake: 'Алдаа',
  missed_chance: 'Алдсан боломж',
  utility: 'Utility',
} as Record<string, string>
const ROLLING = 5

const mapName = (m: string) => m.replace(/^de_/, '').replace(/^\w/, (c) => c.toUpperCase())
const num = (v: number | null | undefined, digits = 1, unit = '') => (v == null ? '—' : `${v.toFixed(digits)}${unit}`)

// One Player's page (docs/plans PL-2): his form Match Map by Match Map, his
// numbers by Map and Side, the Findings he gets most against every Player's,
// where he stands 20 s in, and his guns. Every number is from parsed demos.
export default function PlayerPage() {
  const { steamid = '' } = useParams()
  const page = $api.useQuery('get', '/players/{steamid}', { params: { path: { steamid } } })
  if (page.isPending) return <p className="text-ink-3">Уншиж байна…</p>
  if (page.error || !page.data) return <p className="text-ink-3">Тоглогч олдсонгүй.</p>
  const p = page.data
  return (
    <div className="space-y-8">
      <Header p={p} />
      <Tiles p={p} />
      <Form rows={p.form} />
      <Maps p={p} />
      <Findings p={p} />
      <div className="grid gap-6 md:grid-cols-2">
        <Spots p={p} />
        <Weapons p={p} />
      </div>
    </div>
  )
}

function Header({ p }: { p: Page }) {
  return (
    <div className="space-y-2">
      <h1 className="text-2xl font-semibold text-ink">{p.player.name}</h1>
      {p.player.aliases.length > 0 && (
        <p className="text-sm text-ink-3">Өөр нэрс: {p.player.aliases.join(', ')}</p>
      )}
      <p className="flex flex-wrap gap-2 text-sm">
        {p.teams.map((t) => (
          <Link
            key={t.team_id}
            to={`/teams/${t.team_id}`}
            className="rounded-md border border-line bg-surface px-3 py-1 text-ink hover:border-ct"
          >
            {t.name}
            <span className="ml-2 font-mono text-xs text-ink-3">
              {t.maps} map · {t.first ? day(t.first) : '?'} – {t.last ? day(t.last) : '?'}
            </span>
          </Link>
        ))}
      </p>
    </div>
  )
}

function Tiles({ p }: { p: Page }) {
  const t = p.totals
  const tiles: [string, string][] = [
    ['Map', String(t.maps)],
    ['Раунд', String(t.rounds)],
    ['Swing / раунд', t.swing_per_round == null ? '—' : swingRateText(t.swing_per_round)],
    ['ADR', num(t.adr)],
    ['KAST', num(t.kast_pct, 1, '%')],
    ['Opening хожил', `${num(t.opening_win_pct, 0, '%')} · ${t.opening_attempts}`],
    ['Trade хийгдсэн үхэл', num(t.traded_death_pct, 0, '%')],
  ]
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
      {tiles.map(([label, value]) => (
        <div key={label} className="rounded-lg border border-line bg-surface px-3 py-2">
          <dt className="text-xs text-ink-3">{label}</dt>
          <dd className="font-mono text-lg text-ink">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

/** Swing per Round on each Match Map (bars from zero) and its 5-map rolling mean (line). */
function Form({ rows }: { rows: FormRow[] }) {
  const [hover, setHover] = useState<number | null>(null)
  const points = rows.map((r, i) => ({ ...r, i, v: r.swing_per_round }))
  const known = points.filter((r) => r.v != null) as (FormRow & { i: number; v: number })[]
  if (known.length < 2) {
    return (
      <section className="space-y-2">
        <h2 className="font-medium text-ink">Форм</h2>
        <p className="text-sm text-ink-3">Review-тэй Match Map хоёроос цөөн байна.</p>
      </section>
    )
  }
  const rolling = known.map((r, k) => {
    const window = known.slice(Math.max(0, k - ROLLING + 1), k + 1)
    return { i: r.i, v: window.reduce((s, w) => s + w.v, 0) / window.length }
  })
  const W = 720
  const H = 200
  const pad = { l: 44, r: 12, t: 12, b: 24 }
  const extent = Math.max(0.05, ...known.map((r) => Math.abs(r.v)))
  const x = (i: number) => pad.l + ((i + 0.5) / points.length) * (W - pad.l - pad.r)
  const y = (v: number) => pad.t + ((extent - v) / (2 * extent)) * (H - pad.t - pad.b)
  const bar = Math.max(2, ((W - pad.l - pad.r) / points.length) * 0.6)
  const line = rolling.map((r, k) => `${k ? 'L' : 'M'}${x(r.i).toFixed(1)},${y(r.v).toFixed(1)}`).join(' ')
  const shown = hover == null ? null : points[hover]
  return (
    <section className="space-y-2">
      <h2 className="font-medium text-ink">Форм: map бүрийн Swing / раунд</h2>
      <div className="flex flex-wrap gap-4 text-xs text-ink-2">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-2 rounded-sm" style={{ background: 'var(--mark-mine)' }} />
          Match Map бүр
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4" style={{ background: 'var(--ink)' }} />
          Сүүлийн {ROLLING} map-ын дундаж
        </span>
      </div>
      <div className="relative rounded-xl border border-line bg-surface p-2">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Map бүрийн Swing / раунд">
          {[extent, extent / 2, 0, -extent / 2, -extent].map((v) => (
            <g key={v}>
              <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke="var(--line)" strokeWidth={v === 0 ? 1.5 : 1} />
              <text x={pad.l - 6} y={y(v) + 4} textAnchor="end" fontSize="10" fill="var(--ink-3)">
                {v === 0 ? '0' : swingRateText(v)}
              </text>
            </g>
          ))}
          {known.map((r) => {
            const top = Math.min(y(r.v), y(0))
            return (
              <rect
                key={r.i}
                x={x(r.i) - bar / 2}
                y={top}
                width={bar}
                height={Math.max(1, Math.abs(y(r.v) - y(0)))}
                rx={2}
                fill="var(--mark-mine)"
                opacity={hover == null || hover === r.i ? 1 : 0.45}
              />
            )
          })}
          <path d={line} fill="none" stroke="var(--ink)" strokeWidth={2} strokeLinejoin="round" />
          {points.map((r) => (
            <rect
              key={`hit-${r.i}`}
              x={x(r.i) - (W - pad.l - pad.r) / points.length / 2}
              y={pad.t}
              width={(W - pad.l - pad.r) / points.length}
              height={H - pad.t - pad.b}
              fill="transparent"
              onMouseEnter={() => setHover(r.i)}
              onMouseLeave={() => setHover(null)}
            />
          ))}
        </svg>
        {shown && (
          <div className="pointer-events-none absolute top-2 right-2 rounded-md border border-line bg-raised px-3 py-2 text-xs text-ink-2">
            <b className="text-ink">
              {mapName(shown.map)} · {shown.opponent}
            </b>
            <div>{shown.played_at ? day(shown.played_at) : ''}</div>
            <div>
              Swing / раунд <b className="font-mono text-ink">{shown.v == null ? '—' : swingRateText(shown.v)}</b> · {shown.kills}
              –{shown.deaths} · ADR {num(shown.adr)}
            </div>
          </div>
        )}
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer text-ink-3">Хүснэгтээр</summary>
        <div className="overflow-x-auto">
          <table className="mt-2 w-full text-left text-sm">
            <thead className="text-xs text-ink-3">
              <tr>
                <th className="py-1 pr-3 font-normal">Огноо</th>
                <th className="pr-3 font-normal">Map</th>
                <th className="pr-3 font-normal">Өрсөлдөгч</th>
                <th className="pr-3 font-normal">K–D</th>
                <th className="pr-3 font-normal">ADR</th>
                <th className="pr-3 font-normal">KAST</th>
                <th className="font-normal">Swing / раунд</th>
              </tr>
            </thead>
            <tbody className="text-ink-2">
              {[...rows].reverse().map((r) => (
                <tr key={`${r.match_id}-${r.map_number}`} className="border-t-1 border-line-soft">
                  <td className="py-1 pr-3 font-mono text-xs">{r.played_at ? day(r.played_at) : ''}</td>
                  <td className="pr-3">
                    <Link to={`/matches/${r.match_id}/m/${r.map_number}`} className="text-ct hover:underline">
                      {mapName(r.map)}
                    </Link>
                  </td>
                  <td className="pr-3">
                    {r.opponent}
                    {r.won != null && <span className="ml-1 text-xs text-ink-3">{r.won ? 'хожсон' : 'хожигдсон'}</span>}
                  </td>
                  <td className="pr-3 font-mono">
                    {r.kills}–{r.deaths}
                  </td>
                  <td className="pr-3 font-mono">{num(r.adr)}</td>
                  <td className="pr-3 font-mono">{num(r.kast_pct, 0, '%')}</td>
                  <td className="font-mono">{r.swing_per_round == null ? '—' : swingRateText(r.swing_per_round)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  )
}

function Maps({ p }: { p: Page }) {
  if (!p.maps.length) return null
  return (
    <section className="space-y-2">
      <h2 className="font-medium text-ink">Map ба Side</h2>
      <div className="overflow-x-auto rounded-xl border border-line bg-surface">
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-ink-3">
            <tr>
              <th className="px-3 py-2 font-normal">Map</th>
              <th className="font-normal">Side</th>
              <th className="font-normal">Раунд</th>
              <th className="font-normal">K–D</th>
              <th className="font-normal">ADR</th>
              <th className="font-normal">KAST</th>
              <th className="font-normal">Opening</th>
              <th className="pr-3 font-normal">Trade хийгдсэн</th>
            </tr>
          </thead>
          <tbody className="text-ink-2">
            {p.maps.map((m) => (
              <tr key={`${m.map}-${m.side}`} className="border-t-1 border-line-soft">
                <td className="px-3 py-1.5 text-ink">{mapName(m.map)}</td>
                <td className={m.side === 'ct' ? 'text-ct' : 'text-t'}>{SIDE[m.side as 'ct' | 't'] ?? m.side}</td>
                <td className="font-mono">{m.rounds}</td>
                <td className="font-mono">
                  {m.kills}–{m.deaths}
                </td>
                <td className="font-mono">{num(m.adr)}</td>
                <td className="font-mono">{num(m.kast_pct, 0, '%')}</td>
                <td className="font-mono">
                  {num(m.opening_win_pct, 0, '%')} <span className="text-ink-3">· {m.opening_attempts}</span>
                </td>
                <td className="pr-3 font-mono">{num(m.traded_death_pct, 0, '%')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-ink-3">
        Opening: эхний дуэлийн хожлын хувь · оролдлогын тоо. Цөөн раундтай мөрийн тоо санамсаргүй байж болно.
      </p>
    </section>
  )
}

function Findings({ p }: { p: Page }) {
  if (!p.findings.length) return null
  return (
    <section className="space-y-2">
      <h2 className="font-medium text-ink">Review-ийн олдворууд</h2>
      <p className="text-sm text-ink-2">
        {p.rounds_reviewed} раундын Review-ээс. 24 раунд тутмын давтамж, бүх тоглогчийн дундажтай харьцуулсан.
      </p>
      <div className="overflow-x-auto rounded-xl border border-line bg-surface">
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-ink-3">
            <tr>
              <th className="px-3 py-2 font-normal">Олдвор</th>
              <th className="font-normal">Төрөл</th>
              <th className="font-normal">Тоо</th>
              <th className="font-normal">24 раундад</th>
              <th className="pr-3 font-normal">Бүх тоглогч</th>
            </tr>
          </thead>
          <tbody className="text-ink-2">
            {p.findings.map((f) => {
              const more = f.per24 != null && f.pool_per24 != null && f.per24 > f.pool_per24 * 1.25
              const less = f.per24 != null && f.pool_per24 != null && f.per24 < f.pool_per24 * 0.75
              const note = more ? '▲ дунджаас их' : less ? '▼ дунджаас бага' : ''
              return (
                <tr key={f.code} className="border-t-1 border-line-soft">
                  <td className="px-3 py-1.5 text-ink">{f.label}</td>
                  <td>{KIND[f.kind] ?? f.kind}</td>
                  <td className="font-mono">{f.count}</td>
                  <td className="font-mono">
                    {num(f.per24, 2)} {note && <span className="ml-1 text-xs text-ink-3">{note}</span>}
                  </td>
                  <td className="pr-3 font-mono text-ink-3">{num(f.pool_per24, 2)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-ink-3">
        ▲/▼ нь бүх тоглогчийн дунджаас 25%-иас илүү зөрүүтэйг заана. Үүргийн жишигтэй харьцуулалт ба
        статистикийн шалгалт дараагийн шатанд (PL-3).
      </p>
    </section>
  )
}

function Spots({ p }: { p: Page }) {
  if (!p.spots.length) return null
  // One line per Map and Side: his three most common Callouts 20 s in.
  const lines = new Map<string, typeof p.spots>()
  for (const s of p.spots) lines.set(`${s.map}|${s.side}`, [...(lines.get(`${s.map}|${s.side}`) ?? []), s])
  return (
    <section className="space-y-2">
      <h2 className="font-medium text-ink">20 секунд дэх байрлал</h2>
      <ul className="space-y-1 text-sm text-ink-2">
        {[...lines.entries()].map(([key, spots]) => (
          <li key={key}>
            <span className="text-ink">{mapName(spots[0].map)}</span>{' '}
            <span className={spots[0].side === 'ct' ? 'text-ct' : 'text-t'}>
              {SIDE[spots[0].side as 'ct' | 't'] ?? spots[0].side}
            </span>
            {': '}
            {spots.map((s, i) => (
              <span key={s.place}>
                {i > 0 && ', '}
                {s.place} <span className="font-mono text-ink-3">{num(s.share, 0, '%')}</span>
              </span>
            ))}
          </li>
        ))}
      </ul>
    </section>
  )
}

function Weapons({ p }: { p: Page }) {
  if (!p.weapons.length) return null
  return (
    <section className="space-y-2">
      <h2 className="font-medium text-ink">Зэвсэг</h2>
      <ul className="space-y-1 text-sm text-ink-2">
        {p.weapons.map((w) => (
          <li key={w.weapon}>
            <span className="text-ink">{w.weapon}</span>{' '}
            <span className="font-mono text-ink-3">
              {w.kills} kill · {num(w.share, 0, '%')}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

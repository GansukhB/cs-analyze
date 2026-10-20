// A Player login's own page (docs/plans/01 WS-4): what to work on first (the Focus
// points of the last five Match Maps, Scrims included, worst Swing first), what to
// keep doing, and every recent Map, each opening its Review on the Player.
import { Link } from 'react-router'
import { $api } from '../api/client'
import type { components } from '../api/schema'
import { day } from '../jobs/format'
import { BriefingList } from './BriefingsPage'
import { clock, swingRateText, swingText } from '../review/format'

type Finding = components['schemas']['MeFinding']

export default function MePage() {
  const page = $api.useQuery('get', '/me/overview')
  if (page.isError) return <p className="text-ink-2">Энэ нэвтрэлт тоглогчтой холбогдоогүй байна.</p>
  if (!page.data) return <p className="text-ink-3">Уншиж байна…</p>
  const { player, maps, focus, keep, focus_maps } = page.data
  const review = (matchId: number, mapNumber: number, round?: number | null) =>
    `/matches/${matchId}/m/${mapNumber}?player=${player.steamid}${round ? `&round=${round}` : ''}`

  return (
    <div className="space-y-8">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold text-ink">{player.name}</h1>
        <Link to={`/players/${player.steamid}`} className="text-sm text-ct hover:underline">
          Бүх тоо, Map ба Side-аар →
        </Link>
      </div>

      <Briefings />

      <section className="space-y-3">
        <h2 className="font-medium text-ink">Эхлээд засах</h2>
        <p className="text-sm text-ink-3">
          Сүүлийн {focus_maps} Map-ын Review-ээс: Swing хамгийн их алдсанаас нь. Scrim ч орсон.
        </p>
        {focus.length ? (
          <ul className="space-y-2">
            {focus.map((f, i) => (
              <FindingCard key={i} f={f} href={review(f.match_id, f.map_number, f.round)} />
            ))}
          </ul>
        ) : (
          <p className="text-sm text-ink-3">Сүүлийн Map-уудад таны нэр дээр алдаа гарсангүй.</p>
        )}
      </section>

      {keep.length > 0 && (
        <section className="space-y-3">
          <h2 className="font-medium text-ink">Хадгалах</h2>
          <ul className="space-y-2">
            {keep.map((f, i) => (
              <FindingCard key={i} f={f} href={review(f.match_id, f.map_number, f.round)} />
            ))}
          </ul>
        </section>
      )}

      <section className="space-y-3">
        <h2 className="font-medium text-ink">Сүүлийн Map-ууд</h2>
        <div className="overflow-x-auto rounded-xl border border-line bg-surface">
          <table className="w-full text-sm">
            <thead className="border-b border-line text-left text-xs uppercase text-ink-3">
              <tr>
                <th className="px-4 py-2">Огноо</th>
                <th className="px-4 py-2">Map</th>
                <th className="px-4 py-2">Тоглолт</th>
                <th className="px-4 py-2 text-right">K–D</th>
                <th className="px-4 py-2 text-right">ADR</th>
                <th className="px-4 py-2 text-right">Swing/раунд</th>
              </tr>
            </thead>
            <tbody>
              {maps.map((m) => (
                <tr key={`${m.match_id}-${m.map_number}`} className="border-b border-line-soft last:border-0">
                  <td className="px-4 py-2 whitespace-nowrap text-ink-3">{day(m.played_at)}</td>
                  <td className="px-4 py-2">
                    <Link to={review(m.match_id, m.map_number)} className="text-ct hover:underline">
                      {m.map}
                    </Link>
                  </td>
                  <td className="px-4 py-2">
                    <span className={m.won === true ? 'text-good' : m.won === false ? 'text-crit' : ''}>{m.score}</span>{' '}
                    vs {m.opponent || '?'}
                    {m.scrim && (
                      <span className="ml-2 rounded border border-line px-1.5 text-[10px] uppercase text-ink-2">scrim</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">
                    {m.kills}–{m.deaths}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">{m.adr ?? '—'}</td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums">{swingRateText(m.swing_per_round)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

function FindingCard({ f, href }: { f: Finding; href: string }) {
  return (
    <li className="rounded-md border border-line bg-surface px-4 py-3 text-sm">
      <div className="flex flex-wrap items-baseline gap-x-3">
        <span className="font-medium text-ink">{f.title || f.label}</span>
        <span className="text-xs text-ink-3">
          {f.map} · R{f.round} {clock(f.t)}
          {f.scrim ? ' · scrim' : ''}
        </span>
        <span className={`ml-auto font-mono text-xs ${f.swing < 0 ? 'text-crit' : 'text-good'}`}>{swingText(f.swing)}</span>
      </div>
      {f.text && <p className="mt-1 text-ink-2">{f.text}</p>}
      <Link to={href} className="mt-1 inline-block text-xs text-ct hover:underline">
        Replay дээр үзэх →
      </Link>
    </li>
  )
}

function Briefings() {
  const list = $api.useQuery('get', '/briefings')
  if (!list.data?.briefings.length) return null
  return (
    <section className="space-y-3">
      <h2 className="font-medium text-ink">Briefing</h2>
      <BriefingList rows={list.data.briefings.slice(0, 5)} />
    </section>
  )
}

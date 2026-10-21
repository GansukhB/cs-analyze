// A Team's map pool (docs/plans/05 TM-6): each Map's share of Rounds won, pulled
// toward its own share over every Map so two lucky Maps don't read as a pocket
// pick, and the pool's depth over the Active Duty Maps as the data has them.
import type { components } from '../api/schema'

type Pool = components['schemas']['TeamMapPool']

const STATUS: Record<string, [string, string]> = {
  deep: ['гүн', 'text-good'],
  weak: ['сул', 'text-crit'],
  thin: ['цөөн', 'text-ink-3'],
  untested: ['тоглоогүй', 'text-ink-3'],
}

export default function MapPool({ pool }: { pool: Pool }) {
  return (
    <section className="space-y-2">
      <h2 className="font-medium text-ink">Map pool</h2>
      <p className="max-w-2xl text-sm text-ink-3">
        Гүн: идэвхтэй {pool.active.length} map-аас <b className="text-ink">{pool.depth}</b> нь 2+ удаа тоглогдож, раундын
        хожил нь өөрийн дундаж ({pool.mean}%)-аас 5 нэгжээс илүү доогуур биш. Хүч нь Match Map бүрийг сүүлийн тоглолтоос хойш
        насаар нь жинлэж (90 хоногт хагас), нэг map-ын жингээр өөрийн дундаж руу татсан; «Раунд» нь жингүй хувь.
      </p>
      <table className="text-sm">
        <thead className="text-left text-xs text-ink-3">
          <tr>
            <th className="py-1 pr-6 font-normal">Map</th>
            <th className="py-1 pr-6 text-right font-normal">Map W–L</th>
            <th className="py-1 pr-6 text-right font-normal">Раунд</th>
            <th className="py-1 pr-6 text-right font-normal" title="Сүүлийн тоглолтуудыг илүү жинлэж (90 хоногт хагас), нэг map-ын жингээр өөрийн дундаж руу татсан">
              Хүч
            </th>
            <th className="py-1 pr-6 text-right font-normal">Сүүлийн 90 хоног</th>
            <th className="py-1 pr-6 font-normal">Сүүлд</th>
            <th className="py-1 font-normal" />
          </tr>
        </thead>
        <tbody className="text-ink-2">
          {pool.rows.map((r) => {
            const [word, tone] = STATUS[r.status] ?? [r.status, 'text-ink-3']
            return (
              <tr key={r.map} className={`border-t-1 border-line ${r.active ? '' : 'opacity-60'}`}>
                <td className="py-1 pr-6 text-ink">
                  {r.label}
                  {!r.active && <span className="ml-1 text-xs text-ink-3">(pool-д алга)</span>}
                </td>
                <td className="py-1 pr-6 text-right font-mono">{r.maps ? `${r.won}–${r.maps - r.won}` : '—'}</td>
                <td className="py-1 pr-6 text-right font-mono">{r.share == null ? '—' : `${r.share}%`}</td>
                <td className="py-1 pr-6 text-right font-mono text-ink">{r.shrunk == null ? '—' : `${r.shrunk}%`}</td>
                <td className="py-1 pr-6 text-right font-mono">{r.recent}</td>
                <td className="py-1 pr-6 text-xs text-ink-3">{r.last ?? '—'}</td>
                <td className={`py-1 text-xs ${tone}`}>{word}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </section>
  )
}

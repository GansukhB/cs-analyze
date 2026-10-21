// A Team's Strengths and Weaknesses against the Pool, as the Reviews tell them
// (docs/plans TM-10): its tendencies across all its Maps once per Side, then
// what each Map's own Rounds say beyond them.
import type { components } from '../api/schema'

type Profile = components['schemas']['TeamProfile']
type Line = components['schemas']['TeamProfileLine']

const MAP: Record<string, string> = {
  de_ancient: 'Ancient', de_anubis: 'Anubis', de_cache: 'Cache', de_dust2: 'Dust II',
  de_inferno: 'Inferno', de_mirage: 'Mirage', de_nuke: 'Nuke', de_overpass: 'Overpass', de_train: 'Train',
}

function Lines({ lines }: { lines: Line[] }) {
  return (
    <ul className="space-y-0.5">
      {lines.map((l) => (
        <li key={`${l.key}-${l.good}`} className="text-ink-2">
          <span className={l.good ? 'text-good' : 'text-crit'}>{l.good ? '▲' : '▼'}</span> {l.label}{' '}
          <span className="font-mono text-xs text-ink">{l.value}</span>{' '}
          <span className="text-xs text-ink-3">(Pool {l.pool})</span>
        </li>
      ))}
    </ul>
  )
}

export default function ProfileSection({ p }: { p: Profile }) {
  return (
    <section className="space-y-3">
      <h2 className="font-medium text-ink">Давуу ба сул тал</h2>
      <div className="grid gap-4 sm:grid-cols-2">
        {(['ct', 't'] as const).map((side) =>
          (p.overall[side] ?? []).length ? (
            <div key={side} className="space-y-1 rounded-xl border border-line bg-surface p-4 text-sm">
              <p className="text-xs uppercase tracking-wide text-ink-3">
                <span className={side === 'ct' ? 'text-ct' : 'text-t'}>{side.toUpperCase()}</span> · бүх Map-аар
              </p>
              <Lines lines={p.overall[side] ?? []} />
            </div>
          ) : null,
        )}
      </div>
      {p.maps.length > 0 && (
        <div className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
          {p.maps.map((m) => (
            <div key={`${m.map}-${m.side}`} className="space-y-1">
              <p className="text-xs text-ink-3">
                {MAP[m.map] ?? m.map} <span className={m.side === 'ct' ? 'text-ct' : 'text-t'}>{m.side.toUpperCase()}</span>
              </p>
              <Lines lines={m.lines} />
            </div>
          ))}
        </div>
      )}
      <p className="text-xs text-ink-3">
        Review-үүдээс, бүх багийн Pool-той (z ±0.8). Map-ын мөр нь тухайн Map-ын өөрийн раундууд бүх Map-ын хандлагаас өөр
        зүйл хэлсэн үед л гарна.
      </p>
    </section>
  )
}

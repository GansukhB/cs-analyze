// What a Team does after the first contact on a Map (docs/plans/05 TM-7): after
// the opening at A, mid or B, where the bomb went down (or didn't); where most of
// the T stood at the Setup and whether they rotated; whether a CT came to a site
// whose opening was lost; where the T sat after the plant, and the retakes.
import { useState } from 'react'
import { Link } from 'react-router'
import { $api } from '../api/client'
import type { components } from '../api/schema'

type Node = components['schemas']['AfterNode']
type Branch = components['schemas']['AfterBranch']
type Ref = components['schemas']['CheckRef']

const WHERE: Record<string, string> = { A: 'A дээр', mid: 'mid-д', B: 'B дээр' }
const THEN: Record<string, string> = { A: 'A-д plant', B: 'B-д plant', none: 'plant-гүй' }
const SITUATION: Record<string, string> = { ahead: 'CT олон', even: 'тэнцүү', behind: 'CT цөөн' }
const pct = (a: number, b: number) => (b ? `${Math.round((100 * a) / b)}%` : '—')

function ghost(refs: Ref[], side: string, team: string) {
  return `/ghost?r=${refs.map((r) => `${r.match}.${r.map}.${r.round}`).join(',')}&side=${side}&team=${encodeURIComponent(team)}`
}

function Branches(props: { then: Branch[]; side: string; team: string; rotate?: string }) {
  const { then, side, team, rotate } = props
  const total = then.reduce((a, b) => a + b.n, 0)
  return (
    <span className="flex flex-wrap gap-x-3 gap-y-0.5">
      {then
        .filter((b) => b.n > 0)
        .map((b) => (
          <span key={b.then} className={b.then === rotate ? 'text-warn' : 'text-ink-2'}>
            {THEN[b.then]}
            {b.then === rotate && ' (rotate)'}{' '}
            <b className="font-mono text-ink">{pct(b.n, total)}</b>
            <span className="text-xs text-ink-3">
              {' '}
              {b.n} раунд, {b.won} хожсон
            </span>
            {b.refs.length > 0 && (
              <Link to={ghost(b.refs, side, team)} className="ml-1 text-xs text-ct hover:underline" title="Эдгээр раундыг давхарлаж үзэх">
                ⧉
              </Link>
            )}
          </span>
        ))}
    </span>
  )
}

function Row(props: { title: string; node: Node; side: string; team: string; rotate?: string; extra?: string }) {
  const { title, node, side, team, rotate, extra } = props
  return (
    <li className="space-y-0.5 border-t-1 border-line py-1.5">
      <p className="text-ink">
        {title}
        <span className="ml-2 text-xs text-ink-3">
          {node.n} раунд, {pct(node.wins, node.n)} хожсон{extra ? ` · ${extra}` : ''}
        </span>
      </p>
      <Branches then={node.then} side={side} team={team} rotate={rotate} />
    </li>
  )
}

export default function AfterContactSection({ teamId, name }: { teamId: number; name: string }) {
  const [map, setMap] = useState<string | null>(null)
  const q = $api.useQuery('get', '/teams/{team_id}/after-contact', {
    params: { path: { team_id: teamId }, query: map ? { map } : {} },
  })
  const after = q.data?.after
  if (!q.data || !after) return null
  const { t, ct } = after
  return (
    <section className="space-y-2">
      <h2 className="font-medium text-ink">Анхны тулааны дараа</h2>
      <p className="max-w-3xl text-sm text-ink-3">
        Раундын эхний kill хаана болсон (A, mid, B), дараа нь бөмбөг хаана тавигдсан. ⧉ нь тэр раундуудыг давхарлаж
        харуулна. Цөөн раундтай мөрийг баримт биш, сэжүүр гэж уншаарай.
      </p>
      <div className="flex flex-wrap gap-2 text-sm">
        {q.data.maps.map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMap(m)}
            className={`rounded-md border px-2 py-0.5 ${m === after.map ? 'border-ink-3 bg-raised text-ink' : 'border-line text-ink-3 hover:text-ink'}`}
          >
            {m.replace(/^de_/, '')}
          </button>
        ))}
      </div>
      <div className="grid gap-6 text-sm lg:grid-cols-2">
        <div className="space-y-3">
          <h3 className="font-medium text-t">T тал · {t.rounds} раунд</h3>
          <ul>
            {t.openings.map((n) => (
              <Row
                key={`${n.won}-${n.where}`}
                title={`Opening-ийг ${n.won ? 'авсан' : 'алдсан'}, ${WHERE[n.where]}`}
                node={n}
                side="t"
                team={name}
              />
            ))}
          </ul>
          {t.setups.length > 0 && (
            <ul>
              {t.setups.map((n) => (
                <Row
                  key={n.where}
                  title={`20 с-д ихэнх нь ${n.where} талд`}
                  node={n}
                  side="t"
                  team={name}
                  rotate={n.where === 'A' ? 'B' : 'A'}
                />
              ))}
            </ul>
          )}
          {t.plants > 0 && (
            <p className="text-ink-2">
              Plant-ын дундаж хугацаа <b className="font-mono text-ink">{t.plant_median} с</b>; 60 с-ээс хойш{' '}
              <b className="font-mono text-ink">
                {t.late}/{t.plants}
              </b>{' '}
              ({t.late_won} хожсон).
            </p>
          )}
          {t.post_plant.map((p) => (
            <p key={p.site} className="text-ink-2">
              {p.site}-д plant хийсний дараа ({p.rounds} раунд):{' '}
              {p.places.map(([place, n]) => `${place} ${pct(Number(n), p.rounds)}`).join(', ')}
            </p>
          ))}
        </div>
        <div className="space-y-3">
          <h3 className="font-medium text-ct">CT тал · {ct.rounds} раунд</h3>
          <ul>
            {ct.openings.map((n) => (
              <Row
                key={`${n.won}-${n.where}`}
                title={`Opening-ийг ${n.won ? 'авсан' : 'алдсан'}, ${WHERE[n.where]}`}
                node={n}
                side="ct"
                team={name}
                extra={n.looked ? `10 с-д өөр CT ирсэн ${n.reinforced}/${n.looked}` : undefined}
              />
            ))}
          </ul>
          {ct.retakes.length > 0 && (
            <table className="text-sm">
              <thead className="text-left text-xs text-ink-3">
                <tr>
                  <th className="py-1 pr-4 font-normal">Retake</th>
                  <th className="py-1 pr-4 font-normal">Plant-ын үед</th>
                  <th className="py-1 pr-4 font-normal">Раунд</th>
                  <th className="py-1 pr-4 font-normal">Хожсон</th>
                </tr>
              </thead>
              <tbody>
                {ct.retakes.map((r) => (
                  <tr key={`${r.site}-${r.situation}`} className="border-t-1 border-line">
                    <td className="py-1 pr-4 text-ink">{r.site}</td>
                    <td className="py-1 pr-4 text-ink-2">{SITUATION[r.situation]}</td>
                    <td className="py-1 pr-4 font-mono">{r.n}</td>
                    <td className="py-1 pr-4 font-mono">
                      {pct(r.won, r.n)}
                      {r.refs.length > 0 && (
                        <Link to={ghost(r.refs, 'ct', name)} className="ml-2 text-xs text-ct hover:underline">
                          ⧉
                        </Link>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </section>
  )
}

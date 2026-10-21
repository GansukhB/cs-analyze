import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { $api } from '../api/client'
import { StyleTable } from '../team/Style'
import { type Fixture, Todo } from './panels'
import type { Advice, AdviceSide, Evidence, Habit, PlaybookPanel, RoundRef, Strength, TodoPanel } from './types'

const STALE = 5 * 60_000

const STRENGTH: Record<Strength, string> = { weak: 'сул', medium: 'дунд', strong: 'хүчтэй' }
const OUR_SIDE = { ct: 'Манай CT', t: 'Манай T' } as const

const replayHref = (r: RoundRef) => `/matches/${r.match}/m/${r.map}?round=${r.round}`
// A column shows this many lines before «бусад» opens the rest.
const ADVICE_SHOWN = 4

// «Юу хийх»: the short list of actions on top, then one Map's Playbook at a time,
// picked from the Maps in veto order (CONTEXT.md: Playbook).
export function TodoTab({ data, fixture, map }: { data: TodoPanel; fixture: Fixture; map?: string }) {
  const chosen = map ?? data.maps[0]?.map
  const base = `/gameplan/${fixture.mine.id}/vs/${fixture.theirs.id}/s/todo`
  return (
    <>
      <Todo data={data} />
      <section className="panel">
        <h2>Playbook — map бүрийн стратеги</h2>
        <p className="lede">
          Хоёр багийн өмнөх тоглолтуудаас давтагдсан хэв маягийг гаргаж, тус бүрт хариу санал болгоно. Хэв маяг гэж
          тухайн талд 4-өөс доошгүй раундад давтагдсаныг л тооцно. Нотолгоо нь хэдэн тоглолтоос ирснээр хүчээ авна:
          ганц тоглолтынх <b>сул</b>, 2–3 тоглолтынх <b>дунд</b>, 4-өөс дээш <b>хүчтэй</b>.
        </p>
        {data.maps.length ? (
          <div className="filters">
            <span className="cap">Map</span>
            {data.maps.map((m) => (
              <Link
                key={m.map}
                className={`chip ${m.map === chosen ? 'on' : ''}`}
                to={`${base}/m/${m.map}${fixture.search}`}
              >
                {m.label} <span className={`tag ${m.call}`}>{m.call_label}</span>{' '}
                <small className="mono" title="Задлан шинжилсэн map: тэдний · манай">
                  {m.theirs}·{m.mine}
                </small>
              </Link>
            ))}
          </div>
        ) : (
          <p className="none">Аль ч багт задлан шинжилсэн map алга.</p>
        )}
      </section>
      {chosen && <Playbook fixture={fixture} map={chosen} />}
    </>
  )
}

/** The timeout card (GP-4): what they change when the Map goes against them, our answer. */
function TimeoutCard(props: { fixture: Fixture; map: string; label: string; opponent: string }) {
  const { fixture, map } = props
  const q = $api.useQuery(
    'get',
    '/gameplan/{mine}/vs/{theirs}/timeout/{map_name}',
    { params: { path: { mine: fixture.mine.id, theirs: fixture.theirs.id, map_name: map } } },
    { staleTime: STALE },
  )
  if (!q.data || !q.data.rounds) return null
  const c = q.data
  const moves = c.sides.filter((s) => s.moves.length)
  const pool = c.pool
  return (
    <details className="pb-style pb-timeout" open={moves.length > 0}>
      <summary>
        Timeout card — {props.label}: {props.opponent} дарамтанд юу өөрчилдөг вэ
      </summary>
      <p className="lede">
        {props.opponent}-ийн {c.rounds} раундаас {c.pressure} нь 2+ дараалан алдсаны эсвэл өөрсдийн timeout-ын дараах.
        Тэр раундуудад хэвшлээсээ илт өөрчлөгддөг зүйлс:
      </p>
      {moves.length === 0 ? (
        <p className="none">Дарамтанд тогтвортой өөрчлөгддөг зүйл илрээгүй.</p>
      ) : (
        <ul className="pb-rows">
          {moves.map((s) =>
            s.moves.map((m) => (
              <li key={`${s.side}-${m.key}`}>
                <span className={`tag ${s.side}`}>Тэдний {s.side.toUpperCase()}</span> <b>{m.label}</b>: ердөө {m.usual}% →
                дарамтанд {m.pressed}% ({m.rounds} раунд).{' '}
                <span className="pb-counter">{m.counter}</span>{' '}
                {m.refs.map((r) => (
                  <Link
                    key={`${r.match}-${r.map}-${r.round}`}
                    to={replayHref(r)}
                    className="mono"
                    title={`Тоглолт ${r.match}, map ${r.map}`}
                  >
                    R{r.round}{' '}
                  </Link>
                ))}
              </li>
            )),
          )}
        </ul>
      )}
      {pool.maps > 0 && pool.after_timeout.rounds > 0 && (
        <p className="lede">
          Манай timeout: {pool.maps} map-д 3+ дараалан алдсаны дараах раундыг timeout авсан баг{' '}
          {pool.after_timeout.pct}% ({pool.after_timeout.won}/{pool.after_timeout.rounds}), аваагүй нь {pool.without.pct}% хожсон.
        </p>
      )}
    </details>
  )
}

/** Both Teams' style on the Map, each against every Team on it (TM-5). */
function FixtureStyle(props: { fixture: Fixture; map: string; mine: string; theirs: string }) {
  const { fixture, map } = props
  const q = $api.useQuery(
    'get',
    '/gameplan/{mine}/vs/{theirs}/style/{map_name}',
    { params: { path: { mine: fixture.mine.id, theirs: fixture.theirs.id, map_name: map } } },
    { staleTime: STALE },
  )
  if (!q.data) return null
  return (
    <details className="pb-style">
      <summary>Хэв маяг — хоёр баг энэ map-ыг тоглосон бүх багтай харьцуулахад (percentile)</summary>
      <StyleTable
        teams={[
          { name: props.theirs, style: q.data.theirs, colour: 'var(--mark-theirs)' },
          { name: props.mine, style: q.data.mine, colour: 'var(--mark-mine)' },
        ]}
      />
    </details>
  )
}

// GP-9: read the habits over some Rounds only; the choice rides in the URL.
const BUY_VIEW: [string, string][] = [
  ['', 'Бүх buy'],
  ['full', 'Full buy'],
  ['light', 'Eco/force'],
]
// GP-9: how the Map stood when the Round began, by the Team's own Rounds.
const SCORE_VIEW: [string, string][] = [
  ['', 'Бүх оноо'],
  ['ahead', 'Тэргүүлж (2+)'],
  ['close', 'Ойр (±1)'],
  ['behind', 'Хоцорч (2+)'],
]

const DAYS_VIEW: [number, string][] = [
  [0, 'Бүх хугацаа'],
  [180, '180 хоног'],
  [90, '90 хоног'],
  [30, '30 хоног'],
]

function Playbook({ fixture, map }: { fixture: Fixture; map: string }) {
  const [search, setSearch] = useSearchParams()
  const buy = search.get('buy') ?? ''
  const days = Number(search.get('days') ?? 0)
  // DATA-7: the habits since the latest patch that changed how Rounds play.
  const since = search.get('since') ?? ''
  const score = search.get('score') ?? ''
  const latest = $api.useQuery('get', '/patches', {}, { staleTime: Infinity }).data?.patches[0]
  const pick = (key: string, value: string | number) => {
    const next = new URLSearchParams(search)
    if (value) next.set(key, String(value))
    else next.delete(key)
    setSearch(next, { replace: true })
  }
  const query = $api.useQuery(
    'get',
    '/gameplan/{mine}/vs/{theirs}/playbook/{map_name}',
    {
      params: {
        path: { mine: fixture.mine.id, theirs: fixture.theirs.id, map_name: map },
        query: { ...fixture.query, ...(buy ? { buy } : {}), ...(days ? { days } : {}), ...(since ? { since } : {}), ...(score ? { score } : {}) },
      },
    },
    { staleTime: STALE },
  )
  if (query.isError) return <p className="caveat">Энэ map-ын Playbook-ийг тооцоолж чадсангүй.</p>
  if (!query.data) return <p className="none">Playbook-ийг тооцоолж байна…</p>
  const d = query.data.data as unknown as PlaybookPanel
  const { theirs: them, mine: us } = d.sample
  return (
    <section className="panel pb">
      <h2>
        {d.label} — {d.opponent}-ийн эсрэг{' '}
        <Link
          to={`/gameplan/${fixture.mine.id}/vs/${fixture.theirs.id}/sheet/${map}${fixture.search}`}
          className="mono"
          title="Нэг хуудсанд, хэвлэхэд"
        >
          · Map хуудас
        </Link>
      </h2>
      <p className="lede">
        {d.opponent}: {them.maps} map ({them.h2h_maps} нь хоорондын), T {them.rounds.t} · CT {them.rounds.ct} раунд.{' '}
        {d.my_team}: {us.maps} map.
      </p>
      {them.all_maps !== undefined && them.all_maps > them.maps && (
        <p className="caveat">
          {d.opponent}-ийн habit-ийг одоогийн бүрэлдэхүүний (Lineup-ийн 4+ тоглогч) {them.maps} map-аас уншив; хуучин
          бүрэлдэхүүнтэй {them.all_maps - them.maps} map тооцогдоогүй.
        </p>
      )}
      <div className="filters">
        <span className="cap">Раунд</span>
        {BUY_VIEW.map(([value, label]) => (
          <button key={value} type="button" className={`chip ${buy === value ? 'on' : ''}`} onClick={() => pick('buy', value)}>
            {label}
          </button>
        ))}
        {DAYS_VIEW.map(([value, label]) => (
          <button key={value} type="button" className={`chip ${days === value ? 'on' : ''}`} onClick={() => pick('days', value)}>
            {label}
          </button>
        ))}
        {SCORE_VIEW.map(([value, label]) => (
          <button key={value || 'all'} type="button" className={`chip ${score === value ? 'on' : ''}`} onClick={() => pick('score', value)}>
            {label}
          </button>
        ))}
        {latest && (
          <button
            type="button"
            className={`chip ${since === latest.date ? 'on' : ''}`}
            title={latest.note}
            onClick={() => pick('since', since === latest.date ? '' : latest.date)}
          >
            {latest.name} patch-аас хойш
          </button>
        )}
        {(buy || days > 0 || since || score) && d.view && (
          <small className="mono">
            {d.view.rounds}/{d.view.of} раунд — эдийн засаг, pistol бүх раундаар
          </small>
        )}
      </div>
      {!them.maps && <p className="caveat">{d.opponent} энэ map-ыг тоглоогүй — зөвхөн Self-scout харагдана.</p>}
      {them.maps > 0 && !them.economy && (
        <p className="caveat">
          Эдийн засгийн дата алга: эдгээр map-ыг эдийн засгийг хадгалдаг болохоос өмнө parse хийсэн. Энэ fixture-ийн
          Scout-ыг дахин ажиллуулбал demo-г нь дахин татаж бөглөнө.
        </p>
      )}
      {!d.sites_known && (
        <p className="caveat">Энэ map-ын цэгүүдийн байрлал тодорхойгүй тул A / төв / B хуваарь гарахгүй.</p>
      )}
      {d.advice.limits.map((l) => (
        <p key={l} className="caveat">
          {l}
        </p>
      ))}

      <FixtureStyle fixture={fixture} map={map} mine={d.my_team} theirs={d.opponent} />
      <TimeoutCard fixture={fixture} map={map} label={d.label} opponent={d.opponent} />

      {d.plan.length > 0 && (
        <>
          <h3>Гол төлөвлөгөө</h3>
          <div className="pb-plan">
            {d.plan.map((p, i) => (
              <div key={i} className="pb-card">
                <div className="pb-head">
                  <span className={`tag ${p.side}`}>{OUR_SIDE[p.side]}</span>
                  <span className={`tag ${p.strength}`}>{STRENGTH[p.strength]}</span>
                </div>
                <b>{p.title}</b>
                <p className="pb-counter">{p.counter}</p>
              </div>
            ))}
          </div>
        </>
      )}

      <h3 className="pb-section">Ашиглах ба анхаарах</h3>
      <p className="lede">
        Хоёр багийн Review-г бүх багийн Pool-той харьцуулав: манай давуу тал тэдний сул талтай тулгарсан нь эхэнд,
        тэдний давуу тал манай сул талтай тулгарсан нь анхааруулгын эхэнд. Жин нь тухайн тоо хагас тутамд Pool-ын
        ердийн багаас хэдэн раундын зөрүү гаргадгийг заана.
      </p>
      {d.advice.sides.map((s) => (
        <AdviceColumns key={s.side} side={s} />
      ))}

      {d.sections.map((s) => (
        <div key={s.key}>
          <h3 className="pb-section">{s.title}</h3>
          <Habits habits={s.habits} strat={{ whose: 'theirs', team: fixture.mine.id, map }} />
        </div>
      ))}

      {d.beaten_by.length > 0 && (
        <>
          <h3 className="pb-section">Бусад баг тэднийг яаж хожсон</h3>
          <ul className="pb-rows">
            {d.beaten_by.map((b, i) => (
              <li key={i}>
                <span className={`tag ${b.side}`}>{b.side.toUpperCase()}</span> {b.text}{' '}
                <small>
                  {b.evidence.refs.map((r) => (
                    <Link key={`${r.match}-${r.map}-${r.round}`} className="mono" to={replayHref(r)}>
                      {' '}
                      R{r.round}
                    </Link>
                  ))}
                </small>
              </li>
            ))}
          </ul>
        </>
      )}

      <h3 className="pb-section">Pistol раунд</h3>
      {d.conversion.length > 0 && (
        <div className="tw">
          <table className="setup">
            <thead>
              <tr>
                <th>Баг</th>
                <th>Pistol хожсон</th>
                <th>Дараагийн 2-ыг хожсон</th>
                <th>Алдаад 2-оос 1-ийг авсан</th>
                <th>2 pistol → map</th>
              </tr>
            </thead>
            <tbody>
              {d.conversion.map((c) => (
                <tr key={c.team}>
                  <td>{c.team}</td>
                  <td className="mono">{c.pistols}</td>
                  <td className="mono">{c.converted}</td>
                  <td className="mono">{c.broken}</td>
                  <td className="mono">{c.both}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="cap">
            Pool: энэ map-ын бүх багийн дүн. Pistol хожоод дараагийн хоёр раундыг авах нь хувиргалт; хоёр pistol хожсон баг
            map-ын ихэнхийг хождог тул pistol-д бэлдэх нь хамгийн хямд раундууд.
          </p>
        </div>
      )}
      {d.pistol_plan && d.pistol_plan.length > 0 && (
        <ul className="pb-rows">
          {d.pistol_plan.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}
      {d.pistols.length ? (
        <ul className="pb-rows">
          {d.pistols.map((p) => (
            <li key={`${p.ref.match}-${p.ref.map}-${p.ref.round}`}>
              <Link className="mono" to={replayHref(p.ref)}>
                R{p.ref.round}
              </Link>{' '}
              {p.h2h && <span className="tag theirs">h2h</span>} {p.text}
              {p.next && <small> · {p.next}</small>}
            </li>
          ))}
        </ul>
      ) : (
        <p className="none">Энэ map дээр тэдний pistol раунд алга.</p>
      )}

      <h3 className="pb-section">Эдийн засаг (бүх map-аар)</h3>
      {d.economy.known && d.economy.buys ? (
        <>
          <p className="places">
            {(['eco', 'force', 'full'] as const).map((b) => (
              <span key={b}>
                <b>{b}</b> {d.economy.buys?.[b].n} раунд, {d.economy.buys?.[b].won} хожсон ·{' '}
              </span>
            ))}
          </p>
          <Habits habits={d.economy.habits} />
          {d.economy.choices && d.economy.choices.length > 0 && (
            <ul className="pb-rows">
              {d.economy.choices.map((c) => (
                <li key={c.text}>
                  {c.costly && <span className="tag theirs">ашиглах</span>} {c.text}
                </li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <p className="none">Эдийн засгийн дата алга.</p>
      )}

      <h3 className="pb-section">Тоглогчид ба matchup</h3>
      {d.players.length ? (
        <div className="pb-players">
          {d.players.map((p) => (
            <div key={p.player} className="pb-card">
              <div className="pb-head">
                <b>{p.player}</b>
                {p.tags.map((t) => (
                  <span key={t} className="tag theirs">
                    {t}
                  </span>
                ))}
              </div>
              {p.lines.map((l) => (
                <p key={l} className="pb-detail">
                  {l}
                </p>
              ))}
              {p.duels && <p className="pb-detail">{p.duels}</p>}
              {p.card?.map((l) => (
                <p key={l} className="pb-detail">
                  <small>Review: {l}</small>
                </p>
              ))}
            </div>
          ))}
        </div>
      ) : (
        <p className="none">Тоглогчийн дата алга.</p>
      )}

      <h3 className="pb-section">Self-scout — бидний таагдахуйц зуршил</h3>
      {d.predictability.length > 0 && (
        <ul className="pb-rows">
          {d.predictability.map((p) => (
            <li key={p.side} className={p.predictable ? 'warn-text' : undefined}>
              {p.text}
            </li>
          ))}
        </ul>
      )}
      <div className="sides2">
        {d.self_scout.map((s) => (
          <div key={s.side}>
            <h4>
              <span className={`tag ${s.side}`}>{s.label}</span>
            </h4>
            <Habits habits={s.habits} strat={{ whose: 'mine', team: fixture.mine.id, map }} />
          </div>
        ))}
      </div>
    </section>
  )
}

function Habits({ habits, strat }: { habits: Habit[]; strat?: StratFrom }) {
  if (!habits.length) return <p className="none">4-өөс доошгүй раундад давтагдсан хэв маяг алга.</p>
  return (
    <div className="pb-list">
      {habits.map((h, i) => (
        <div key={`${h.kind}-${i}`} className={`pb-card ${h.evidence?.strength ?? ''}`}>
          <b>{h.title}</b>
          <p className="pb-detail">{h.detail}</p>
          {h.counter && <p className="pb-counter">{h.counter}</p>}
          {h.review && <p className="pb-review">{h.review}</p>}
          {h.evidence && <Proof e={h.evidence} />}
          {strat && h.kind === 'set_play' && <StratButton habit={h} from={strat} />}
        </div>
      ))}
    </div>
  )
}

// SB-2: a Set play found in the data becomes a written Strat. Ours keeps its
// grenades and Rounds; theirs becomes our answer on the other Side, with their
// Rounds to study.
interface StratFrom {
  whose: 'mine' | 'theirs'
  team: number
  map: string
}

function StratButton({ habit, from }: { habit: Habit; from: StratFrom }) {
  const navigate = useNavigate()
  const create = $api.useMutation('post', '/strats', { onSuccess: (s) => navigate(`/stratbook/${s.id}`) })
  const side = habit.spec?.side ?? 't'
  const ours = from.whose === 'mine'
  const mySide = ours ? side : side === 't' ? 'ct' : 't'
  const make = () =>
    create.mutate({
      body: {
        team_id: from.team,
        map_name: from.map,
        side: mySide,
        name: (ours ? habit.title : `Эсрэг: ${habit.title}`).slice(0, 120),
        kind: ours ? (side === 't' ? 'execute' : 'setup') : mySide === 'ct' ? 'setup' : 'default',
        description: ours ? habit.detail : `Тэдний set play: ${habit.title}. ${habit.counter}`,
        roles: [],
        grenades: ours
          ? (habit.spec?.grenades ?? []).map((g) => ({
              slot: null,
              type: (['smoke', 'flash', 'he', 'inferno', 'decoy'].includes(g.type) ? g.type : 'smoke') as 'smoke',
              place: g.place,
              at: g.at,
              note: '',
              lineup: null,
            }))
          : [],
        timings: '',
        variations: '',
        calls: '',
        tags: ['set play'],
        status: 'draft',
        visibility: 'staff',
        examples: habit.evidence.refs.slice(0, 8).map((r) => ({ match_id: r.match, map_number: r.map, round: r.round, note: '' })),
      },
    })
  return (
    <p className="pb-review">
      <button type="button" className="underline" disabled={create.isPending} onClick={make}>
        {ours ? 'Strat болгох' : 'Эсрэг Strat бичих'}
      </button>
      {create.isError && <span className="crit-text"> Зөвхөн манай багийн Strat бичнэ.</span>}
    </p>
  )
}

function AdviceColumns({ side }: { side: AdviceSide }) {
  return (
    <div className="pb-adv">
      <h4>
        <span className={`tag ${side.side}`}>{side.label}</span>
      </h4>
      <div className="sides2">
        <div>
          <h5 className="pb-role pb-role-lever">Ашиглах</h5>
          <AdviceList entries={side.levers} none="Энэ талд ашиглах тод давуу тал гарсангүй." />
        </div>
        <div>
          <h5 className="pb-role pb-role-caution">Анхаарах</h5>
          <AdviceList entries={side.cautions} none="Энэ талд онцгой анхааруулга гарсангүй." />
        </div>
      </div>
    </div>
  )
}

function AdviceList({ entries, none }: { entries: Advice[]; none: string }) {
  const [all, setAll] = useState(false)
  if (!entries.length) return <p className="none">{none}</p>
  const shown = all ? entries : entries.slice(0, ADVICE_SHOWN)
  return (
    <div className="pb-list">
      {shown.map((a, i) => (
        <div key={`${a.title}-${i}`} className={`pb-card pb-${a.role} ${a.strength}`}>
          <div className="pb-head">
            {a.pair && <span className="tag pair">хос</span>}
            <span className={`tag ${a.strength}`}>{STRENGTH[a.strength]}</span>
            <small className="mono">{a.weight_label}</small>
          </div>
          <b>{a.title}</b>
          {a.facts.map((f) => (
            <p key={f} className="pb-detail">
              {f}
            </p>
          ))}
          {a.counter && <p className="pb-counter">{a.counter}</p>}
          {a.proofs.map((p) => (
            <Proof key={p.whose} e={p.evidence} label={a.proofs.length > 1 ? p.label : undefined} />
          ))}
        </div>
      ))}
      {entries.length > ADVICE_SHOWN && (
        <button type="button" className="chip" onClick={() => setAll(!all)}>
          {all ? 'Хураах' : `Бусад ${entries.length - ADVICE_SHOWN}`}
        </button>
      )}
    </div>
  )
}

function Proof({ e, label }: { e: Evidence; label?: string }) {
  return (
    <div className="pb-ev">
      {label && <span>{label}:</span>}
      <span className={`tag ${e.strength}`}>{STRENGTH[e.strength]}</span>
      <span>
        {e.n}/{e.of} {e.unit ?? 'раунд'} · {e.maps} map{e.h2h ? ` · ${e.h2h} нь h2h` : ''}
      </span>
      <span className="pb-refs">
        {e.refs.map((r) => (
          <Link
            key={`${r.match}-${r.map}-${r.round}`}
            to={replayHref(r)}
            title={`Replay-д нээх · тоглолт ${r.match}, ${r.map}-р map, ${r.round}-р раунд`}
          >
            R{r.round}
          </Link>
        ))}
        {e.refs.length > 1 && (
          // VIZ-5: every Round of the line played over each other.
          <Link to={`/ghost?r=${e.refs.map((r) => `${r.match}.${r.map}.${r.round}`).join(',')}`} title="Бүх раундыг давхарлаж үзэх">
            ⧉ давхар
          </Link>
        )}
      </span>
    </div>
  )
}

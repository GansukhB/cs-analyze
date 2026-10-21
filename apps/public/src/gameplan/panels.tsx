// The game plan's panels, ported from cstat's _gp_panels.html, _decision.html and
// _gp_metrics.html. Every label arrives worded from the server (app/services/mn.py);
// these components only lay it out. An empty section says "no data" in so many
// words rather than leaving a blank panel.
import { Fragment, useState } from 'react'
import { Link } from 'react-router'
import { $api } from '../api/client'
import type {
  DecisionForecast,
  DecisionPanel,
  DuelsPanel,
  EdgePanel,
  H2HPanel,
  MapsPanel,
  MetricRow,
  MetricsPanel,
  PlayersPanel,
  Profile,
  RolesPanel,
  SetupRow,
  TodoPanel,
  VerdictPanel,
} from './types'

export interface Fixture {
  mine: { id: number; name: string }
  theirs: { id: number; name: string }
  tabs: { key: string; label: string; grp: number; n?: number }[]
  /** The picked Lineups as the page's query string ("" or "?mine=…"), kept on every link. */
  search: string
  /** The same Lineups as the API's query parameters. */
  query: { my_lineup?: string; their_lineup?: string }
}

const tabHref = (f: Fixture, key: string) => `/gameplan/${f.mine.id}/vs/${f.theirs.id}/s/${key}${f.search}`

// Server-drawn SVG (app/services/charts.py escapes every label it writes).
function Chart({ svg }: { svg: string }) {
  return <div dangerouslySetInnerHTML={{ __html: svg }} />
}

const fmt2 = (v: number | null | undefined) => (v === null || v === undefined ? '' : v.toFixed(2))
const tone = (v: number) => (v < 0 ? 'var(--crit)' : v > 0 ? 'var(--good)' : undefined)
const join = (names: string[]) => names.join(' · ')

// --------------------------------------------------------------- decision ---
export function Decision({ data, fixture }: { data: DecisionPanel; fixture: Fixture }) {
  const d = data.decision
  return (
    <section className="panel">
      <div className="dec">
        <p className="dec-fix">
          <b>{fixture.mine.name}</b> <span>vs</span> <b>{fixture.theirs.name}</b>
          <span className="dec-n">{data.h2h_maps} хоорондын мап</span>
        </p>
        <div className={`dec-banner ${d.tone}`}>
          <p className="dec-call">{d.label}</p>
          <p className="dec-lead">{d.lead}</p>
        </div>
        <ForecastBlock forecast={d.forecast} fixture={fixture} />
        {d.cards.length > 0 && (
          <div className="dec-cards">
            {d.cards.map((c, i) => (
              <div key={i} className={`dec-card ${c.tone}`}>
                <b>
                  {c.value}
                  {c.unit && <span style={{ fontSize: 14 }}> {c.unit}</span>}
                </b>
                <span className="lbl">{c.label}</span>
                <span className="act">{c.action}</span>
                <span className="det">{c.detail}</span>
              </div>
            ))}
          </div>
        )}
        {d.moves.length > 0 && (
          <>
            <p className="dec-h">Гурван зүйл</p>
            {d.moves.map((m, i) => (
              <div key={i} className={`dec-move ${m.tone}`}>
                <span className="n">{i + 1}</span>
                <span>
                  <span className="w">{m.what}</span>
                  <span className="y">{m.why}</span>
                </span>
              </div>
            ))}
          </>
        )}
        {data.top_advice && (data.top_advice.levers.length > 0 || data.top_advice.cautions.length > 0) && (
          <>
            <p className="dec-h">Бүх map-аас: ашиглах ба анхаарах</p>
            {[...data.top_advice.levers.map((a) => ({ ...a, tone: 'good' })), ...data.top_advice.cautions.map((a) => ({ ...a, tone: 'warn' }))].map(
              (a, i) => (
                <div key={i} className={`dec-move ${a.tone}`}>
                  <span className="n">{a.tone === 'good' ? '+' : '!'}</span>
                  <span>
                    <span className="w">{a.what}</span>
                    <span className="y">{a.why}</span>
                  </span>
                </div>
              ),
            )}
          </>
        )}
        <p className="dec-foot">{d.confidence}</p>
        <a className="dec-more" href="#detail">
          Дэлгэрэнгүй нотолгоо доор ↓
        </a>
      </div>

      <div id="detail">
        <h2>Дэлгэрэнгүй нотолгоо</h2>
        <p className="cap" style={{ margin: '0 0 12px' }}>
          Дээрх шийдвэрийн цаад тоонууд хэсэг тус бүрдээ байна.
        </p>
        <div className="filters" style={{ borderBottom: 0, paddingBottom: 0 }}>
          {fixture.tabs
            .filter((t) => t.grp === 2)
            .map((t) => (
              <Link key={t.key} className="chip" to={tabHref(fixture, t.key)}>
                {t.label}
                {t.n ? ` · ${t.n}` : ''}
              </Link>
            ))}
        </div>
      </div>
    </section>
  )
}

// The Forecast (docs/plans/03): each format's chance, rounded to 5 like the model
// deserves, how often such forecasts came true, the Maps both Teams play, its
// limits, and a button that keeps it to be graded once the series is played.
function ForecastBlock({ forecast, fixture }: { forecast: DecisionForecast; fixture: Fixture }) {
  const [format, setFormat] = useState('bo3')
  const save = $api.useMutation('post', '/forecasts')
  if (!forecast.series.length) {
    return forecast.limits.length ? <p className="fc-limit">{forecast.limits.join(' ')}</p> : null
  }
  const bo3 = forecast.series.find((s) => s.format === 'Bo3')
  const ids = (raw?: string) => (raw ? raw.split(',').filter(Boolean) : [])
  function keep() {
    save.mutate({
      body: {
        my_team_id: fixture.mine.id,
        opponent_id: fixture.theirs.id,
        my_lineup: ids(fixture.query.my_lineup),
        their_lineup: ids(fixture.query.their_lineup),
        format: format as 'bo1' | 'bo3' | 'bo5',
      },
    })
  }
  return (
    <div className="fc">
      <div className="fc-series">
        {forecast.series.map((s) => (
          <div key={s.format} className={`fc-tile ${s.tone}`}>
            <b>~{s.pct}%</b>
            <span className="fmt">
              {s.format} · {s.word}
            </span>
            <span className="of">{s.often}</span>
          </div>
        ))}
      </div>
      <p className="fc-note">
        {forecast.ratings
          .map((r) => `${r.team} ${r.rating ?? '—'}${r.region ? ` (${r.region}, ${r.series} цуврал)` : ''}`)
          .join(' · ')}
        {bo3?.trust ? ` ${bo3.trust}` : ''}
      </p>
      {(forecast.why ?? []).length > 0 && <p className="fc-note">Яагаад: {forecast.why!.join(' ')}</p>}
      {forecast.maps.length > 0 && (
        <table className="setup fc-maps">
          <thead>
            <tr>
              <th>Map</th>
              {forecast.maps_used && <th className="num">Бидний хожих</th>}
              <th className="num">Бид тоглосон</th>
              <th className="num">Тэд тоглосон</th>
            </tr>
          </thead>
          <tbody>
            {forecast.maps.map((m) => (
              <tr key={m.map}>
                <td>{m.map}</td>
                {forecast.maps_used && <td className="num">~{m.pct}%</td>}
                <td className="num">{m.played_mine}</td>
                <td className={`num ${m.played_theirs === 0 ? 'warn' : ''}`}>{m.played_theirs}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="fc-note">Тоглосон: сүүлийн 180 хоногт хадгалагдсан Match Map. Тэдний тоглоогүй Map нь ихэвчлэн ban-д ордог.</p>
      {forecast.limits.map((l, i) => (
        <p key={i} className="fc-limit">
          {l}
        </p>
      ))}
      <div className="fc-save">
        <select value={format} onChange={(e) => setFormat(e.target.value)} aria-label="Формат">
          <option value="bo1">Bo1</option>
          <option value="bo3">Bo3</option>
          <option value="bo5">Bo5</option>
        </select>
        <button type="button" onClick={keep} disabled={save.isPending}>
          Forecast хадгалах
        </button>
        {save.isSuccess && <span>Хадгаллаа: тоглолтын дараа дүгнэгдэнэ.</span>}
        {save.isError && <span className="crit-text">Хадгалж чадсангүй.</span>}
        <Link to="/forecasts">Бүх Forecast →</Link>
      </div>
    </div>
  )
}

// What the evidence settles about one Player (PL-3, PL-7): each line passed its
// test against the cohort or every reviewed Player, so a short list is the honest one.
function Proven({ proven }: { proven?: PlayersPanel['cards'][number]['proven'] }) {
  if (!proven) return null
  const groups: [string, string[], string][] = [
    ['Давуу тал', proven.strengths, 'var(--good)'],
    ['Сул тал', proven.weaknesses, 'var(--crit)'],
    ['Хандлага', proven.tendencies, 'var(--ink-2)'],
  ]
  if (!groups.some(([, lines]) => lines.length) && !proven.swing) return null
  return (
    <div className="proven">
      {groups
        .filter(([, lines]) => lines.length)
        .map(([title, lines, color]) => (
          <div key={title}>
            <b style={{ color }}>{title}</b>
            <ul>
              {lines.map((l, i) => (
                <li key={i}>{l}</li>
              ))}
            </ul>
          </div>
        ))}
      {proven.swing && !proven.strengths.concat(proven.weaknesses).some((l) => l.startsWith('Swing')) && (
        <p className="cap">{proven.swing}: бусдаас ялгарахгүй.</p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- verdict ---
export function Verdict({ data, fixture }: { data: VerdictPanel; fixture: Fixture }) {
  const r = data.record
  return (
    <section className="panel">
      <h2>Дүгнэлт</h2>
      <p className="lead">{data.headline}</p>
      <div className="statrow">
        <div className={`stat ${r.won > r.lost ? 'ok' : r.lost > r.won ? 'bad' : ''}`}>
          <b>
            {r.won}–{r.lost}
          </b>
          <span>хоорондын мап</span>
        </div>
        <div className="stat">
          <b>{data.sample.my_maps}</b>
          <span>манай мап</span>
        </div>
        <div className="stat">
          <b>{data.sample.opponent_maps}</b>
          <span>тэдний мап</span>
        </div>
        <div className="stat">
          <b>{data.sample.pool_teams}</b>
          <span>сангийн баг</span>
        </div>
        {data.worst_side && (
          <div className="stat bad">
            <b>{data.worst_side}</b>
            <span>хамгийн их унасан хагас</span>
          </div>
        )}
      </div>
      {data.points.length ? (
        <>
          <h2>Гол зүйлс</h2>
          {data.points.map((p, i) => (
            <div key={i} className="card2">
              <p className="why" style={{ margin: 0 }}>
                {p}
              </p>
            </div>
          ))}
        </>
      ) : (
        <p className="none">Тоо дэмжсэн дүгнэлт гарсангүй — задлан шинжилсэн тоглолт хэрэгтэй.</p>
      )}
      <p style={{ marginTop: 18 }}>
        <Link className="chip" to={tabHref(fixture, 'todo')}>
          Юу хийхийг харах →
        </Link>
      </p>
    </section>
  )
}

export function Todo({ data }: { data: TodoPanel }) {
  return (
    <section className="panel">
      <h2>Товч зөвлөмж</h2>
      {data.actions.length ? (
        <div className="todo">
          {data.actions.map((a, i) => (
            <div key={i} className="item2">
              <span className="num">{i + 1}</span>
              <span className="body">
                <b>{a.what}</b>
                <span>{a.why}</span>
              </span>
            </div>
          ))}
        </div>
      ) : (
        <p className="none">Тоо дэмжсэн үйлдэл гарсангүй.</p>
      )}
    </section>
  )
}

// ---------------------------------------------------------------- metrics ---
function MetricRows({ rows, withWhy }: { rows: MetricRow[]; withWhy: boolean }) {
  return (
    <>
      {rows.map((m) => (
        <div key={m.label} className="mrow">
          <span>
            {m.label} {withWhy && <small>{m.why}</small>}
          </span>
          <span className="n">
            {m.value}
            {m.unit} <small>сан {m.pool_mean}</small>
          </span>
          <span className="z">{m.z}σ</span>
        </div>
      ))}
    </>
  )
}

function ProfileBlock({ prof }: { prof: Profile }) {
  if (prof.empty_note) {
    return (
      <div className="caveat">
        {!prof.maps
          ? 'Задлан шинжилсэн бүх мап нь яг энэ өрсөлдөгчийн эсрэг тул өөрийн бие даасан түвшинг хэмжих юм алга. Өөр тоглолтыг нь задлан шинжилбэл энэ панель дүүрнэ.'
          : `${prof.maps} мап задлагдсан ч сантай харьцуулж дүгнэхэд ямар ч үзүүлэлтэд раунд хүрэлцсэнгүй.`}
      </div>
    )
  }
  const heading = (color: string) => ({
    fontSize: 13,
    textTransform: 'uppercase' as const,
    letterSpacing: '.1em',
    color,
  })
  return (
    <>
      <div className="mgrid">
        <div className="figure">
          <h3 style={heading('var(--good)')}>Хүчтэй тал</h3>
          {prof.strengths.length ? (
            <MetricRows rows={prof.strengths} withWhy />
          ) : (
            <>
              <p className="none" style={{ fontStyle: 'normal', margin: '8px 0 0' }}>
                {prof.rounds} раундын түүвэр дээр сангийн дунджаас 0.8 стандарт хазайлтаас илүү дээгүүр гарсан
                үзүүлэлт байхгүй. Харьцангуй хамгийн сайн нь:
              </p>
              <MetricRows rows={prof.best_relative} withWhy={false} />
            </>
          )}
        </div>
        <div className="figure">
          <h3 style={heading('var(--crit)')}>Сул тал</h3>
          {prof.weaknesses.length ? (
            <MetricRows rows={prof.weaknesses} withWhy />
          ) : (
            <>
              <p className="none" style={{ fontStyle: 'normal', margin: '8px 0 0' }}>
                Сангаас 0.8 стандарт хазайлтаас илүү доогуур зүйл байхгүй. Харьцангуй хамгийн тааруу нь:
              </p>
              <MetricRows rows={prof.worst_relative} withWhy={false} />
            </>
          )}
        </div>
      </div>
      <p className="cap" style={{ marginTop: 4 }}>
        {prof.maps} мап, {prof.rounds} раунд · сан {prof.pool_n} баг — энэ өрсөлдөгчийн эсрэг мапуудыг хассан.
      </p>
    </>
  )
}

export function Metrics({ data, fixture }: { data: MetricsPanel; fixture: Fixture }) {
  return (
    <section className="panel">
      <h2>Үзүүлэлт — зөвхөн өөрсдийн тоглолт дээр</h2>
      <div className="figure">
        <Chart svg={data.chart} />
        <p className="cap">
          Хоёр багийн үзүүлэлтийг харьцуулав. Аль ч талын тоонд энэ фикстурын мапууд ороогүй: хоорондоо тоглосон
          мапаар хэмжвэл сул тал нь бүх зүйлдээ тааруу гарч, ашиггүй болно. Тэднийтэй тулахад юу өөрчлөгддөгийг
          "Хоорондын" хэсэг хэлнэ.
        </p>
      </div>
      <section className="scope mine">
        <h3>{fixture.mine.name}</h3>
        <ProfileBlock prof={data.mine} />
      </section>
      <section className="scope theirs">
        <h3>{fixture.theirs.name}</h3>
        <ProfileBlock prof={data.theirs} />
      </section>
      <p className="cap" style={{ marginTop: 14 }}>
        σ гэдэг нь задлан шинжилсэн бүх багийн сангийн дундажаас хэдэн стандарт хазайлтаар зөрж байгаа нь —
        өрсөлдөгчтэйгээ харьцуулсан тоо биш. Хоёр багийг зөвхөн бие бие нь харьцуулбал "тэд илүү сайн" гэсэн ганц
        дүгнэлт гарна.
      </p>
    </section>
  )
}

// -------------------------------------------------------------------- h2h ---
export function H2H({ data }: { data: H2HPanel }) {
  const h = data.totals
  return (
    <section className="panel">
      <h2>Хоорондын тоглолт</h2>
      {h.maps_played ? (
        <>
          <div className="statrow">
            <div
              className={`stat ${(h.maps_won ?? 0) > (h.maps_lost ?? 0) ? 'ok' : (h.maps_lost ?? 0) > (h.maps_won ?? 0) ? 'bad' : ''}`}
            >
              <b>
                {h.maps_won}–{h.maps_lost}
              </b>
              <span>мап</span>
            </div>
            <div className="stat">
              <b>{h.map_win_pct}%</b>
              <span>мапын хожил</span>
            </div>
            <div className="stat">
              <b>
                {h.rounds_for}–{h.rounds_against}
              </b>
              <span>раунд</span>
            </div>
          </div>
          {data.continuity_note && <div className="caveat">{data.continuity_note}</div>}
        </>
      ) : (
        <p className="none">
          Хоёр багийн хоорондын задлан шинжилсэн мап байхгүй. Доорх хэсгүүд зөвхөн хоёр багийн өөрсдийн түвшинг
          харуулна.
        </p>
      )}

      {data.delta_rows.length > 0 && (
        <>
          <div className="figure">
            <Chart svg={data.chart} />
            <p className="cap">
              Өөрсдийн тоглолтын түвшнээс энэ багийн эсрэг үзүүлэлт хэр зөрж байгаа нь. Энэ зөрүү л "бид энэ зүйлд
              тааруу" ба "тэд биднийг тааруу болгодог" хоёрыг ялгана. ✓ нь зөрүү санамсаргүй тохиолдлоос давсан (хувь нь 5+
              пункт, p &lt; 0.10, Match Map-ын раундуудыг хамааралтай гэж тооцсон); саарал нь дээж хүрэлцэхгүй эсвэл
              санамсаргүйгээр гарч болох зөрүү.
            </p>
          </div>
          <div className="tw">
            <table className="setup">
              <thead>
                <tr>
                  <th>Үзүүлэлт</th>
                  <th>Өөрсдийн</th>
                  <th>Тэдний эсрэг</th>
                  <th>Зөрүү</th>
                  <th>Юу хэлж байна</th>
                </tr>
              </thead>
              <tbody>
                {data.delta_rows.map((r) => (
                  <tr key={r.label}>
                    <td>{r.label}</td>
                    <td className="mono">
                      {r.own}
                      {r.unit}
                    </td>
                    <td className="mono">
                      {r.versus}
                      {r.unit}
                    </td>
                    <td
                      className="mono"
                      style={{ color: r.clear ? (r.worse ? 'var(--crit)' : 'var(--good)') : 'var(--ink-3)' }}
                      title={r.enough ? undefined : 'Тэдний эсрэг дээж бага'}
                    >
                      {r.delta}
                      {r.unit}
                      {r.clear ? ' ✓' : ''}
                    </td>
                    <td>{r.why}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="cap">
            Өөрсдийн {data.own_rounds} раунд, тэдний эсрэг {data.versus_rounds} раунд.
          </p>
        </>
      )}

      {data.by_map.length > 0 && (
        <>
          <h2>Мапаар</h2>
          <div className="tw">
            <table className="setup">
              <thead>
                <tr>
                  <th>Газрын зураг</th>
                  <th>Тоглосон</th>
                  <th>W–L</th>
                  <th>Хожил %</th>
                  <th>Раунд</th>
                  <th>Раундын зөрүү</th>
                </tr>
              </thead>
              <tbody>
                {data.by_map.map((e) => (
                  <tr key={e.map}>
                    <td>{e.map_label}</td>
                    <td className="mono">{e.played}</td>
                    <td className="mono">
                      {e.won}–{e.lost}
                    </td>
                    <td className="mono">{e.win_pct}%</td>
                    <td className="mono">
                      {e.rounds_for}–{e.rounds_against}
                    </td>
                    <td className="mono" style={{ color: tone(e.round_diff) }}>
                      {e.round_diff}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {data.matches.length > 0 && (
        <>
          <h2>Тоглолт тус бүр</h2>
          {data.matches.map((m, i) => (
            <div key={i} className="card2">
              <h3>
                {m.my_maps_won}–{m.their_maps_won}
                <span className={`tag ${m.my_maps_won > m.their_maps_won ? 'pick' : 'ban'}`}>{m.played_at}</span>
              </h3>
              <p className="places" style={{ marginTop: 6 }}>
                {m.maps.map((s, j) => (
                  <Fragment key={j}>
                    {m.match_id && s.map_number ? (
                      <Link to={`/matches/${m.match_id}/m/${s.map_number}`} className="hover:underline">
                        <b>{s.map_label}</b>
                      </Link>
                    ) : (
                      <b>{s.map_label}</b>
                    )}{' '}
                    <span style={{ color: s.won ? 'var(--good)' : 'var(--crit)' }}>
                      {s.my_score}–{s.their_score}
                    </span>
                    {j < m.maps.length - 1 && ' · '}
                  </Fragment>
                ))}
              </p>
            </div>
          ))}
        </>
      )}

      {data.continuity && (
        <>
          <h2>Дүнг гаргасан бүрэлдэхүүн</h2>
          <div className="sides2">
            {data.continuity.sides.map((s) => (
              <div key={s.scope}>
                <h4>
                  <span className={`tag ${s.scope}`}>{s.team}</span>
                  {s.n}/{s.of} тоглогч хоорондын мапуудад тоглосон
                </h4>
                <p className="places">
                  <b>Одоогийн тав:</b> {join(s.current)}
                </p>
                {s.unseen.length > 0 && (
                  <p className="places">
                    <b>Тэднийтэй тоглож үзээгүй:</b> {join(s.unseen)}
                  </p>
                )}
              </div>
            ))}
          </div>
          {data.continuity.stale && (
            <div className="caution">
              Дүнг гаргасан бүрэлдэхүүний хагасаас илүү нь өөрчлөгдсөн — энэ бол таамаг биш, түүх.
            </div>
          )}
        </>
      )}
    </section>
  )
}

// ------------------------------------------------------------------- maps ---
function SetupTable({ rows, empty }: { rows: SetupRow[]; empty: string }) {
  if (!rows.length) return <p className="none">{empty}</p>
  return (
    <table className="setup">
      <thead>
        <tr>
          <th>Тоглогч</th>
          <th>Үүрэг</th>
          <th>Байр</th>
          <th>Ал</th>
          <th>Төвлөрөл</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.name}>
            <td>{r.name}</td>
            <td>{r.role}</td>
            <td>{r.post}</td>
            <td className="mono">
              {r.post_kills}/{r.total_kills}
            </td>
            <td className="mono">{r.concentration}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function Maps({ data, fixture }: { data: MapsPanel; fixture: Fixture }) {
  const [map, setMap] = useState(data.cards[0]?.map ?? '')
  const [side, setSide] = useState<'ct' | 't'>('ct')
  const card = data.cards.find((c) => c.map === map) ?? data.cards[0]
  const rec = (r: MapsPanel['board'][number]['mine']) =>
    r ? (
      <>
        {r.won}–{r.lost} · {r.win_pct}%
        {r.thin && (
          <>
            {' '}
            <span className="tag unknown">цөөн</span>
          </>
        )}
      </>
    ) : (
      '—'
    )
  return (
    <section className="panel">
      <h2>Газрын зураг: вето, төлөвлөгөө, байрлал</h2>
      <div className="figure">
        <Chart svg={data.chart} />
        <p className="cap">Задлан шинжилсэн бүх мап дээрх map-ын хожлын хувь. Задлагдаагүй мап нь сул тал биш — судлагдаагүй хэсэг.</p>
      </div>
      <div className="tw">
        <table className="setup">
          <thead>
            <tr>
              <th>Газрын зураг</th>
              <th>Манай</th>
              <th>Тэдний</th>
              <th>Хоорондын</th>
              <th>Шийдэл</th>
              <th>Итгэл</th>
            </tr>
          </thead>
          <tbody>
            {data.board.map((b) => (
              <tr key={b.map}>
                <td>{b.map_label}</td>
                <td className="mono">{rec(b.mine)}</td>
                <td className="mono">{rec(b.theirs)}</td>
                <td className="mono">{rec(b.h2h)}</td>
                <td>
                  <span className={`tag ${b.call}`}>{b.call_label}</span>
                </td>
                <td className="mono">{b.confidence}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="cap">
        "Мэдээгүй" гэдэг нь бид тоглосон, тэд задлагдаагүй: тэдний сул тал биш, бидний судалгааны цоорхой.
        "Зайлсхийх" бол эсрэгээрээ — тэд тэнд демотой, бид байхгүй.
      </p>
      {!data.bombsite.healthy && (
        <div className="caveat">
          Хадгалсан bomb-ын цэг bomb-ний бүртгэлтэй таарахгүй байна ({data.bombsite.mismatched}/{data.bombsite.checked}{' '}
          шалгасан тавилт зөрүүтэй). Доорх цэгийн тоонууд баталгаа муутай.
        </div>
      )}

      {card ? (
        <>
          <div className="filters" style={{ marginTop: 22 }}>
            <span className="cap">Газрын зураг</span>
            {data.cards.map((c) => (
              <button key={c.map} type="button" className={`chip mono ${c.map === card.map ? 'on' : ''}`} onClick={() => setMap(c.map)}>
                {c.map_label}
              </button>
            ))}
            <span className="cap">Тал</span>
            {card.sides.map((s) => (
              <button key={s.key} type="button" className={`chip mono ${s.key === side ? 'on' : ''}`} onClick={() => setSide(s.key)}>
                Бид {s.label}
              </button>
            ))}
          </div>
          <h3>
            {card.map_label} <span className={`tag ${card.call}`}>{card.call_label}</span>{' '}
            <span className="tag unknown">итгэл {card.confidence}</span>
          </h3>
          <div className="statrow">
            {card.ours && (
              <div className={`stat ${card.ours.win_pct >= 55 ? 'ok' : card.ours.win_pct <= 45 ? 'bad' : ''}`}>
                <b>
                  {card.ours.won}–{card.ours.lost}
                </b>
                <span>манай ({card.ours.win_pct}%)</span>
              </div>
            )}
            {card.theirs && (
              <>
                <div className="stat">
                  <b>
                    {card.theirs.won}–{card.theirs.lost}
                  </b>
                  <span>тэдний ({card.theirs.win_pct}%)</span>
                </div>
                <div className="stat">
                  <b>{card.theirs.median_plant_sec ?? '—'}с</b>
                  <span>тэдний тавилтын хэм</span>
                </div>
              </>
            )}
          </div>
          {card.sides
            .filter((s) => s.key === side)
            .map((s) => (
              <div key={s.key}>
                <h4 className="mb-2 mt-4 flex items-center gap-2 text-sm text-ink-2">
                  <span className={`tag ${s.key}`}>бид {s.label}</span> тэд {s.their_label}
                </h4>
                {s.plan.length ? (
                  <div className="card2">
                    <h3>Төлөвлөгөө</h3>
                    <ul>
                      {s.plan.map((l, i) => (
                        <li key={i}>{l}</li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <p className="none">Энэ талд тэдний тоо дэмжсэн төлөвлөгөө гарсангүй.</p>
                )}
                <div className="sides2">
                  <div>
                    <h4>
                      <span className="tag mine">{fixture.mine.name}</span> байрлал
                    </h4>
                    <SetupTable rows={s.mine} empty="Энэ мап, тал дээр манай байрлалын өгөгдөл байхгүй." />
                  </div>
                  <div>
                    <h4>
                      <span className="tag theirs">{fixture.theirs.name}</span> байрлал
                    </h4>
                    <SetupTable rows={s.theirs} empty="Энэ мап, тал дээр тэдний байрлалын өгөгдөл байхгүй." />
                    {s.their_kills_from.length > 0 && (
                      <p className="places">
                        <b>Тэд эндээс алдаг:</b> {s.their_kills_from.map((r) => `${r.place} ${r.count}`).join(' · ')}
                      </p>
                    )}
                    {s.their_dies_at.length > 0 && (
                      <p className="places">
                        <b>Тэд энд үхдэг:</b> {s.their_dies_at.map((r) => `${r.place} ${r.count}`).join(' · ')}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          {card.cautions.map((l, i) => (
            <div key={i} className="caution">
              {l}
            </div>
          ))}
          <p className="cap">
            Байршил зөвхөн өөрийн мапын дотор утгатай тул мапуудыг хэзээ ч нэгтгээгүй: Anubis дээрх "A цэг" ба Nuke
            дээрх "A цэг" хоёр өөр өрөө.
          </p>
        </>
      ) : (
        <p className="none">Аль ч талын задлан шинжилсэн мап байхгүй тул төлөвлөгөө гарсангүй.</p>
      )}
    </section>
  )
}

// ---------------------------------------------------------------- players ---
export function Players({ data }: { data: PlayersPanel }) {
  const [picked, setPicked] = useState<number | null>(data.cards[0]?.id ?? null)
  const card = data.cards.find((c) => c.id === picked) ?? data.cards[0]
  return (
    <section className="panel">
      <h2>Тоглогчид</h2>
      <p className="cap" style={{ marginBottom: 12 }}>
        Одоогийн бүрэлдэхүүн. Зөвлөмж бүр өөрийн тооноос гарсан: түүвэр хүрэлцээгүй бол мөр үүсэхгүй.
      </p>
      {card ? (
        <>
          <div className="filters">
            {(['mine', 'theirs'] as const).map((scope) => (
              <Fragment key={scope}>
                <span className="cap">{scope === 'mine' ? 'Манай' : 'Тэдний'}</span>
                {data.cards
                  .filter((c) => c.scope === scope)
                  .map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      className={`chip ${scope} ${c.id === card.id ? 'on' : ''}`}
                      onClick={() => setPicked(c.id)}
                    >
                      {c.name}
                    </button>
                  ))}
              </Fragment>
            ))}
          </div>
          <div className="card2" style={{ ['--scope-soft' as string]: `var(--${card.scope}-soft)` }}>
            <h3>
              {card.name} <span className={`tag ${card.scope}`}>{card.team}</span>
              {card.elsewhere && <span className="tag">шинэ · {card.elsewhere}-аас</span>}
              {card.roles.map((r) => (
                <span key={r.side} className={`tag ${r.side}`} title={r.mix || undefined}>
                  {r.label} {r.role}
                  {r.declared && ' · зарласан'}
                  {r.fit && ` · ${r.fit}`}
                </span>
              ))}
            </h3>
            {card.roles.some((r) => r.mix && !r.declared) && (
              <p className="cap">
                Үүргийн холимог:{' '}
                {card.roles
                  .filter((r) => r.mix && !r.declared)
                  .map((r) => `${r.label} ${r.mix}`)
                  .join(' — ')}
              </p>
            )}
            {card.own && (
              <p className="why">
                {card.elsewhere ? `${card.elsewhere}-д тоглосон тоо` : 'Өөрсдийн тоглолт'}: {card.own.rounds} раунд · ADR {card.own.adr} · K/D {card.own.kd} · KAST{' '}
                {card.own.kast_pct}% · нээлт {card.own.opening_win_pct}% ({card.own.opening_kills}–
                {card.own.opening_deaths}) · толгой {card.own.hs_pct}%
              </p>
            )}
            {card.vs && (
              <p className="why">
                Энэ багийн эсрэг: {card.vs.rounds} раунд · ADR {card.vs.adr} · K/D {card.vs.kd} · KAST {card.vs.kast_pct}%
                · нээлт {card.vs.opening_win_pct}%
              </p>
            )}
            {!card.own && !card.vs && <p className="none">Задлан шинжилсэн раунд байхгүй.</p>}
            <Proven proven={card.proven} />
            {card.instructions.length ? (
              <div className="ins">
                {card.instructions.map((i, n) => (
                  <div key={n} className={`i ${i.tone}`}>
                    <b>{i.title}</b>
                    <span>{i.text}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="none" style={{ marginTop: 10 }}>
                Тоо дэмжсэн зөвлөмж гарсангүй — раунд хүрэлцэхгүй.
              </p>
            )}
          </div>
          {data.hidden.length > 0 && (
            <div className="caution">
              Аль ч тал одоо тоглуулахгүй байгаа тул хасагдсан: {data.hidden.join(', ')}. Тэдний тоо бол бэлтгэл биш,
              түүх.
            </div>
          )}
        </>
      ) : (
        <p className="none">Задлан шинжилсэн тоглогч байхгүй.</p>
      )}
    </section>
  )
}

// ------------------------------------------------------------------ duels ---
export function Duels({ data }: { data: DuelsPanel }) {
  const gone = [...data.dropped.mine, ...data.dropped.theirs]
  return (
    <section className="panel">
      <h2>Дуэль — хоорондын мапууд</h2>
      {data.has_rows ? (
        <>
          <div className="figure">
            <Chart svg={data.chart} />
            <p className="cap">
              Багууд хоорондын алалт. Мөр манай тоглогч, багана тэдний. 4-өөс доош дуэльтэй хос нь хандлага биш —
              тэмдэглэгдсэн.
            </p>
          </div>
          <div className="tw">
            <table className="setup">
              <thead>
                <tr>
                  <th>Манай тоглогч</th>
                  <th>Ал</th>
                  <th>Үхэл</th>
                  <th>Зөрүү</th>
                  <th>Дуэль</th>
                </tr>
              </thead>
              <tbody>
                {data.totals.map((t) => (
                  <tr key={t.name}>
                    <td>{t.name}</td>
                    <td className="mono">{t.for}</td>
                    <td className="mono">{t.against}</td>
                    <td className="mono" style={{ color: tone(t.net) }}>
                      {t.net}
                    </td>
                    <td className="mono">{t.duels}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {gone.length > 0 && (
            <div className="caution">
              Аль ч тал одоо тоглуулахгүй байгаа тул хасагдсан: {gone.join(', ')}. Тэдний дуэль бол бэлтгэл биш, түүх.
            </div>
          )}
        </>
      ) : (
        <p className="none">Хоорондын задлан шинжилсэн мап байхгүй тул дуэль гарсангүй.</p>
      )}
    </section>
  )
}

// ------------------------------------------------------------------ roles ---
export function Roles({ data }: { data: RolesPanel }) {
  return (
    <section className="panel">
      <h2>Үүрэг — ижил ажил дээр хүн хүнээр</h2>
      {data.comparison.length ? (
        <>
          <div className="figure">
            <Chart svg={data.chart} />
            <p className="cap">
              Ижил үүрэг дээрх хоёр хүний тохирлын зөрүү. Үүргийг задлан шинжилсэн бүх мапын сантай харьцуулж
              тодорхойлсон — таван хүнийг бие биетэй харьцуулбал нэвтрэлт хийдэггүй багт ч "нэвтрэгч" үргэлж гарна.
            </p>
          </div>
          <div className="tw">
            <table className="setup">
              <thead>
                <tr>
                  <th>Тал</th>
                  <th>Үүрэг</th>
                  <th>Манай</th>
                  <th>Тэдний</th>
                  <th>Зөрүү</th>
                </tr>
              </thead>
              <tbody>
                {data.comparison.map((r, i) => (
                  <tr key={i}>
                    <td>
                      <span className={`tag ${r.side}`}>{r.side_label}</span>
                    </td>
                    <td>{r.role}</td>
                    <td>
                      {r.mine} <span className="mono">{fmt2(r.mine_fit)}</span>
                    </td>
                    <td>
                      {r.theirs ? (
                        <>
                          {r.theirs} <span className="mono">{fmt2(r.theirs_fit)}</span>
                        </>
                      ) : (
                        <span className="tag unknown">харьцуулах хүнгүй</span>
                      )}
                    </td>
                    <td className="mono" style={{ color: r.delta !== null ? tone(r.delta) : undefined }}>
                      {r.delta !== null ? r.delta : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <p className="none">Хоёр талын үүргийг харьцуулах өгөгдөл хүрэлцсэнгүй.</p>
      )}

      {data.teams.map((sec) => (
        <section key={sec.scope} className={`scope ${sec.scope}`}>
          <h3>
            {sec.team} — {sec.maps} мап
          </h3>
          {sec.missing.map((m) => (
            <div key={m.side} className="caution">
              <b>{m.label}</b> — хэн ч гүйцэтгэхгүй байна:{' '}
              {m.roles.map((r) => (
                <span key={r} className="tag unknown" style={{ marginRight: 4 }}>
                  {r}
                </span>
              ))}
            </div>
          ))}
          {sec.players.map((p) => (
            <div key={p.name} className="card2" style={{ marginTop: 10 }}>
              <h3>
                {p.name}
                {p.elsewhere && <span className="tag">шинэ · {p.elsewhere}-д тоглосноор</span>}
                {p.rating !== null && (
                  <span
                    className="mono"
                    style={{ color: p.rating > 0.2 ? 'var(--good)' : p.rating < -0.4 ? 'var(--crit)' : undefined }}
                  >
                    {p.rating.toFixed(2)}
                  </span>
                )}
              </h3>
              <p className="why">
                {p.rounds} раунд · ADR {p.adr} · K/D {p.kd_ratio}
              </p>
              {p.sides.map((s) => (
                <Fragment key={s.side}>
                  <p className="why">
                    <span className={`tag ${s.side}`}>{s.label}</span> <b>{s.role}</b>{' '}
                    <span className="mono">{s.confidence}</span>
                    {s.fit_score !== null &&
                      ` · ${s.fit} (${s.fit_score.toFixed(2)}, ${s.cohort_size} хүнтэй харьцуулав)`}
                  </p>
                  <p className="places">{s.blurb}</p>
                  {s.evidence.length > 0 && (
                    <p className="places">
                      {s.evidence.map((e, i) => (
                        <Fragment key={e.signal}>
                          <b>{e.signal}</b> {String(e.value)} <i>z{e.z.toFixed(1)}</i>
                          {i < s.evidence.length - 1 && ' · '}
                        </Fragment>
                      ))}
                    </p>
                  )}
                </Fragment>
              ))}
            </div>
          ))}
        </section>
      ))}
    </section>
  )
}

// ------------------------------------------------------------------- edge ---
export function Edge({ data }: { data: EdgePanel }) {
  return (
    <section className="panel">
      <h2>Тулгуур тоглогч ба тооны илүүрэл</h2>
      <p className="cap" style={{ marginBottom: 14 }}>
        Хоёулаа самбар дээр байхгүй тоо. Эхнийх нь "хэнийг эхэлж алах вэ", хоёр дахь нь "илүү тоогоо раунд болгож
        чадаж байна уу" гэсэн асуултын хариу.
      </p>
      {data.teams.map((t) => (
        <section key={t.scope} className={`scope ${t.scope}`}>
          <h3>{t.team}</h3>
          {t.man_advantage ? (
            <div className="statrow">
              <div
                className={`stat ${t.man_advantage.up.win_pct >= 70 ? 'ok' : t.man_advantage.up.win_pct <= 55 ? 'bad' : ''}`}
              >
                <b>{t.man_advantage.up.win_pct}%</b>
                <span>илүү тоотой ({t.man_advantage.up.reached} раунд)</span>
              </div>
              <div className={`stat ${t.man_advantage.down.win_pct >= 25 ? 'ok' : ''}`}>
                <b>{t.man_advantage.down.win_pct}%</b>
                <span>дутуу тоотой ({t.man_advantage.down.reached} раунд)</span>
              </div>
            </div>
          ) : (
            <p className="none">Тооны илүүрлийг хэмжих раунд хүрэлцсэнгүй.</p>
          )}
          {t.linchpins.length ? (
            <>
              <div className="tw" style={{ marginTop: 12 }}>
                <table className="setup">
                  <thead>
                    <tr>
                      <th>Тоглогч</th>
                      <th>Эрт үхсэн раунд</th>
                      <th>Тэр раундын хожил</th>
                      <th>Бусад раунд</th>
                      <th>Ялгаа</th>
                      <th>Багийнхнаас</th>
                    </tr>
                  </thead>
                  <tbody>
                    {t.linchpins.map((p) => (
                      <tr key={p.player_id}>
                        <td>{p.name}</td>
                        <td className="mono">{p.early_deaths}</td>
                        <td className="mono">{p.early_pct}%</td>
                        <td className="mono">
                          {p.other_pct}% ({p.other_rounds})
                        </td>
                        <td className="mono">{p.swing}</td>
                        <td className="mono" style={{ color: p.significant ? 'var(--crit)' : undefined }}>
                          {p.vs_teammates > 0 ? '+' : ''}
                          {p.vs_teammates} ({p.first_deaths}){p.significant ? ' ✓' : ''}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="cap">
                "Эрт" гэдэг нь фризийн дараах 30 секунд — задлан шинжилсэн түүврийн нээлтийн тулааны дундажаас (29.5с)
                хойно. Ялгаа нь тэр тоглогч эрт унасан раундад багийн хожил хэдэн пунктээр унадаг нь. Багийнхнаас: баг
                эхний хүнээ эрт алдсан раундуудад тэр нь энэ тоглогч байхад хожил хэдэн пунктээр илүү унадаг нь (хаалтанд тийм
                раундын тоо), Side ба buy-аар тэнцүүлсэн; ✓ нь санамсаргүй тохиолдлоос давсан (permutation test, тоглогч олон тул FDR 10%). Зөвхөн
                ✓-тэй нь Шийдвэрийн хөшүүрэг болно.
              </p>
            </>
          ) : (
            <p className="none" style={{ marginTop: 8 }}>
              Ямар ч тоглогчид найдвартай дүгнэлт хийхэд хүрэлцэх эрт үхэл байхгүй (8-аас доош).
            </p>
          )}
        </section>
      ))}
    </section>
  )
}

import { keepPreviousData, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { Link, Navigate, useLocation, useNavigate, useParams, useSearchParams } from 'react-router'
import { $api } from '../api/client'
import type { components } from '../api/schema'
import '../gameplan/gameplan.css'
import { lineupQuery, lineupSearch, readLineups } from '../gameplan/lineup'
import { LineupPicker } from '../gameplan/LineupPicker'
import MapGrid from '../gameplan/MapGrid'
import { TodoTab } from '../gameplan/Playbook'
import {
  Decision,
  Duels,
  Edge,
  type Fixture,
  H2H,
  Maps,
  Metrics,
  Players,
  Roles,
  Verdict,
} from '../gameplan/panels'
import type * as T from '../gameplan/types'
import { useElapsed } from '../gameplan/useElapsed'

type Panel = components['schemas']['GameplanPanel']
type Tab = components['schemas']['GameplanTab']
type Header = components['schemas']['GameplanHeader']

const STALE = 5 * 60_000

// The match-preparation page for one fixture, one panel per URL (cstat's
// gameplan view). The header comes once; each panel is its own request, so a
// tab only pays for what it shows. While a panel loads the previous one stays on
// screen, dimmed, under a progress bar; every other tab is warmed in the
// background one at a time, and the nav marks which are ready.
export default function GameplanPage() {
  const params = useParams()
  const mine = Number(params.mine)
  const theirs = Number(params.theirs)
  const queryClient = useQueryClient()
  // The picked Lineups ride on the URL, so every request and link carries them.
  const [searchParams] = useSearchParams()
  const lineups = readLineups(searchParams)
  const search = lineupSearch(lineups)
  const query = useMemo(() => lineupQuery(readLineups(new URLSearchParams(search))), [search])

  const header = $api.useQuery(
    'get',
    '/gameplan/{mine}/vs/{theirs}',
    { params: { path: { mine, theirs }, query } },
    { staleTime: STALE },
  )
  const tab = params.tab ?? header.data?.default_tab ?? 'decision'
  const tabs = useMemo(() => header.data?.tabs ?? [], [header.data])
  const known = !header.data || tabs.some((t) => t.key === tab)

  const optionsFor = useMemo(
    () => (key: string) =>
      $api.queryOptions('get', '/gameplan/{mine}/vs/{theirs}/s/{tab}', {
        params: { path: { mine, theirs, tab: key }, query },
      }),
    [mine, theirs, query],
  )
  const panel = useQuery({
    ...optionsFor(tab),
    enabled: header.isSuccess && known,
    staleTime: STALE,
    placeholderData: keepPreviousData,
  })
  // Observers only: they never fetch, they watch what the panel query, a hover
  // or the warm-up put in the cache, so the nav can say which tabs are ready.
  const statuses = useQueries({
    queries: tabs.map((t) => ({ ...optionsFor(t.key), enabled: false, staleTime: STALE })),
  })

  // Warm the rest once the open panel is in: sequentially, so the server is
  // computing one section at a time and the reader's own clicks are not queued
  // behind eleven others.
  const settled = panel.isSuccess && !panel.isPlaceholderData
  useEffect(() => {
    if (!settled || !tabs.length) return
    let cancelled = false
    ;(async () => {
      for (const t of tabs) {
        if (cancelled) return
        const options = optionsFor(t.key)
        if (queryClient.getQueryData(options.queryKey)) continue
        await queryClient.prefetchQuery({ ...options, staleTime: STALE }).catch(() => {})
      }
    })()
    return () => {
      cancelled = true
    }
  }, [settled, tabs, optionsFor, queryClient])

  useEffect(() => {
    if (header.data) document.title = `${header.data.my_team.name} vs ${header.data.opponent.name} — game plan`
    return () => {
      document.title = 'cs-analyze'
    }
  }, [header.data])

  const status = header.error as { detail?: string } | null
  if (header.error && status?.detail === 'Pick two different teams') return <Navigate to="/gameplan" replace />
  if (header.error && search)
    return (
      <p className="text-crit">
        Lineup-ийг уншиж чадсангүй: {status?.detail ?? 'алдаа'}.{' '}
        <Link className="underline" to={`/gameplan/${mine}/vs/${theirs}`}>
          Lineup-гүйгээр нээх
        </Link>
      </p>
    )
  if (header.error) return <p className="text-crit">Баг олдсонгүй.</p>
  if (!known) return <p className="text-crit">Ийм хэсэг алга: {tab}</p>

  const fixture: Fixture | null = header.data
    ? { mine: header.data.my_team, theirs: header.data.opponent, tabs, search, query }
    : null
  const ready = statuses.filter((s) => s.data).length
  const label = tabs.find((t) => t.key === tab)?.label ?? tab
  const loading = !header.data || panel.isPending || panel.isPlaceholderData

  return (
    <div className="gp-page">
      <p className="mb-2 font-mono text-xs text-ink-3">
        <Link to="/gameplan" className="hover:underline">
          Game plan
        </Link>{' '}
        /
      </p>
      {fixture && header.data ? (
        <div>
          <h1>
            {fixture.mine.name} <span style={{ color: 'var(--ink-3)' }}>—</span> {fixture.theirs.name}
          </h1>
          <p className="lede">
            Тоглолтын бэлтгэл. Манай {header.data.lede.my_maps}, тэдний {header.data.lede.opponent_maps} газрын зураг,
            хоорондын {header.data.lede.h2h_maps} газрын зураг дээр тулгуурлав.{' '}
            <Link to={`/gameplan/${mine}/vs/${theirs}/briefing${search}`} className="text-ct hover:underline">
              Briefing бэлдэх →
            </Link>
          </p>
        </div>
      ) : (
        <div>
          <h1 className="text-ink-3">Фикстурыг уншиж байна…</h1>
          <p className="lede">Хоёр багийн задлан шинжилсэн мапуудыг тоолж байна.</p>
        </div>
      )}

      {header.data && <LineupBar header={header.data} />}

      <div className="keys">
        <span className="k">
          <i className="sw" style={{ background: 'var(--mark-mine)' }} /> {fixture?.mine.name ?? '…'} — манай баг
        </span>
        <span className="k">
          <i className="sw" style={{ background: 'var(--mark-theirs)' }} /> {fixture?.theirs.name ?? '…'} — эсрэг баг
        </span>
        <span className="k">
          <i className="sw" style={{ background: 'var(--mark-h2h)' }} /> хоорондын тоглолт
        </span>
      </div>

      <div className="gp">
        <aside className="gp-side">
          {[
            [1, 'Тойм'],
            [2, 'Задлан шинжилгээ'],
            [3, 'Үйлдэл'],
          ].map(([grp, title]) => (
            <div key={grp}>
              <div className="grp">{title}</div>
              {tabs
                .map((t, i) => [t, statuses[i]] as const)
                .filter(([t]) => t.grp === grp)
                .map(([t, s]) => (
                  <NavItem
                    key={t.key}
                    tab={t}
                    fixture={{ mine, theirs, search }}
                    on={t.key === tab}
                    busy={s?.fetchStatus === 'fetching' || (t.key === tab && panel.isFetching)}
                    ready={!!s?.data}
                    onHover={() => queryClient.prefetchQuery({ ...optionsFor(t.key), staleTime: STALE })}
                  />
                ))}
            </div>
          ))}
        </aside>

        <div className="gp-main">
          <Progress
            loading={loading}
            label={label}
            panel={panel.isPlaceholderData ? undefined : (panel.data as Panel | undefined)}
            failed={panel.isError}
            ready={ready}
            total={tabs.length}
            onRetry={() => panel.refetch()}
          />
          {fixture && panel.data && (
            <div className={panel.isPlaceholderData ? 'panel stale' : undefined}>
              <PanelBody panel={panel.data as Panel} fixture={fixture} map={params.map} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function NavItem({
  tab,
  fixture,
  on,
  busy,
  ready,
  onHover,
}: {
  tab: Tab
  fixture: { mine: number; theirs: number; search: string }
  on: boolean
  busy: boolean
  ready: boolean
  onHover: () => void
}) {
  return (
    <Link
      to={`/gameplan/${fixture.mine}/vs/${fixture.theirs}/s/${tab.key}${fixture.search}`}
      className={on ? 'on' : undefined}
      onMouseEnter={onHover}
      onFocus={onHover}
      title={busy ? 'Тооцоолж байна…' : ready ? 'Бэлэн' : undefined}
    >
      <span className={`st ${busy ? 'busy' : ready ? 'ready' : ''}`} aria-hidden="true" />
      {tab.label}
      {tab.n ? <span className="n">{tab.n}</span> : null}
    </Link>
  )
}

// Both Lineups the plan was built with, and an editor for them: applying it is
// a new URL, so the plan recomputes (or comes from cache) for that pair.
function LineupBar({ header }: { header: Header }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [editing, setEditing] = useState(false)
  const { mine, theirs } = header.lineups
  const [myFive, setMyFive] = useState<string[] | null>(null)
  const [theirFive, setTheirFive] = useState<string[] | null>(null)

  function open() {
    setMyFive(mine.picked ? mine.players.map((p) => p.steamid) : null)
    setTheirFive(theirs.picked ? theirs.players.map((p) => p.steamid) : null)
    setEditing(true)
  }
  function apply() {
    setEditing(false)
    navigate(`${location.pathname}${lineupSearch({ mine: myFive ?? [], theirs: theirFive ?? [] })}`)
  }

  const sides = [
    ['mine', header.my_team.name, mine],
    ['theirs', header.opponent.name, theirs],
  ] as const
  return (
    <div className="lu-bar">
      {sides.map(([scope, name, side]) => (
        <div key={scope} className="lu-side">
          <span className={`tag ${scope}`}>{name}</span>
          {side.players.map((p) => (
            <span key={p.steamid} className="lu-member" title={p.elsewhere ? `Тоо нь ${p.elsewhere}-аас` : undefined}>
              {p.name}
              {p.elsewhere && <small> · шинэ</small>}
            </span>
          ))}
          {!side.picked && <small className="lu-auto">сүүлийн тоглолтын 5</small>}
        </div>
      ))}
      {editing ? (
        <div className="lu-sides">
          <LineupPicker
            team={header.my_team}
            label="Манай Lineup"
            value={myFive}
            onChange={setMyFive}
            known={mine.players}
            taken={theirFive ?? []}
          />
          <LineupPicker
            team={header.opponent}
            label="Тэдний Lineup"
            value={theirFive}
            onChange={setTheirFive}
            known={theirs.players}
            taken={myFive ?? []}
          />
          <div className="lu-actions">
            <button
              type="button"
              className="lu-apply"
              disabled={myFive?.length === 0 || theirFive?.length === 0}
              onClick={apply}
            >
              Lineup-аар дахин тооцоолох
            </button>
            <button type="button" className="lu-reset" onClick={() => setEditing(false)}>
              болих
            </button>
          </div>
        </div>
      ) : (
        <button type="button" className="lu-reset" onClick={open}>
          Lineup засах
        </button>
      )}
    </div>
  )
}

// What is loading, for how long, and where the answer came from. The bar keeps
// running while a slow section computes, and says so in words with a clock,
// rather than a frozen page that might be broken.
function Progress({
  loading,
  label,
  panel,
  failed,
  ready,
  total,
  onRetry,
}: {
  loading: boolean
  label: string
  panel: Panel | undefined
  failed: boolean
  ready: number
  total: number
  onRetry: () => void
}) {
  const elapsed = useElapsed(loading && !failed)
  const warming = total > 0 && ready < total
  return (
    <div className="gp-progress" aria-live="polite">
      <div className={`bar ${loading && !failed ? '' : 'done'}`} style={{ opacity: loading || failed ? 1 : 0.35 }}>
        {(loading || !failed) && <i />}
      </div>
      <div className="txt">
        {failed ? (
          <span className="err">
            «{label}» хэсгийг тооцоолж чадсангүй.{' '}
            <button type="button" className="underline" onClick={onRetry}>
              Дахин оролдох
            </button>
          </span>
        ) : loading ? (
          <span>
            <b>«{label}»</b> хэсгийг тооцоолж байна… {elapsed.toFixed(1)}с
          </span>
        ) : panel ? (
          <span className="ok">
            «{label}» · {panel.cached ? 'кэшээс' : 'шинээр тооцоолсон'} · сервер {Math.round(panel.ms)}мс
          </span>
        ) : null}
        {total > 0 && (
          <span style={{ marginLeft: 'auto' }}>
            {warming ? `Бусад хэсгийг бэлдэж байна · ${ready}/${total}` : `Бүх ${total} хэсэг бэлэн`}
          </span>
        )}
      </div>
    </div>
  )
}

function PanelBody({ panel, fixture, map }: { panel: Panel; fixture: Fixture; map?: string }) {
  const d = panel.data as unknown
  switch (panel.tab) {
    case 'decision':
      return <Decision data={d as T.DecisionPanel} fixture={fixture} />
    case 'verdict':
      return <Verdict data={d as T.VerdictPanel} fixture={fixture} />
    case 'todo':
      return <TodoTab data={d as T.TodoPanel} fixture={fixture} map={map} />
    case 'metrics':
      return <Metrics data={d as T.MetricsPanel} fixture={fixture} />
    case 'h2h':
      return <H2H data={d as T.H2HPanel} />
    case 'maps':
      return <Maps data={d as T.MapsPanel} fixture={fixture} />
    case 'players':
      return <Players data={d as T.PlayersPanel} />
    case 'duels':
      return <Duels data={d as T.DuelsPanel} />
    case 'roles':
      return <Roles data={d as T.RolesPanel} />
    case 'edge':
      return <Edge data={d as T.EdgePanel} />
    case 'heatmaps':
    case 'movement': {
      const grid = d as T.GridPanel
      const heat = panel.tab === 'heatmaps'
      return (
        <section className="panel">
          <h2>{heat ? 'Heatmap — баг, тоглогч, map-аар харах' : 'Хөдөлгөөн — хаагуур явдаг вэ'}</h2>
          {grid.index.combinations ? (
            <>
              <p style={{ fontSize: 14, marginBottom: 12 }}>
                {heat ? (
                  <>
                    Тоглогч хаанаас kill авдаг, хаана үхдэг вэ — мапын өөрийнх нь хэлбэр дээр. Мап, баг, тоглогч, талаа
                    сонгоно уу; зургийг {grid.index.combinations}-ыг нь урьдчилан биш, асуусан үед нь зурна.
                  </>
                ) : (
                  <>
                    Тоглогч бүрийн байнга явдаг зам: дайрдаг цэгүүд нь цэгээр, нэр ба хувь нь замынхаа дэргэд. Хувь
                    гэдэг нь тухайн тоглогчийн <b>мөшгиж чадсан</b> раундын хэдэн хувьд энэ замаар явсныг хэлнэ — тоглосон
                    бүх раунд биш, учир нь эхний секундэд үхсэн раунд зам үлдээхгүй. Нэг замыг хэд хэдэн матчид явсныг
                    нэгтгэнэ; өөр мапыг хэзээ ч нэгтгэхгүй.
                  </>
                )}
              </p>
              <MapGrid
                key={`${fixture.mine.id}-${fixture.theirs.id}-${panel.tab}`}
                index={grid.index}
                words={grid.words}
                mine={fixture.mine.id}
                theirs={fixture.theirs.id}
                kind={heat ? 'heatmap' : 'movement'}
              />
            </>
          ) : (
            <div className="empty">
              {heat
                ? 'Зурах байрлал алга — энэ хоёр багийн боловсруулсан мапнаас хангалттай kill бүртгэгдээгүй байна.'
                : 'Зурах зам алга — энэ хоёр багийн боловсруулсан мапнаас хангалттай маршрут бүртгэгдээгүй байна.'}
            </div>
          )}
        </section>
      )
    }
    default:
      return null
  }
}

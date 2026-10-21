// The Stratbook (CONTEXT.md: Stratbook, Strat; docs/plans/08 SB-1): a my team's
// Strats, Map by Map and Side by Side. Staff write them; a Player login reads
// the active ones shared with the team.
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { $api } from '../api/client'
import { useMe, useMyTeams } from '../auth/useMe'
import { day } from '../jobs/format'
import { KINDS, type StratWrite } from '../strat/kinds'
import StratForm from '../strat/StratForm'

const kindLabel = (k: string) => KINDS.find(([key]) => key === k)?.[1] ?? k
const label = (m: string) => m.replace(/^de_/, '').replace(/^\w/, (c) => c.toUpperCase())
const STATUS: Record<string, string> = { draft: 'ноорог', active: 'идэвхтэй', retired: 'хуучирсан' }

export function StratbookPage() {
  const myTeams = useMyTeams()
  const staff = useMe().data?.role === 'staff'
  const [teamId, setTeamId] = useState<number | null>(null)
  const team = teamId ?? myTeams[0]?.id ?? null
  const maps = $api.useQuery('get', '/strats/maps')
  const strats = $api.useQuery('get', '/strats', { params: { query: team ? { team_id: team } : {} } })
  const cover = $api.useQuery('get', '/strats/coverage/{team_id}', { params: { path: { team_id: team ?? 0 } } }, { enabled: staff && !!team })
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-4">
        <h1 className="text-2xl font-semibold text-ink">Stratbook</h1>
        <Link to="/lineups" className="text-sm text-ct hover:underline">
          Lineup-ийн сан →
        </Link>
        <Link to="/search" className="text-sm text-ct hover:underline">
          Раунд хайх →
        </Link>
        {myTeams.length > 1 && (
          <select
            value={team ?? ''}
            onChange={(e) => setTeamId(Number(e.target.value))}
            className="rounded-md border border-line bg-surface-2 px-2 py-1 text-sm text-ink"
          >
            {myTeams.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        )}
      </div>
      {!strats.data || !maps.data ? (
        <p className="text-ink-3">Уншиж байна…</p>
      ) : (
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-ink-3">
            <tr>
              <th className="w-28 py-1 font-normal">Map</th>
              <th className="py-1 font-normal">T</th>
              <th className="py-1 font-normal">CT</th>
            </tr>
          </thead>
          <tbody>
            {maps.data.map((m) => (
              <tr key={m} className="border-t-1 border-line align-top">
                <td className="py-2 text-ink">
                  {label(m)}
                  {cover.data?.[m] && (
                    <span className="block text-xs text-ink-3" title="Идэвхтэй Strat · сүүлийн 30 хоногт тоглогдсон">
                      {cover.data[m].active} идэвхтэй · {cover.data[m].recent} туршсан
                    </span>
                  )}
                </td>
                {(['t', 'ct'] as const).map((side) => (
                  <td key={side} className="space-y-1 py-2 pr-4">
                    {strats.data
                      .filter((s) => s.map_name === m && s.side === side)
                      .map((s) => (
                        <Link
                          key={s.id}
                          to={`/stratbook/${s.id}`}
                          className={`block hover:underline ${s.status === 'active' ? 'text-ct' : 'text-ink-3'}`}
                        >
                          {s.name} <span className="text-xs text-ink-3">{kindLabel(s.kind)} · {STATUS[s.status]}</span>
                          {s.examples > 0 && <span className="ml-1 font-mono text-xs text-ink-3">{s.examples}R</span>}
                        </Link>
                      ))}
                    {staff && team && (
                      <Link to={`/stratbook/new?team=${team}&map=${m}&side=${side}`} className="block text-xs text-ink-3 hover:text-ink">
                        + Strat
                      </Link>
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export function StratNewPage() {
  const [search] = useSearchParams()
  const myTeams = useMyTeams()
  const maps = $api.useQuery('get', '/strats/maps')
  const navigate = useNavigate()
  const create = $api.useMutation('post', '/strats', { onSuccess: (s) => navigate(`/stratbook/${s.id}`) })
  if (!maps.data || !myTeams.length) return <p className="text-ink-3">Уншиж байна…</p>
  const initial: StratWrite = {
    team_id: Number(search.get('team')) || myTeams[0].id,
    map_name: search.get('map') || maps.data[0],
    side: search.get('side') === 'ct' ? 'ct' : 't',
    name: '',
    kind: 'default',
    description: '',
    roles: [],
    grenades: [],
    timings: '',
    variations: '',
    calls: '',
    tags: [],
    status: 'draft',
    visibility: 'staff',
  }
  return (
    <div className="space-y-4">
      <p className="font-mono text-xs text-ink-3">
        <Link to="/stratbook" className="hover:underline">
          Stratbook
        </Link>{' '}
        / шинэ
      </p>
      <h1 className="text-2xl font-semibold text-ink">Шинэ Strat</h1>
      <StratForm
        initial={initial}
        teams={myTeams}
        maps={maps.data}
        busy={create.isPending}
        error={(create.error as { detail?: string } | undefined)?.detail}
        onSave={(body) => create.mutate({ body })}
      />
    </div>
  )
}

export function StratPage() {
  const id = Number(useParams().stratId)
  const path = { params: { path: { strat_id: id } } }
  const strat = $api.useQuery('get', '/strats/{strat_id}', path)
  const myTeams = useMyTeams()
  const maps = $api.useQuery('get', '/strats/maps')
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [editing, setEditing] = useState(false)
  const [round, setRound] = useState({ match_id: '', map_number: '1', round: '' })
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['get', '/strats'] })
    void strat.refetch()
  }
  const save = $api.useMutation('put', '/strats/{strat_id}', {
    onSuccess: () => {
      setEditing(false)
      refresh()
    },
  })
  const addExample = $api.useMutation('post', '/strats/{strat_id}/examples', { onSuccess: refresh })
  const dropExample = $api.useMutation('delete', '/strats/{strat_id}/examples/{example_id}', { onSuccess: refresh })
  const remove = $api.useMutation('delete', '/strats/{strat_id}', {
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['get', '/strats'] })
      navigate('/stratbook')
    },
  })
  const printed = $api.useMutation('post', '/strats/{strat_id}/print')
  const match = $api.useMutation('post', '/strats/{strat_id}/match', { onSuccess: refresh })
  const confirm = $api.useMutation('post', '/strats/{strat_id}/examples/{example_id}/confirm', { onSuccess: refresh })
  const library = $api.useQuery(
    'get',
    '/lineups/{map_name}',
    { params: { path: { map_name: strat.data?.map_name ?? '' } } },
    { enabled: !!strat.data?.grenades.some((g) => g.lineup) },
  )
  if (strat.isError) return <p className="text-ink-2">Ийм Strat алга.</p>
  if (!strat.data) return <p className="text-ink-3">Уншиж байна…</p>
  const s = strat.data
  if (editing && maps.data) {
    const { id: _id, team, examples: _e, examples_list: _l, versions: _v, can_edit: _c, updated_at: _u, ...rest } = s
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold text-ink">{s.name} засах</h1>
        <StratForm
          initial={{ ...rest, team_id: team.id } as StratWrite}
          teams={myTeams}
          maps={maps.data}
          busy={save.isPending}
          error={(save.error as { detail?: string } | undefined)?.detail}
          onSave={(body) => save.mutate({ ...path, body })}
        />
        <button type="button" onClick={() => setEditing(false)} className="text-sm text-ink-3 hover:text-ink">
          Болих
        </button>
      </div>
    )
  }
  return (
    <article className="space-y-5">
      <p className="font-mono text-xs text-ink-3">
        <Link to="/stratbook" className="hover:underline">
          Stratbook
        </Link>{' '}
        / {label(s.map_name)} {s.side.toUpperCase()}
      </p>
      <header className="flex flex-wrap items-baseline gap-3">
        <h1 className="text-2xl font-semibold text-ink">{s.name}</h1>
        <span className="text-sm text-ink-3">
          {kindLabel(s.kind)} · {STATUS[s.status]} · {s.visibility === 'team' ? 'багт хуваалцсан' : 'зөвхөн Staff'} ·{' '}
          {day(s.updated_at)}
        </span>
        <span className="ml-auto flex gap-3 text-sm print:hidden">
          <button
            type="button"
            onClick={() => printed.mutate(path, { onSettled: () => window.print() })}
            className="text-ct underline"
          >
            Хэвлэх
          </button>
          {s.can_edit && (
            <button type="button" onClick={() => setEditing(true)} className="text-ct underline">
              Засах
            </button>
          )}
        </span>
      </header>
      {s.description && <p className="max-w-3xl whitespace-pre-line text-ink-2">{s.description}</p>}
      {s.roles.length > 0 && (
        <section className="space-y-1">
          <h2 className="font-medium text-ink">Slot бүрийн үүрэг</h2>
          <ul className="space-y-0.5 text-sm text-ink-2">
            {s.roles.map((r) => (
              <li key={r.slot}>
                <span className="mr-2 font-mono text-ink-3">{r.slot}</span>
                <b className="text-ink">{r.role}</b> {r.does}
              </li>
            ))}
          </ul>
        </section>
      )}
      {s.grenades.length > 0 && (
        <section className="space-y-1">
          <h2 className="font-medium text-ink">Граната</h2>
          <ul className="space-y-0.5 text-sm text-ink-2">
            {[...s.grenades]
              .sort((a, b) => (a.at ?? 999) - (b.at ?? 999))
              .map((g, i) => (
                <li key={i}>
                  <span className="mr-2 font-mono text-ink-3">{g.at != null ? `${g.at}с` : '—'}</span>
                  {g.slot ? `slot ${g.slot}: ` : ''}
                  <b className="text-ink">{g.type}</b> → {g.place || '?'} {g.note && <span className="text-ink-3">({g.note})</span>}
                  {g.lineup && library.data?.find((lu) => lu.key === g.lineup) && (
                    // The practice-server spot, printed on the card (SB-6).
                    <span className="ml-2 font-mono text-xs text-ink-3">
                      {library.data.find((lu) => lu.key === g.lineup)!.setpos}
                    </span>
                  )}
                </li>
              ))}
          </ul>
        </section>
      )}
      {(['timings', 'variations', 'calls'] as const).map((k) =>
        s[k] ? (
          <section key={k} className="space-y-1">
            <h2 className="font-medium text-ink">{{ timings: 'Timing', variations: 'Хувилбарууд', calls: 'Дуудлага' }[k]}</h2>
            <p className="max-w-3xl whitespace-pre-line text-sm text-ink-2">{s[k]}</p>
          </section>
        ) : null,
      )}
      <Report s={s} onMatch={s.can_edit ? () => match.mutate(path) : undefined} busy={match.isPending} />
      <section className="space-y-1">
        <h2 className="font-medium text-ink">Жишээ раундууд</h2>
        <ul className="space-y-0.5 text-sm">
          {s.examples_list.map((e) => (
            <li key={e.id}>
              <Link to={`/matches/${e.match_id}/m/${e.map_number}?round=${e.round}`} className="text-ct hover:underline">
                ▶ {e.label}
              </Link>
              {!e.confirmed && (
                <span className="ml-2 text-xs text-warn">
                  олдсон
                  {s.can_edit && (
                    <button
                      type="button"
                      onClick={() => confirm.mutate({ params: { path: { strat_id: id, example_id: e.id } } })}
                      className="ml-1 text-ct underline print:hidden"
                    >
                      батлах
                    </button>
                  )}
                </span>
              )}
              {e.note && <span className="ml-2 text-ink-3">{e.note}</span>}
              {s.can_edit && (
                <button
                  type="button"
                  onClick={() => dropExample.mutate({ params: { path: { strat_id: id, example_id: e.id } } })}
                  className="ml-2 text-xs text-ink-3 hover:text-crit print:hidden"
                >
                  ✕
                </button>
              )}
            </li>
          ))}
          {!s.examples_list.length && <li className="text-ink-3">Алга.</li>}
        </ul>
        {s.can_edit && (
          <form
            className="flex flex-wrap items-center gap-2 pt-1 text-sm print:hidden"
            onSubmit={(ev) => {
              ev.preventDefault()
              addExample.mutate({
                ...path,
                body: { match_id: Number(round.match_id), map_number: Number(round.map_number), round: Number(round.round), note: '' },
              })
            }}
          >
            <input
              placeholder="тоглолтын id"
              value={round.match_id}
              onChange={(e) => setRound({ ...round, match_id: e.target.value })}
              className="w-28 rounded-md border border-line bg-surface-2 px-2 py-1 text-ink"
            />
            <input
              placeholder="map"
              value={round.map_number}
              onChange={(e) => setRound({ ...round, map_number: e.target.value })}
              className="w-14 rounded-md border border-line bg-surface-2 px-2 py-1 text-ink"
            />
            <input
              placeholder="раунд"
              value={round.round}
              onChange={(e) => setRound({ ...round, round: e.target.value })}
              className="w-16 rounded-md border border-line bg-surface-2 px-2 py-1 text-ink"
            />
            <button type="submit" className="text-ct hover:underline">
              + жишээ
            </button>
            {addExample.isError && <span className="text-crit">Ийм раунд олдсонгүй.</span>}
          </form>
        )}
      </section>
      {s.can_edit && <StaffTrail id={id} versions={s.versions} onDelete={() => remove.mutate(path)} />}
    </article>
  )
}

type Read = NonNullable<ReturnType<typeof useStrat>['data']>
const useStrat = (id: number) => $api.useQuery('get', '/strats/{strat_id}', { params: { path: { strat_id: id } } })

/** How it did over its kept Rounds (SB-4), and finding more. */
function Report({ s, onMatch, busy }: { s: Read; onMatch?: () => void; busy: boolean }) {
  const r = s.report
  const share = (t?: { played: number; won: number } | null) => (t && t.played ? `${t.won}/${t.played}` : '—')
  return (
    <section className="space-y-1 text-sm">
      <h2 className="font-medium text-ink">Гүйцэтгэл</h2>
      {r.played === 0 ? (
        <p className="text-ink-3">Тоглогдсон раунд алга.</p>
      ) : (
        <p className="text-ink-2">
          {r.played} удаа, <b className="text-ink">{r.won}</b> хожил ({Math.round((100 * r.won) / r.played)}%, 80%: {r.low}–{r.high}%)
          · official {share(r.official)} · Scrim {share(r.scrim)}
          {r.last && ` · сүүлд ${r.last}`}
          {r.pending > 0 && <span className="text-warn"> · {r.pending} батлагдаагүй</span>}
          <br />
          <span className="text-xs text-ink-3">
            Buy-аар: {Object.entries(r.by_buy).map(([k, v]) => `${k} ${v.won}/${v.played}`).join(', ')}
          </span>
        </p>
      )}
      {onMatch && (
        <button type="button" disabled={busy} onClick={onMatch} className="text-ct underline print:hidden">
          {busy ? 'Хайж байна…' : 'Тоглогдсон раундыг гранатаар нь хайх'}
        </button>
      )}
    </section>
  )
}

/** Who read, printed or changed it, and the Strat as it was (SB-7). Staff only. */
function StaffTrail({ id, versions, onDelete }: { id: number; versions: number; onDelete: () => void }) {
  const [open, setOpen] = useState(false)
  const events = $api.useQuery('get', '/strats/{strat_id}/events', { params: { path: { strat_id: id } } }, { enabled: open })
  const old = $api.useQuery('get', '/strats/{strat_id}/versions', { params: { path: { strat_id: id } } }, { enabled: open })
  return (
    <section className="space-y-2 border-t-1 border-line pt-3 text-sm print:hidden">
      <button type="button" onClick={() => setOpen(!open)} className="text-ink-3 hover:text-ink">
        {open ? '▾' : '▸'} Бүртгэл · {versions} өмнөх хувилбар
      </button>
      {open && (
        <div className="grid gap-4 sm:grid-cols-2">
          <ul className="space-y-0.5 text-xs text-ink-2">
            {(events.data ?? []).map((e, i) => (
              <li key={i}>
                <span className="font-mono text-ink-3">{day(e.at)}</span> {e.user} — {e.action}
              </li>
            ))}
          </ul>
          <ul className="space-y-0.5 text-xs text-ink-2">
            {(old.data ?? []).map((v) => (
              <li key={v.id}>
                <span className="font-mono text-ink-3">{day(v.created_at)}</span> {v.created_by}: «{String(v.payload.name ?? '')}»
              </li>
            ))}
          </ul>
          <button type="button" onClick={onDelete} className="justify-self-start text-xs text-ink-3 hover:text-crit">
            Strat-ийг устгах
          </button>
        </div>
      )}
    </section>
  )
}

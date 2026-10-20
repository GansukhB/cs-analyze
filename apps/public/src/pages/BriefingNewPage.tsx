// Making a Briefing (docs/plans/01 WS-5): Staff tick the Playbook lines the Players
// should get, Map by Map in veto order, add notes, and choose whether the Forecast
// goes in (off by default). Saving freezes the lines as the Game Plan says them now.
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { $api } from '../api/client'
import { type PickLine, pickLines } from '../briefing/lines'
import { lineupQuery, readLineups } from '../gameplan/lineup'
import type { PlaybookMap, PlaybookPanel, TodoPanel } from '../gameplan/types'

const field = 'w-full rounded-md border border-line bg-surface-2 px-3 py-2 text-sm text-ink'

export default function BriefingNewPage() {
  const params = useParams()
  const mine = Number(params.mine)
  const theirs = Number(params.theirs)
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const query = useMemo(() => lineupQuery(readLineups(searchParams)), [searchParams])
  const header = $api.useQuery('get', '/gameplan/{mine}/vs/{theirs}', { params: { path: { mine, theirs }, query } })
  const todo = $api.useQuery('get', '/gameplan/{mine}/vs/{theirs}/s/{tab}', {
    params: { path: { mine, theirs, tab: 'todo' }, query },
  })
  const [title, setTitle] = useState('')
  const [note, setNote] = useState('')
  const [forecast, setForecast] = useState(false)
  const [picks, setPicks] = useState<Record<string, string[]>>({})
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [open, setOpen] = useState<string | null>(null)
  const save = $api.useMutation('post', '/briefings', {
    onSuccess: (b) => navigate(`/briefings/${b.id}`),
  })
  const [checks, setChecks] = useState<Record<string, string[]>>({})
  const draft = $api.useMutation('post', '/briefings/draft', {
    onSuccess: (d) => {
      setNote(d.note)
      setNotes((prev) => ({ ...prev, ...d.maps }))
      setChecks(d.unverified)
    },
  })

  if (!header.data || !todo.data) return <p className="text-ink-3">Game Plan-ийг уншиж байна…</p>
  const maps = (todo.data.data as unknown as TodoPanel).maps
  const ids = (raw?: string) => (raw ? raw.split(',').filter(Boolean) : [])
  const total = Object.values(picks).reduce((n, l) => n + l.length, 0)

  function body(share: boolean) {
    return {
      my_team_id: mine,
      opponent_id: theirs,
      my_lineup: ids(query.my_lineup),
      their_lineup: ids(query.their_lineup),
      title: title.trim() || `${header.data!.my_team.name} vs ${header.data!.opponent.name}`,
      note,
      include_forecast: forecast,
      stamp: header.data!.stamp,
      share,
      maps: maps
        .map((m) => ({ map: m.map, note: notes[m.map] ?? '', picks: picks[m.map] ?? [] }))
        .filter((m) => m.picks.length || m.note.trim()),
    }
  }
  function submit(share: boolean) {
    save.mutate({ body: body(share) })
  }
  const error =
    (save.error as { detail?: string } | undefined)?.detail ?? (draft.error as { detail?: string } | undefined)?.detail
  const flagged = Object.entries(checks)

  return (
    <div className="space-y-6">
      <p className="font-mono text-xs text-ink-3">
        <Link to={`/gameplan/${mine}/vs/${theirs}?${searchParams}`} className="hover:underline">
          {header.data.my_team.name} — {header.data.opponent.name}
        </Link>{' '}
        / Briefing
      </p>
      <h1 className="text-2xl font-semibold text-ink">Briefing бэлдэх</h1>
      <p className="max-w-2xl text-sm text-ink-2">
        Тоглогчдод өгөх мөрүүдээ Map бүрээс сонгоно. Хадгалсны дараа Briefing өөрчлөгдөхгүй: шинэ demo parse хийгдсэн ч
        тохиролцсон төлөвлөгөө хэвээр үлдэнэ.
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block space-y-1 text-sm">
          <span className="text-ink-3">Гарчиг</span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={160}
            placeholder={`${header.data.my_team.name} vs ${header.data.opponent.name}`}
            className={field}
          />
        </label>
        <label className="flex items-end gap-2 pb-2 text-sm text-ink-2">
          <input type="checkbox" checked={forecast} onChange={(e) => setForecast(e.target.checked)} />
          Forecast-ыг оруулах
        </label>
      </div>
      <label className="block space-y-1 text-sm">
        <span className="text-ink-3">Ерөнхий тэмдэглэл</span>
        <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} maxLength={4000} className={field} />
      </label>

      <div className="space-y-2">
        {maps.map((m) => (
          <MapPicker
            key={m.map}
            map={m}
            mine={mine}
            theirs={theirs}
            query={query}
            open={open === m.map}
            onToggle={() => setOpen(open === m.map ? null : m.map)}
            picked={picks[m.map] ?? []}
            onPick={(list) => setPicks({ ...picks, [m.map]: list })}
            note={notes[m.map] ?? ''}
            onNote={(text) => setNotes({ ...notes, [m.map]: text })}
          />
        ))}
      </div>

      {flagged.length > 0 && (
        <p className="rounded-md border-l-2 border-warn bg-surface px-4 py-2 text-sm text-ink-2">
          Ноорогт сонгосон мөрүүдэд байхгүй тоо байна, хадгалахаас өмнө шалгаарай:{' '}
          {flagged.map(([where, nums]) => `${where === 'note' ? 'ерөнхий' : where.replace('de_', '')}: ${nums.join(', ')}`).join('; ')}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span className="text-ink-3">{total} мөр сонгосон</span>
        <button
          type="button"
          disabled={draft.isPending || total === 0}
          onClick={() => draft.mutate({ body: body(false) })}
          className="rounded-md border border-line bg-raised px-4 py-2 text-ink hover:border-ink-3 disabled:opacity-50"
        >
          {draft.isPending ? 'Ноорог бичиж байна…' : 'Assistant-аар тэмдэглэлийн ноорог'}
        </button>
        <button
          type="button"
          disabled={save.isPending}
          onClick={() => submit(false)}
          className="rounded-md border border-line bg-raised px-4 py-2 text-ink hover:border-ink-3 disabled:opacity-50"
        >
          Ноорог болгон хадгалах
        </button>
        <button
          type="button"
          disabled={save.isPending}
          onClick={() => submit(true)}
          className="rounded-md bg-ct px-4 py-2 font-medium text-ground hover:brightness-110 disabled:opacity-50"
        >
          Хадгалж тоглогчдод хуваалцах
        </button>
        {error && <span className="text-crit">{error}</span>}
      </div>
    </div>
  )
}

function MapPicker(props: {
  map: PlaybookMap
  mine: number
  theirs: number
  query: { my_lineup?: string; their_lineup?: string }
  open: boolean
  onToggle: () => void
  picked: string[]
  onPick: (list: string[]) => void
  note: string
  onNote: (text: string) => void
}) {
  const { map, mine, theirs, query, open, picked } = props
  const panel = useQuery({
    ...$api.queryOptions('get', '/gameplan/{mine}/vs/{theirs}/playbook/{map_name}', {
      params: { path: { mine, theirs, map_name: map.map }, query },
    }),
    enabled: open,
    staleTime: 5 * 60_000,
  })
  const lines = panel.data ? pickLines(panel.data.data as unknown as PlaybookPanel) : []
  const groups = lines.reduce<Record<string, PickLine[]>>((acc, l) => {
    ;(acc[l.group] ??= []).push(l)
    return acc
  }, {})
  const toggle = (path: string) =>
    props.onPick(picked.includes(path) ? picked.filter((p) => p !== path) : [...picked, path])
  return (
    <section className="rounded-xl border border-line bg-surface">
      <button type="button" onClick={props.onToggle} className="flex w-full items-center gap-3 px-4 py-3 text-left">
        <span className="font-medium text-ink">{map.label}</span>
        <span className="text-xs text-ink-3">{map.call_label}</span>
        <span className="ml-auto text-xs text-ink-3">{picked.length ? `${picked.length} мөр` : ''}</span>
      </button>
      {open && (
        <div className="space-y-4 border-t-1 border-line px-4 py-3 text-sm">
          {!panel.data ? (
            <p className="text-ink-3">{panel.isError ? 'Playbook-ийг уншиж чадсангүй.' : 'Playbook-ийг бодож байна…'}</p>
          ) : lines.length === 0 ? (
            <p className="text-ink-3">Энэ Map-д сонгох мөр алга.</p>
          ) : (
            Object.entries(groups).map(([group, items]) => (
              <div key={group} className="space-y-1">
                <p className="text-xs uppercase tracking-wide text-ink-3">{group}</p>
                {items.map((l) => (
                  <label key={l.path} className="flex gap-2 text-ink-2">
                    <input type="checkbox" checked={picked.includes(l.path)} onChange={() => toggle(l.path)} />
                    <span>
                      <span className="text-ink">{l.title}</span>
                      {l.sub && <span className="block text-xs text-ink-3">{l.sub}</span>}
                    </span>
                  </label>
                ))}
              </div>
            ))
          )}
          <label className="block space-y-1">
            <span className="text-ink-3">{map.label}-ийн тэмдэглэл</span>
            <textarea
              value={props.note}
              onChange={(e) => props.onNote(e.target.value)}
              rows={2}
              maxLength={2000}
              className={field}
            />
          </label>
        </div>
      )}
    </section>
  )
}

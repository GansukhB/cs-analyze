// Playlists (docs/plans/07 RV-7): Rounds from any Match Map in a watching order,
// each with a line. Staff make them from a Finding's «+ Playlist» and share them;
// a Player sees the shared ones.
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { $api } from '../api/client'
import type { components } from '../api/schema'
import { useMe } from '../auth/useMe'
import { day } from '../jobs/format'
import { clock } from '../review/format'

type Item = components['schemas']['PlaylistItemRead']

export function PlaylistsPage() {
  const lists = $api.useQuery('get', '/playlists')
  const staff = useMe().data?.role === 'staff'
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold text-ink">Playlist</h1>
      {staff && (
        <p className="max-w-2xl text-sm text-ink-2">
          Match-ийн Review дээрх Finding-ийн «+ Playlist»-ээр раунд нэмнэ. Хуваалцсан playlist-ийг тоглогчид харна.
        </p>
      )}
      {!lists.data ? (
        <p className="text-ink-3">Уншиж байна…</p>
      ) : lists.data.length === 0 ? (
        <p className="text-sm text-ink-3">Playlist алга.</p>
      ) : (
        <ul className="divide-y divide-line rounded-xl border border-line bg-surface text-sm">
          {lists.data.map((p) => (
            <li key={p.id} className="flex flex-wrap items-baseline gap-x-4 px-4 py-2">
              <Link to={`/playlists/${p.id}`} className="font-medium text-ct hover:underline">
                {p.title}
              </Link>
              <span className="text-ink-3">{p.rounds} раунд</span>
              {staff && <span className={p.shared ? 'text-good' : 'text-ink-3'}>{p.shared ? 'хуваалцсан' : 'ноорог'}</span>}
              <span className="ml-auto text-xs text-ink-3">
                {p.created_by} · {day(p.updated_at)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function PlaylistPage() {
  const id = Number(useParams().playlistId)
  const path = { params: { path: { playlist_id: id } } }
  const playlist = $api.useQuery('get', '/playlists/{playlist_id}', path)
  const staff = useMe().data?.role === 'staff'
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [draft, setDraft] = useState<{ title: string; note: string; items: Item[] } | null>(null)
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ['get', '/playlists'] })
  const save = $api.useMutation('put', '/playlists/{playlist_id}', {
    onSuccess: () => {
      setDraft(null)
      refresh()
      void playlist.refetch()
    },
  })
  const remove = $api.useMutation('delete', '/playlists/{playlist_id}', {
    onSuccess: () => {
      refresh()
      navigate('/playlists')
    },
  })
  if (playlist.isError) return <p className="text-ink-2">Playlist олдсонгүй.</p>
  if (!playlist.data) return <p className="text-ink-3">Уншиж байна…</p>
  const p = playlist.data
  const editing = draft ?? { title: p.title, note: p.note, items: p.items }
  const strip = (items: Item[]) => items.map(({ label: _label, ...rest }) => rest)
  function put(shared: boolean, next = editing) {
    save.mutate({ ...path, body: { title: next.title, note: next.note, items: strip(next.items), shared } })
  }
  function move(i: number, dir: -1 | 1) {
    const items = [...editing.items]
    const j = i + dir
    if (j < 0 || j >= items.length) return
    ;[items[i], items[j]] = [items[j], items[i]]
    setDraft({ ...editing, items })
  }
  const href = (it: Item) => `/matches/${it.match_id}/m/${it.map_number}?round=${it.round}`
  return (
    <article className="space-y-4">
      <p className="font-mono text-xs text-ink-3">
        <Link to="/playlists" className="hover:underline">
          Playlist
        </Link>{' '}
        / {p.title}
      </p>
      {staff && draft ? (
        <input
          value={editing.title}
          onChange={(e) => setDraft({ ...editing, title: e.target.value })}
          maxLength={160}
          className="w-full rounded-md border border-line bg-surface-2 px-3 py-2 text-xl text-ink"
        />
      ) : (
        <h1 className="text-2xl font-semibold text-ink">{p.title}</h1>
      )}
      {staff && draft ? (
        <textarea
          value={editing.note}
          onChange={(e) => setDraft({ ...editing, note: e.target.value })}
          rows={2}
          maxLength={4000}
          className="w-full rounded-md border border-line bg-surface-2 px-3 py-2 text-sm text-ink"
        />
      ) : (
        p.note && <p className="max-w-2xl whitespace-pre-line text-sm text-ink-2">{p.note}</p>
      )}
      <ol className="space-y-2">
        {editing.items.map((it, i) => (
          <li key={`${it.match_id}-${it.map_number}-${it.round}-${i}`} className="flex gap-3 rounded-lg border border-line bg-surface p-3 text-sm">
            <span className="font-mono text-ink-3">{i + 1}.</span>
            <div className="min-w-0 flex-1 space-y-1">
              <div className="flex flex-wrap items-baseline gap-x-3">
                <Link to={href(it)} className="font-medium text-ct hover:underline">
                  ▶ R{it.round}
                  {it.t != null ? ` · ${clock(it.t)}` : ''}
                </Link>
                <span className="text-xs text-ink-3">{it.label}</span>
              </div>
              {staff && draft ? (
                <input
                  value={it.text}
                  onChange={(e) => {
                    const items = [...editing.items]
                    items[i] = { ...it, text: e.target.value }
                    setDraft({ ...editing, items })
                  }}
                  maxLength={1000}
                  className="w-full rounded-md border border-line bg-surface-2 px-2 py-1 text-ink"
                />
              ) : (
                it.text && <p className="text-ink-2">{it.text}</p>
              )}
            </div>
            {staff && draft && (
              <span className="flex shrink-0 items-start gap-1 text-xs text-ink-3">
                <button type="button" onClick={() => move(i, -1)} className="hover:text-ink">
                  ↑
                </button>
                <button type="button" onClick={() => move(i, 1)} className="hover:text-ink">
                  ↓
                </button>
                <button
                  type="button"
                  onClick={() => setDraft({ ...editing, items: editing.items.filter((_x, k) => k !== i) })}
                  className="hover:text-crit"
                >
                  ✕
                </button>
              </span>
            )}
          </li>
        ))}
      </ol>
      {staff && (
        <div className="flex flex-wrap items-center gap-3 text-sm print:hidden">
          {draft ? (
            <>
              <button type="button" disabled={save.isPending} onClick={() => put(p.shared)} className="rounded-md bg-ct px-4 py-2 font-medium text-ground">
                Хадгалах
              </button>
              <button type="button" onClick={() => setDraft(null)} className="text-ink-3 hover:text-ink">
                Болих
              </button>
            </>
          ) : (
            <button type="button" onClick={() => setDraft({ title: p.title, note: p.note, items: p.items })} className="rounded-md border border-line bg-raised px-4 py-2 text-ink">
              Засах
            </button>
          )}
          <button type="button" disabled={save.isPending} onClick={() => put(!p.shared, { title: p.title, note: p.note, items: p.items })} className="rounded-md border border-line bg-raised px-4 py-2 text-ink">
            {p.shared ? 'Хуваалцахаа болих' : 'Тоглогчдод хуваалцах'}
          </button>
          <button type="button" disabled={remove.isPending} onClick={() => remove.mutate(path)} className="ml-auto text-ink-3 hover:text-crit">
            Устгах
          </button>
        </div>
      )}
    </article>
  )
}

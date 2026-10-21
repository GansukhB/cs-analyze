// Staff's notes on a Review, Findings they dispute, and adding a Round to a
// Playlist (docs/plans/07 RV-7). The match page provides the context; a Finding
// card shows its actions only under it, and only to Staff.
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { $api, fetchClient } from '../api/client'
import type { components } from '../api/schema'
import type { ReplayBridge, Shape } from '../replay/player'
import type { PenHooks } from './notesContext'
import { CLIP_SECONDS, clock } from './format'
import { type Actions, NotesContext, useNotes } from './notesContext'
import type { Goto } from './MapReview'

type Finding = components['schemas']['ReviewFinding']
type Item = components['schemas']['PlaylistItem']


const findingKey = (code: string, round: number | null | undefined, sid: string | null | undefined) =>
  `${code}:${round ?? ''}:${sid ?? ''}`

export function NotesProvider(props: { matchId: number; mapNumber: number; staff: boolean; children: React.ReactNode }) {
  const { matchId, mapNumber, staff } = props
  const path = { params: { path: { match_id: matchId, map_number: mapNumber } } }
  const query = $api.useQuery('get', '/matches/{match_id}/maps/{map_number}/notes', path)
  const queryClient = useQueryClient()
  const value: Actions = {
    staff,
    matchId,
    mapNumber,
    notes: (query.data?.notes ?? []) as Actions['notes'],
    reasons: query.data?.reasons ?? {},
    refresh: () =>
      void queryClient.invalidateQueries({
        queryKey: ['get', '/matches/{match_id}/maps/{map_number}/notes', path],
      }),
  }
  return <NotesContext.Provider value={value}>{props.children}</NotesContext.Provider>
}

/** Under a Finding card: dispute it, or add its Round to a Playlist. Staff only. */
export function FindingActions({ f }: { f: Finding }) {
  const ctx = useNotes()
  const [open, setOpen] = useState<'dispute' | 'playlist' | null>(null)
  const add = $api.useMutation('post', '/matches/{match_id}/maps/{map_number}/notes', { onSuccess: () => ctx?.refresh() })
  if (!ctx?.staff || f.round === null) return null
  const disputed = ctx.notes.find(
    (n) => n.kind === 'dispute' && findingKey(n.code, n.round, n.sids[0]) === findingKey(f.code, f.round, f.sids[0]),
  )
  return (
    <span className="contents">
      {disputed ? (
        <span className="text-warn" title={disputed.text || undefined}>
          ✗ маргасан: {ctx.reasons[disputed.reason] ?? disputed.reason}
        </span>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(open === 'dispute' ? null : 'dispute')}
          className="rounded-md px-1.5 py-0.5 text-ink-3 hover:text-ink"
        >
          Буруу?
        </button>
      )}
      <button
        type="button"
        onClick={() => setOpen(open === 'playlist' ? null : 'playlist')}
        className="rounded-md px-1.5 py-0.5 text-ink-3 hover:text-ink"
      >
        + Playlist
      </button>
      {open === 'dispute' && (
        <span className="flex w-full flex-wrap gap-1.5 pt-1">
          {Object.entries(ctx.reasons).map(([key, label]) => (
            <button
              key={key}
              type="button"
              disabled={add.isPending}
              onClick={() => {
                add.mutate({
                  params: { path: { match_id: ctx.matchId, map_number: ctx.mapNumber } },
                  body: { kind: 'dispute', code: f.code, round: f.round, t: f.t, sids: f.sids, reason: key, text: '', tag: '' },
                })
                setOpen(null)
              }}
              className="rounded-md border border-line bg-raised px-2 py-0.5 text-ink-2 hover:border-ink-3"
            >
              {label}
            </button>
          ))}
        </span>
      )}
      {open === 'playlist' && (
        <PlaylistPicker
          item={{ match_id: ctx.matchId, map_number: ctx.mapNumber, round: f.round, t: f.t, sid: f.sids[0] ?? null, text: f.title }}
          done={() => setOpen(null)}
        />
      )}
    </span>
  )
}

/** Append one Round to a Playlist, or start a new one with it. */
export function PlaylistPicker({ item, done }: { item: Item; done: () => void }) {
  const lists = $api.useQuery('get', '/playlists')
  const queryClient = useQueryClient()
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function append(id: number | null) {
    setBusy(true)
    setError('')
    try {
      if (id === null) {
        const made = await fetchClient.POST('/playlists', {
          body: { title: title.trim() || 'Шинэ playlist', note: '', shared: false, items: [item] },
        })
        if (made.error) throw new Error()
      } else {
        const { data } = await fetchClient.GET('/playlists/{playlist_id}', { params: { path: { playlist_id: id } } })
        if (!data) throw new Error()
        const items = [...data.items.map(({ label: _label, ...rest }) => rest), item]
        const saved = await fetchClient.PUT('/playlists/{playlist_id}', {
          params: { path: { playlist_id: id } },
          body: { title: data.title, note: data.note, shared: data.shared, items },
        })
        if (saved.error) throw new Error()
      }
      void queryClient.invalidateQueries({ queryKey: ['get', '/playlists'] })
      done()
    } catch {
      setError('Нэмж чадсангүй.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <span className="flex w-full flex-wrap items-center gap-1.5 pt-1">
      {(lists.data ?? []).slice(0, 6).map((p) => (
        <button
          key={p.id}
          type="button"
          disabled={busy}
          onClick={() => void append(p.id)}
          className="rounded-md border border-line bg-raised px-2 py-0.5 text-ink-2 hover:border-ink-3"
        >
          {p.title} ({p.rounds})
        </button>
      ))}
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Шинэ playlist"
        maxLength={160}
        className="w-36 rounded-md border border-line bg-surface-2 px-2 py-0.5 text-ink"
      />
      <button type="button" disabled={busy} onClick={() => void append(null)} className="text-ct hover:underline">
        Үүсгэх
      </button>
      {error && <span className="text-crit">{error}</span>}
    </span>
  )
}

/** The Round's notes beside the Replay, and, for Staff, a note on this moment. */
export function RoundNotes(props: {
  round: number | null
  bridge: ReplayBridge
  // VIZ-8: hands the page (which owns the Replay) this box's pen and marks.
  onPens: (hooks: PenHooks | null) => void
  names: Record<string, string>
  onGoto: Goto
}) {
  const { round, bridge, onPens, names, onGoto } = props
  const ctx = useNotes()
  const [text, setText] = useState('')
  const [tag, setTag] = useState('')
  const [who, setWho] = useState<string[]>([])
  const [atMoment, setAtMoment] = useState(true)
  // VIZ-8: a pen for the Replay; strokes wait here until the Note is saved.
  const [pen, setPen] = useState<'arrow' | 'circle' | 'text' | null>(null)
  const [penText, setPenText] = useState('')
  const [marks, setMarks] = useState<Shape[]>([])
  const notes = ctx?.notes
  useEffect(() => {
    const all = notes ?? []
    onPens({
      pen: () => (pen && (pen !== 'text' || penText) ? { kind: pen, text: penText } : null),
      onShape: (shape) => setMarks((m) => [...m, shape]),
      // A Note's marks show in its Round, around its moment.
      shapes: (n, t) => [
        ...(n === round ? marks : []),
        ...all
          .filter((x) => x.drawing && x.round === n && (x.t === null || Math.abs(t - (x.t ?? 0)) <= 4))
          .flatMap((x) => (x.drawing ?? []) as Shape[]),
      ],
    })
    bridge.redraw?.()
    return () => onPens(null)
  }, [onPens, bridge, pen, penText, marks, round, notes])
  const add = $api.useMutation('post', '/matches/{match_id}/maps/{map_number}/notes', {
    onSuccess: () => {
      setText('')
      setWho([])
      setMarks([])
      setPen(null)
      ctx?.refresh()
    },
  })
  const remove = $api.useMutation('delete', '/notes/{note_id}', { onSuccess: () => ctx?.refresh() })
  if (!ctx) return null
  const here = ctx.notes.filter((n) => n.kind === 'note' && n.round === round)
  if (!ctx.staff && here.length === 0) return null
  function submit() {
    if (!ctx || (!text.trim() && !marks.length)) return
    const now = atMoment ? bridge.now?.() : null
    add.mutate({
      params: { path: { match_id: ctx.matchId, map_number: ctx.mapNumber } },
      body: {
        kind: 'note', round: now?.round ?? round, t: now?.t ?? null, sids: who, text, tag, code: '', reason: '',
        drawing: marks.length ? marks.map((m) => ({ kind: m.kind, points: m.points, text: m.text ?? '' })) : null,
      },
    })
  }
  return (
    <section className="space-y-2 rounded-xl border border-line bg-surface p-3 text-sm">
      <h3 className="font-medium text-ink">Тэмдэглэл{round ? ` · R${round}` : ''}</h3>
      {here.map((n) => (
        <div key={n.id} className="space-y-0.5 border-l-2 border-line pl-2">
          <p className="text-ink-2">
            {n.t !== null && (
              <button type="button" onClick={() => onGoto(n.round ?? 1, n.t ?? 0, n.sids[0] ?? null)} className="mr-1 font-mono text-xs text-ct">
                ▶ {clock(n.t)}
              </button>
            )}
            {n.text}
            {n.drawing && n.drawing.length > 0 && (
              <span className="ml-1 text-xs text-warn" title="Replay дээр тэр агшинд харагдана">
                ✎ {n.drawing.length}
              </span>
            )}
          </p>
          <NoteClip note={n} staff={ctx.staff} bridge={bridge} onGoto={onGoto} refresh={ctx.refresh} />
          <p className="text-xs text-ink-3">
            {n.tag && <span className="mr-2 rounded border border-line px-1">{n.tag}</span>}
            {n.sids.map((s) => names[s] ?? '?').join(', ')}
            {n.created_by && ` · ${n.created_by}`}
            {ctx.staff && (
              <button type="button" onClick={() => remove.mutate({ params: { path: { note_id: n.id } } })} className="ml-2 hover:text-crit">
                устгах
              </button>
            )}
          </p>
        </div>
      ))}
      {ctx.staff && (
        <div className="space-y-1.5">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={2}
            maxLength={4000}
            placeholder="Энэ раундад тэмдэглэл…"
            className="w-full rounded-md border border-line bg-surface-2 px-2 py-1 text-ink"
          />
          <div className="flex flex-wrap gap-1 text-xs">
            {Object.entries(names).map(([sid, name]) => (
              <button
                key={sid}
                type="button"
                onClick={() => setWho(who.includes(sid) ? who.filter((s) => s !== sid) : [...who, sid])}
                className={`rounded px-1.5 py-0.5 ${who.includes(sid) ? 'bg-raised text-ink' : 'text-ink-3 hover:text-ink'}`}
              >
                {name}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            <span className="text-ink-3">Зурах:</span>
            {(
              [
                ['arrow', '➚ сум'],
                ['circle', '◯ тойрог'],
                ['text', 'T текст'],
              ] as const
            ).map(([k, l]) => (
              <button
                key={k}
                type="button"
                onClick={() => setPen(pen === k ? null : k)}
                className={`rounded px-1.5 py-0.5 ${pen === k ? 'bg-raised text-ink' : 'text-ink-3 hover:text-ink'}`}
              >
                {l}
              </button>
            ))}
            {pen === 'text' && (
              <input
                value={penText}
                onChange={(e) => setPenText(e.target.value)}
                maxLength={80}
                placeholder="бичих үг"
                className="w-28 rounded-md border border-line bg-surface-2 px-2 py-0.5 text-ink"
              />
            )}
            {marks.length > 0 && (
              <button type="button" onClick={() => setMarks([])} className="text-ink-3 hover:text-crit">
                {marks.length} зураас арилгах
              </button>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <input
              value={tag}
              onChange={(e) => setTag(e.target.value)}
              maxLength={32}
              placeholder="tag"
              className="w-24 rounded-md border border-line bg-surface-2 px-2 py-0.5 text-ink"
            />
            <label className="flex items-center gap-1 text-ink-3">
              <input type="checkbox" checked={atMoment} onChange={(e) => setAtMoment(e.target.checked)} />
              Replay-ийн энэ агшинд
            </label>
            <button
              type="button"
              disabled={add.isPending || (!text.trim() && !marks.length)}
              onClick={submit}
              className="ml-auto rounded-md bg-ct px-3 py-1 font-medium text-ground disabled:opacity-50"
            >
              Нэмэх
            </button>
          </div>
        </div>
      )}
    </section>
  )
}

/** A Player's notes on his own page: what Staff left that names him. */
export function MyNotes() {
  const notes = $api.useQuery('get', '/me/notes')
  const playlists = $api.useQuery('get', '/playlists')
  if (!notes.data?.length && !playlists.data?.length) return null
  return (
    <section className="space-y-3">
      {(playlists.data?.length ?? 0) > 0 && (
        <div className="space-y-1">
          <h2 className="font-medium text-ink">Playlist</h2>
          <ul className="space-y-1 text-sm">
            {playlists.data!.map((p) => (
              <li key={p.id}>
                <Link to={`/playlists/${p.id}`} className="text-ct hover:underline">
                  {p.title}
                </Link>{' '}
                <span className="text-ink-3">{p.rounds} раунд</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {(notes.data?.length ?? 0) > 0 && (
        <div className="space-y-1">
          <h2 className="font-medium text-ink">Багийн тэмдэглэл</h2>
          <ul className="space-y-1 text-sm text-ink-2">
            {notes.data!.map((n) => (
              <li key={n.id}>
                <Link
                  to={`/matches/${n.match_id}/m/${n.map_number}${n.round ? `?round=${n.round}` : ''}`}
                  className="mr-1 font-mono text-xs text-ct"
                >
                  {n.round ? `R${n.round}` : 'Map'}
                </Link>
                {n.text}
                {n.tag && <span className="ml-1 rounded border border-line px-1 text-xs text-ink-3">{n.tag}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

// VIZ-13: ten seconds of the Replay from the note's moment, kept with it. Staff
// record it here (the Replay jumps to the moment and plays while it records);
// whoever may read the note plays it back.
function NoteClip(props: {
  note: components['schemas']['NoteRead']
  staff: boolean
  bridge: ReplayBridge
  onGoto: Goto
  refresh: () => void
}) {
  const { note, staff, bridge, onGoto, refresh } = props
  const [url, setUrl] = useState<string | null>(null)
  const [busy, setBusy] = useState<'' | 'recording' | 'saving'>('')
  const [error, setError] = useState('')
  useEffect(() => () => void (url && URL.revokeObjectURL(url)), [url])

  async function play() {
    if (url) return setUrl(null)
    const got = await fetchClient.GET('/notes/{note_id}/clip', {
      params: { path: { note_id: note.id } },
      parseAs: 'blob',
    })
    if (got.data) setUrl(URL.createObjectURL(got.data as Blob))
    else setError('Клипийг уншиж чадсангүй.')
  }
  function record() {
    if (note.t === null || busy) return
    setError('')
    onGoto(note.round ?? 1, note.t, note.sids[0] ?? null, false)
    window.setTimeout(() => {
      const ok = bridge.record?.(CLIP_SECONDS, async (blob) => {
        setBusy('saving')
        const sent = await fetchClient.PUT('/notes/{note_id}/clip', {
          params: { path: { note_id: note.id } },
          body: { data: blob as unknown as string },
          bodySerializer: (body) => {
            const form = new FormData()
            form.append('data', body.data as unknown as Blob, 'clip.webm')
            return form
          },
        })
        setBusy('')
        if (sent.error) setError('Клипийг хадгалж чадсангүй.')
        else refresh()
      })
      if (ok) setBusy('recording')
      else setError('Энэ browser Replay-ийг бичиж чадахгүй.')
    }, 300)
  }

  if (!note.has_clip && !(staff && note.t !== null)) return null
  return (
    <div className="space-y-1 text-xs">
      <p className="flex flex-wrap gap-3">
        {note.has_clip && (
          <button type="button" onClick={play} className="text-ct hover:underline">
            {url ? '■ Клипийг хаах' : '🎬 Клип үзэх'}
          </button>
        )}
        {staff && note.t !== null && (
          <button type="button" onClick={record} disabled={!!busy} className="text-ink-3 hover:text-ct disabled:opacity-60">
            {busy === 'recording'
              ? '● Бичиж байна…'
              : busy === 'saving'
                ? 'Хадгалж байна…'
                : note.has_clip
                  ? '● Клипийг дахин бичих'
                  : `● ${CLIP_SECONDS} с клип хавсаргах`}
          </button>
        )}
        {error && <span className="text-crit">{error}</span>}
      </p>
      {url && <video src={url} controls autoPlay className="w-full max-w-md rounded-md border border-line" />}
    </div>
  )
}

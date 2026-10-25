// A Workspace's own Demos (docs/plans/02 DATA-1): a Scrim, or an official Match HLTV
// doesn't carry. The file goes up in parts (the server keeps them in MySQL until the
// parse queue has them), then each Map is parsed beside any Scout. A Map whose
// Players don't say which side is ours waits here for Staff to pick (who is who).
import { useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useMemo, useState } from 'react'
import { Link } from 'react-router'
import { $api, fetchClient } from '../api/client'
import { errorText } from '../api/errors'
import type { components } from '../api/schema'
import { useMyTeams } from '../auth/useMe'
import { usePaths } from '../paths'

type Upload = components['schemas']['UploadRead']
type UploadMap = components['schemas']['UploadMap']

const STATUS: Record<string, { text: string; tone: string }> = {
  receiving: { text: 'хүлээн авч байна', tone: 'text-ink-2' },
  queued: { text: 'дараалалд', tone: 'text-ink-2' },
  parsing: { text: 'parse хийж байна', tone: 'text-warn' },
  needs_sides: { text: 'аль тал нь манайх вэ?', tone: 'text-warn' },
  done: { text: 'бэлэн', tone: 'text-good' },
  failed: { text: 'амжилтгүй', tone: 'text-crit' },
}

const today = () => new Date().toISOString().slice(0, 10)
const mb = (bytes: number) => `${(bytes / 2 ** 20).toFixed(1)} MB`

export default function UploadsPage() {
  const list = $api.useQuery('get', '/uploads', {}, {
    // While something is parsing, the list follows it.
    refetchInterval: (q) =>
      q.state.data?.uploads.some((u) => ['queued', 'parsing'].includes(u.status)) ? 4000 : false,
  })
  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold text-ink">Демо оруулах</h1>
        <p className="max-w-2xl text-ink-2">
          Өөрсдийн demo: scrim, эсвэл HLTV-д ороогүй албан тоглолт. Scrim нь Review, Replay-тэй болох ч ямар ч
          багийн Own form, habit, Pool-д тооцогдохгүй. Албан тоглолт нь зөвхөн энэ Workspace дотор тооцогдоно.
        </p>
      </div>
      <UploadForm />
      {list.isError ? (
        <p className="text-crit">Uploads-ыг уншиж чадсангүй.</p>
      ) : !list.data ? (
        <p className="text-ink-3">Уншиж байна…</p>
      ) : list.data.uploads.length === 0 ? (
        <p className="text-sm text-ink-3">Upload алга.</p>
      ) : (
        <div className="space-y-3">
          {list.data.uploads.map((u) => (
            <UploadCard key={u.id} upload={u} />
          ))}
        </div>
      )}
    </div>
  )
}

function UploadForm() {
  const queryClient = useQueryClient()
  const myTeams = useMyTeams()
  const paths = usePaths()
  const teams = $api.useQuery('get', '/teams')
  const [kind, setKind] = useState<'scrim' | 'official'>('scrim')
  const [playedOn, setPlayedOn] = useState(today())
  const [myTeam, setMyTeam] = useState<number | null>(null)
  const [opponent, setOpponent] = useState('')
  const [note, setNote] = useState('')
  const [file, setFile] = useState<File | null>(null)
  // DATA-1: or a link (a scrim server's demo, a shared Drive file) the worker fetches.
  const [link, setLink] = useState('')
  const [progress, setProgress] = useState<{ done: number; of: number } | null>(null)
  const [error, setError] = useState('')
  const mine = myTeam ?? paths.team ?? myTeams[0]?.id ?? null
  const byName = useMemo(
    () => new Map((teams.data?.teams ?? []).map((t) => [t.name.toLowerCase(), t.id])),
    [teams.data],
  )

  async function submit(event: FormEvent) {
    event.preventDefault()
    if ((!file && !link.trim()) || mine === null) return
    setError('')
    const opponentId = byName.get(opponent.trim().toLowerCase()) ?? null
    if (!file) {
      setProgress({ done: 0, of: 0 })
      const fetched = await fetchClient.POST('/uploads/from-url', {
        body: {
          kind,
          played_on: playedOn,
          my_team_id: mine,
          opponent_id: opponentId,
          opponent_name: opponentId ? '' : opponent.trim(),
          note,
          url: link.trim(),
        },
      })
      setProgress(null)
      if (fetched.error) setError(errorText(fetched.error) || 'Линкийг хүлээж авсангүй.')
      else setLink('')
      queryClient.invalidateQueries({ queryKey: ['get', '/uploads'] })
      return
    }
    const made = await fetchClient.POST('/uploads', {
      body: {
        kind,
        played_on: playedOn,
        my_team_id: mine,
        opponent_id: opponentId,
        opponent_name: opponentId ? '' : opponent.trim(),
        note,
        filename: file.name,
        size: file.size,
      },
    })
    if (!made.data) {
      setError(errorText(made.error) || 'Upload эхлүүлж чадсангүй.')
      return
    }
    const up = made.data
    setProgress({ done: 0, of: up.parts_total })
    for (let n = 0; n < up.parts_total; n++) {
      const blob = file.slice(n * up.part_bytes, (n + 1) * up.part_bytes)
      const sent = await fetchClient.PUT('/uploads/{public_id}/parts/{n}', {
        params: { path: { public_id: up.id, n } },
        body: { data: blob as unknown as string },
        bodySerializer: (body) => {
          const form = new FormData()
          form.append('data', body.data as unknown as Blob, `part-${n}`)
          return form
        },
      })
      if (sent.error) {
        setError(errorText(sent.error) || `Хэсэг ${n + 1} явсангүй.`)
        setProgress(null)
        return
      }
      setProgress({ done: n + 1, of: up.parts_total })
    }
    const closed = await fetchClient.POST('/uploads/{public_id}/complete', {
      params: { path: { public_id: up.id } },
    })
    if (closed.error) setError(errorText(closed.error) || 'Upload-ыг хааж чадсангүй.')
    setProgress(null)
    setFile(null)
    queryClient.invalidateQueries({ queryKey: ['get', '/uploads'] })
  }

  if (!myTeams.length) {
    return <p className="text-sm text-ink-3">Энэ Workspace-д my team алга: эхлээд my team нэмнэ үү.</p>
  }
  const busy = progress !== null
  return (
    <form onSubmit={submit} className="space-y-4 rounded-xl border border-line bg-surface p-6">
      <div className="flex flex-wrap gap-4 text-sm">
        {(['scrim', 'official'] as const).map((k) => (
          <label key={k} className="flex items-center gap-2 text-ink-2">
            <input type="radio" name="kind" checked={kind === k} onChange={() => setKind(k)} />
            {k === 'scrim' ? 'Scrim' : 'Албан тоглолт (HLTV-д байхгүй)'}
          </label>
        ))}
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <label className="block space-y-1 text-sm">
          <span className="text-ink-3">Манай баг</span>
          <select
            value={mine ?? ''}
            onChange={(e) => setMyTeam(Number(e.target.value))}
            className="w-full rounded-md border border-line bg-surface-2 px-3 py-2 text-ink"
          >
            {myTeams.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
                {t.label ? ` (${t.label})` : ''}
              </option>
            ))}
          </select>
        </label>
        <label className="block space-y-1 text-sm">
          <span className="text-ink-3">{kind === 'scrim' ? 'Scrim-ийн түнш' : 'Өрсөлдөгч'}</span>
          <input
            list="upload-teams"
            value={opponent}
            onChange={(e) => setOpponent(e.target.value)}
            required
            className="w-full rounded-md border border-line bg-surface-2 px-3 py-2 text-ink"
          />
          <datalist id="upload-teams">
            {(teams.data?.teams ?? []).map((t) => (
              <option key={t.id} value={t.name} />
            ))}
          </datalist>
        </label>
        <label className="block space-y-1 text-sm">
          <span className="text-ink-3">Огноо</span>
          <input
            type="date"
            value={playedOn}
            onChange={(e) => setPlayedOn(e.target.value)}
            required
            className="w-full rounded-md border border-line bg-surface-2 px-3 py-2 text-ink"
          />
        </label>
      </div>
      <label className="block space-y-1 text-sm">
        <span className="text-ink-3">Тэмдэглэл</span>
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={500}
          className="w-full rounded-md border border-line bg-surface-2 px-3 py-2 text-ink"
        />
      </label>
      <div className="flex flex-wrap items-center gap-4 text-sm">
        <input
          type="file"
          accept=".dem,.zip,.rar,.7z,.gz,.bz2,.xz,.tar,.tgz"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="text-ink-2"
        />
        {file && <span className="font-mono text-xs text-ink-3">{mb(file.size)}</span>}
        <span className="text-ink-3">эсвэл</span>
        <input
          type="url"
          value={link}
          onChange={(e) => setLink(e.target.value)}
          placeholder="Линк: scrim server, Google Drive…"
          disabled={!!file}
          className="min-w-[16rem] flex-1 rounded-md border border-line bg-surface-2 px-3 py-2 text-ink disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={(!file && !link.trim()) || busy}
          className="rounded-md border border-line bg-raised px-4 py-2 text-ink hover:border-ink-3 disabled:opacity-50"
        >
          Оруулах
        </button>
        {progress && (
          <span className="font-mono text-xs text-ink-2">
            {progress.done}/{progress.of} хэсэг
          </span>
        )}
        {error && <span className="text-crit">{error}</span>}
      </div>
    </form>
  )
}

function UploadCard({ upload: u }: { upload: Upload }) {
  const paths = usePaths()
  const s = STATUS[u.status] ?? { text: u.status, tone: 'text-ink-2' }
  const opponent = u.opponent?.name ?? u.opponent_name
  return (
    <div className="space-y-3 rounded-xl border border-line bg-surface p-4 text-sm">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span className="font-medium text-ink">
          {u.my_team.name} vs {opponent}
        </span>
        <span className="rounded border border-line px-1.5 text-[10px] uppercase tracking-wide text-ink-2">
          {u.kind === 'scrim' ? 'scrim' : 'official'}
        </span>
        <span className="text-ink-3">{u.played_on}</span>
        <span className="font-mono text-xs text-ink-3">
          {u.filename}
          {u.size_bytes > 0 ? ` · ${mb(u.size_bytes)}` : ''}
          {u.source_url ? ` · ${hostOf(u.source_url)}-оос` : ''}
        </span>
        <span className={`ml-auto ${s.tone}`}>{s.text}</span>
      </div>
      {u.status === 'receiving' && (
        <p className="text-ink-3">
          {u.received}/{u.parts_total} хэсэг ирсэн. Хуудсыг хаасан бол файлаа дахин сонгож upload хийнэ үү.
        </p>
      )}
      {u.error && <p className="text-crit">{u.error}</p>}
      {u.maps.length > 0 && (
        <ul className="space-y-2">
          {u.maps.map((m) => (
            <MapLine key={m.map_number} upload={u} map={m} />
          ))}
        </ul>
      )}
      <div className="flex gap-4 text-xs">
        {u.match_id && (
          <Link to={paths.match(u.match_id)} className="text-ct hover:underline">
            Review ба Replay →
          </Link>
        )}
        {u.job_id && (
          <Link to={paths.job(u.job_id)} className="text-ink-3 hover:underline">
            Job-ын явц
          </Link>
        )}
      </div>
    </div>
  )
}

function MapLine({ upload, map }: { upload: Upload; map: UploadMap }) {
  const queryClient = useQueryClient()
  const answer = $api.useMutation('post', '/uploads/{public_id}/sides', {
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['get', '/uploads'] }),
  })
  if (map.assigned) {
    return (
      <li className="text-ink-2">
        <span className="text-good">✓</span> {map.map}
      </li>
    )
  }
  const waiting = map.mine !== null && map.mine !== undefined
  return (
    <li className="space-y-2 rounded-md border border-line-soft p-3">
      <p className="text-ink">
        {map.map}:{' '}
        {waiting ? 'сонгосноор дахин хадгалж байна…' : 'аль 5 нь манай баг вэ? Demo-д багийн нэр алга.'}
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        {map.groups.map((group, i) => (
          <div key={i} className="space-y-2">
            <p className="text-ink-2">
              {group.map((p) => (
                <span key={p.steamid} className="mr-2 inline-block">
                  {p.name || p.steamid}
                  {p.known && (
                    <span className="ml-1 font-mono text-[10px] text-ink-3">
                      {p.known === 'mine' ? 'манай' : 'тэдний'}
                    </span>
                  )}
                </span>
              ))}
            </p>
            <button
              type="button"
              disabled={answer.isPending || waiting}
              onClick={() =>
                answer.mutate({
                  params: { path: { public_id: upload.id } },
                  body: { map_number: map.map_number, mine: i },
                })
              }
              className="rounded-md border border-line bg-raised px-3 py-1 text-xs text-ink hover:border-ink-3 disabled:opacity-50"
            >
              Энэ 5 манайх
            </button>
          </div>
        ))}
      </div>
    </li>
  )
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname
  } catch {
    return 'линк'
  }
}


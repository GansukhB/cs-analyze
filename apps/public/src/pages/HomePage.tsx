import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { $api } from '../api/client'
import { usePaths } from '../paths'
import type { components } from '../api/schema'
import { useMyTeams } from '../auth/useMe'
import JobTable from '../jobs/JobTable'

type Defaults = components['schemas']['ScoutDefaults']
type ValidationError = components['schemas']['HTTPValidationError']

export default function HomePage() {
  const home = $api.useQuery('get', '/home')
  const myTeams = useMyTeams()
  // In v2 the Scout starts from the my team in the URL.
  const team = usePaths().team
  const mine = (myTeams.find((t) => t.id === team) ?? myTeams[0])?.name ?? ''
  if (!home.data) return <p className="text-ink-3">Уншиж байна…</p>
  const { known_teams, parsed_maps, recent_jobs, defaults } = home.data

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold text-ink">Хэнтэй тоглох вэ?</h1>
        <p className="max-w-2xl text-ink-2">
          Манай баг, өрсөлдөгчөө нэрлэ. Worker тэдний сүүлийн demo-г HLTV-ээс татаж, задлаад parse хийнэ; алхам
          бүрийг шууд харна.
        </p>
      </div>

      {/* Keyed by my team so the form starts from it once /auth/me has answered. */}
      <ScoutForm key={mine} myTeamName={mine} defaults={defaults} knownTeams={known_teams} parsedMaps={parsed_maps} />

      {known_teams.length > 0 && (
        <section className="space-y-2">
          <h2 className="font-medium text-ink">Өгөгдөлд байгаа багууд</h2>
          <p className="text-sm text-ink-2">
            {known_teams.map((name, i) => (
              <span key={name}>
                <code className="rounded bg-surface-2 px-1">{name}</code>
                {i < known_teams.length - 1 && ' · '}
              </span>
            ))}
          </p>
        </section>
      )}

      <section className="space-y-2">
        <h2 className="font-medium text-ink">Сүүлийн Scout-ууд</h2>
        {recent_jobs.length ? (
          <JobTable jobs={recent_jobs} />
        ) : (
          <p className="text-sm text-ink-3">Scout алга: эхнийхээ дээрх маягтаас эхлүүл.</p>
        )}
      </section>
    </div>
  )
}

const WINDOWS = [
  { key: 'n_my_matches', letter: 'a', label: 'манай багийн', help: 'Өрсөлдөгчөөс бусадтай хийсэн сүүлийн тоглолтууд.' },
  { key: 'n_opponent_matches', letter: 'b', label: 'өрсөлдөгчийн', help: 'Манай багаас бусадтай хийсэн сүүлийн тоглолтууд.' },
  { key: 'n_h2h_matches', letter: 'c', label: 'хоорондын', help: 'Хоёр багийн хоорондоо хийсэн сүүлийн тоглолтууд.' },
] as const

type WindowKey = (typeof WINDOWS)[number]['key']

function ScoutForm({
  myTeamName,
  defaults,
  knownTeams,
  parsedMaps,
}: {
  myTeamName: string
  defaults: Defaults
  knownTeams: string[]
  parsedMaps: number
}) {
  const navigate = useNavigate()
  const paths = usePaths()
  const [myTeam, setMyTeam] = useState(myTeamName)
  const [opponent, setOpponent] = useState('')
  const [counts, setCounts] = useState<Record<WindowKey, number>>({
    n_my_matches: defaults.matches,
    n_opponent_matches: defaults.matches,
    n_h2h_matches: defaults.matches,
  })
  const [download, setDownload] = useState(true)
  const create = $api.useMutation('post', '/jobs', {
    onSuccess: (job) => navigate(paths.job(job.public_id)),
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    create.mutate({ body: { my_team: myTeam, opponent, download, ...counts } })
  }

  const errors = (create.error as ValidationError | undefined)?.detail?.map((d) => d.msg.replace(/^Value error, /, ''))

  return (
    <form onSubmit={submit} className="space-y-6 rounded-xl border border-line bg-surface p-6">
      <div className="grid items-end gap-4 sm:grid-cols-[1fr_auto_1fr]">
        <TeamInput label="Манай баг" value={myTeam} onChange={setMyTeam} placeholder="Vitality" autoFocus={!myTeamName} />
        <span className="hidden pb-2 font-mono text-xs tracking-widest text-ink-3 sm:block">VS</span>
        <TeamInput label="Өрсөлдөгч" value={opponent} onChange={setOpponent} placeholder="Inner Circle" autoFocus={!!myTeamName} />
      </div>
      <datalist id="teams">
        {knownTeams.map((name) => (
          <option key={name} value={name} />
        ))}
      </datalist>

      <div className="grid gap-4 sm:grid-cols-3">
        {WINDOWS.map((w) => (
          <label key={w.key} className="block space-y-1">
            <span className="text-sm text-ink-2">
              <b className="mr-1 font-mono text-ct">{w.letter}</b>
              {w.label}
            </span>
            <input
              type="number"
              min={0}
              max={defaults.max_matches}
              value={counts[w.key]}
              onChange={(e) => setCounts({ ...counts, [w.key]: Number(e.target.value) })}
              className="w-full rounded-md border border-line bg-ground px-3 py-2 text-ink placeholder:text-ink-3 focus:border-ct focus:outline-none text-center tabular-nums"
            />
            <span className="block text-xs text-ink-3">{w.help}</span>
          </label>
        ))}
      </div>

      <label className="flex items-start gap-2">
        <input type="checkbox" checked={download} onChange={(e) => setDownload(e.target.checked)} className="mt-1" />
        <span>
          <span className="text-sm text-ink">HLTV-ээс шинэ demo татах</span>
          <span className="block text-xs text-ink-3">Чагтыг авбал зөвхөн аль хэдийн parse хийсэн тоглолтуудаар шинжилнэ.</span>
        </span>
      </label>

      {errors && <p className="text-sm text-crit">{errors.join(' ')}</p>}

      <div className="flex flex-wrap items-center gap-4">
        <button type="submit" disabled={create.isPending} className="rounded-md bg-ct px-4 py-2 font-semibold text-ground hover:brightness-110 disabled:opacity-50">
          Scout эхлүүлэх
        </button>
        <span className="text-xs text-ink-3">
          Тоглолт бүр хэдэн зуун MB татна, ар талд ажиллана.
        </span>
      </div>
      <p className="font-mono text-xs text-ink-3">{parsedMaps} Map parse хийгдэж бэлэн байна</p>
    </form>
  )
}

function TeamInput(props: {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder: string
  autoFocus?: boolean
}) {
  return (
    <label className="block space-y-1">
      <span className="text-sm text-ink-2">{props.label}</span>
      <input
        list="teams"
        required
        maxLength={120}
        autoComplete="off"
        autoFocus={props.autoFocus}
        placeholder={props.placeholder}
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        className="w-full rounded-md border border-line bg-ground px-3 py-2 text-ink placeholder:text-ink-3 focus:border-ct focus:outline-none"
      />
    </label>
  )
}

import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { $api } from '../api/client'
import { errorText } from '../api/errors'
import { usePaths } from '../paths'
import type { components } from '../api/schema'
import { useMyTeams } from '../auth/useMe'
import JobTable from '../jobs/JobTable'

type Defaults = components['schemas']['ScoutDefaults']
// A Scout is about a fixture; a Team Scout pulls one Team's latest Matches (CONTEXT.md).
type Mode = 'scout' | 'team'

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
          Манай баг, өрсөлдөгчөө нэрлэ, эсвэл «Нэг баг»-аар нэг багийн сүүлийн 40 хүртэлх тоглолтыг тат. Worker
          demo-г HLTV-ээс татаж, задлаад parse хийнэ; алхам бүрийг шууд харна.
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
  const [mode, setMode] = useState<Mode>('scout')
  const [myTeam, setMyTeam] = useState(myTeamName)
  const [opponent, setOpponent] = useState('')
  const [counts, setCounts] = useState<Record<WindowKey, number>>({
    n_my_matches: defaults.matches,
    n_opponent_matches: defaults.matches,
    n_h2h_matches: defaults.matches,
  })
  const [teamMatches, setTeamMatches] = useState(defaults.team_matches)
  const [download, setDownload] = useState(true)
  const create = $api.useMutation('post', '/jobs', {
    onSuccess: (job) => navigate(paths.job(job.public_id)),
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    create.mutate({
      body:
        mode === 'team'
          ? { kind: 'team', my_team: myTeam, opponent: '', n_my_matches: teamMatches, n_opponent_matches: 0, n_h2h_matches: 0, download }
          : { kind: 'scout', my_team: myTeam, opponent, download, ...counts },
    })
  }

  function pick(next: Mode) {
    setMode(next)
    create.reset()
  }

  const error = create.error ? errorText(create.error) : ''

  return (
    <form onSubmit={submit} className="space-y-6 rounded-xl border border-line bg-surface p-6">
      <div role="radiogroup" aria-label="Scout-ийн төрөл" className="inline-flex rounded-md border border-line bg-ground p-0.5 text-sm">
        {(
          [
            ['scout', 'Хоёр баг'],
            ['team', 'Нэг баг'],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="radio"
            aria-checked={mode === key}
            onClick={() => pick(key)}
            className={`rounded px-3 py-1.5 ${mode === key ? 'bg-ct font-semibold text-ground' : 'text-ink-2 hover:text-ink'}`}
          >
            {label}
          </button>
        ))}
      </div>

      <datalist id="teams">
        {knownTeams.map((name) => (
          <option key={name} value={name} />
        ))}
      </datalist>

      {mode === 'team' ? (
        <div className="grid items-start gap-4 sm:grid-cols-[1fr_12rem]">
          <TeamInput label="Баг" value={myTeam} onChange={setMyTeam} placeholder="The MongolZ" autoFocus />
          <label className="block space-y-1">
            <span className="text-sm text-ink-2">Сүүлийн хэдэн тоглолт</span>
            <input
              type="number"
              min={1}
              max={defaults.team_max_matches}
              required
              value={teamMatches}
              onChange={(e) => setTeamMatches(Number(e.target.value))}
              className="w-full rounded-md border border-line bg-ground px-3 py-2 text-center text-ink tabular-nums focus:border-ct focus:outline-none"
            />
            <span className="block text-xs text-ink-3">1–{defaults.team_max_matches}, хэнтэй ч хамаагүй.</span>
          </label>
          <p className="text-xs text-ink-3 sm:col-span-2">
            HLTV дээрх энэ багийн хамгийн сүүлийн тоглолтуудыг нэг нэгээр нь татаж parse хийнэ. Аль хэдийн parse
            хийсэн нь хэдэн секундэд алгасагдана. Шинэ тоглолт бүр ойролцоогоор 5 минут болдог тул 40 шинэ тоглолт
            хэдэн цаг үргэлжилнэ. Энэ хооронд бусад Scout дараалалд хүлээнэ, STOP дарвал тэр хүртэл parse хийсэн нь
            хадгалагдана.
          </p>
        </div>
      ) : (
        <>
          <div className="grid items-end gap-4 sm:grid-cols-[1fr_auto_1fr]">
            <TeamInput label="Манай баг" value={myTeam} onChange={setMyTeam} placeholder="Vitality" autoFocus={!myTeamName} />
            <span className="hidden pb-2 font-mono text-xs tracking-widest text-ink-3 sm:block">VS</span>
            <TeamInput label="Өрсөлдөгч" value={opponent} onChange={setOpponent} placeholder="Inner Circle" autoFocus={!!myTeamName} />
          </div>
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
        </>
      )}

      <label className="flex items-start gap-2">
        <input type="checkbox" checked={download} onChange={(e) => setDownload(e.target.checked)} className="mt-1" />
        <span>
          <span className="text-sm text-ink">HLTV-ээс шинэ demo татах</span>
          <span className="block text-xs text-ink-3">Чагтыг авбал зөвхөн аль хэдийн parse хийсэн тоглолтуудаар шинжилнэ.</span>
        </span>
      </label>

      {error && <p className="text-sm text-crit">{error}</p>}

      <div className="flex flex-wrap items-center gap-4">
        <button type="submit" disabled={create.isPending} className="rounded-md bg-ct px-4 py-2 font-semibold text-ground hover:brightness-110 disabled:opacity-50">
          {mode === 'team' ? 'Team Scout эхлүүлэх' : 'Scout эхлүүлэх'}
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

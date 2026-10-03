import { useEffect, useRef } from 'react'
import { Link, useParams } from 'react-router'
import { $api } from '../api/client'
import {
  STATUS_MN,
  secs,
  tally,
  when,
  type JobEvent,
  type JobResult,
  type MatchSummary,
  type StageRow,
} from '../jobs/format'
import StatusPill from '../jobs/StatusPill'
import { useJobLive } from '../jobs/useJobLive'

// Log lines sit on a dark background.
const LEVEL: Record<string, string> = {
  debug: 'text-ink-3',
  info: 'text-ink-2',
  success: 'text-good',
  warning: 'text-warn',
  error: 'text-crit',
}

const DOT: Record<string, string> = {
  done: 'bg-good',
  running: 'bg-ct animate-pulse',
  failed: 'bg-crit',
  pending: 'bg-raised',
}

const DEMO: Record<string, string> = {
  processed: 'задлагдсан',
  downloaded: 'татсан',
  failed: 'унасан',
  pending: 'хүлээгдэж байна',
  none: 'demo байхгүй',
}

export default function JobPage() {
  const { publicId = '' } = useParams()
  const { detail, status, events, conn, error } = useJobLive(publicId)
  const cancel = $api.useMutation('post', '/jobs/{public_id}/cancel')

  if (error) return <p className="text-crit">Job олдсонгүй.</p>
  if (!detail || !status) return <p className="text-ink-3">Уншиж байна…</p>
  const { job, words } = detail

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold text-ink">
          {job.my_team_name} <span className="text-ink-3">vs</span> {job.opponent_name}
        </h1>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <StatusPill status={status.status} labels={STATUS_MN} />
          <span className="font-mono text-xs text-ink-3">{words.stages[status.stage] ?? status.stage_label}</span>
          {status.cycle && (
            <span className="rounded-md border border-line px-2 py-0.5 font-mono text-xs text-ink-2">
              Матч {status.cycle.n}/{status.cycle.of}
            </span>
          )}
          {!status.finished && (
            <button
              onClick={() => cancel.mutate({ params: { path: { public_id: publicId } } })}
              disabled={cancel.isPending || cancel.isSuccess}
              className="rounded-md border border-line px-3 py-1 text-ink-2 hover:bg-surface-2 disabled:opacity-50"
            >
              {cancel.isPending || cancel.isSuccess ? 'Зогсож байна…' : 'STOP'}
            </button>
          )}
          <span className="ml-auto text-xs text-ink-3">{conn}</span>
        </div>
        <p className="text-xs text-ink-3">
          a/b/c {job.windows} · {job.download ? 'HLTV-ээс татна' : 'зөвхөн диск дээрх demo'} · {when(job.created_at)}
          {job.requested_by && ` · ${job.requested_by}`}
        </p>
      </header>

      <section className="space-y-2">
        <div className="h-2 overflow-hidden rounded-full bg-raised">
          <div className="h-full bg-ct transition-all" style={{ width: `${status.progress}%` }} />
        </div>
        <div className="flex justify-between font-mono text-xs text-ink-3">
          <span>{status.progress}%</span>
          <span>{secs(status.duration)}</span>
        </div>
        {status.activity?.text && (
          <div className="rounded-md border border-ct/30 bg-ct/10 px-3 py-2 text-sm text-ink">
            <span className="mr-2 text-ct">●</span>
            {status.activity.text}
            {typeof status.activity.pct === 'number' && (
              <div className="mt-2 h-1 overflow-hidden rounded-full bg-ct/20">
                <div className="h-full bg-ct" style={{ width: `${status.activity.pct}%` }} />
              </div>
            )}
          </div>
        )}
        {status.error && (
          <pre className="whitespace-pre-wrap rounded-md border border-crit/40 bg-crit/10 px-3 py-2 text-sm text-crit">{status.error}</pre>
        )}
      </section>

      <Stages rows={status.stages} words={words} cycle={status.finished ? null : status.cycle ?? null} />
      <Log events={events} />
      {detail.result && <Result result={detail.result} words={words.counts} />}
    </div>
  )
}

function Stages({
  rows,
  words,
  cycle,
}: {
  rows: StageRow[]
  words: { stages: Record<string, string>; counts: Record<string, string> }
  cycle: { n: number; of: number } | null
}) {
  return (
    <ol className="divide-y divide-line-soft rounded-xl border border-line bg-surface">
      {cycle && (
        // Downloading, unpacking and parsing repeat for every match, one at a time,
        // so a match's files are gone before the next one is fetched.
        <li className="px-4 py-2 font-mono text-xs text-ink-3">
          Матч {cycle.n}/{cycle.of} — татах, задлах, боловсруулах шат матч бүрт давтагдана
        </li>
      )}
      {rows.map((row) => (
        <li key={row.stage} className="flex items-center gap-3 px-4 py-2 text-sm">
          <span className={`h-2.5 w-2.5 rounded-full ${DOT[row.state] ?? DOT.pending}`} />
          <span className={row.state === 'pending' ? 'text-ink-3' : 'text-ink'}>
            {words.stages[row.stage] ?? row.label}
          </span>
          <span className="flex-1 truncate text-ink-3">{tally(row.counts, words.counts) || row.summary}</span>
          <span className="font-mono text-xs text-ink-3">{secs(row.seconds)}</span>
        </li>
      ))}
    </ol>
  )
}

function Log({ events }: { events: JobEvent[] }) {
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (box.current) box.current.scrollTop = box.current.scrollHeight
  }, [events.length])

  return (
    <section className="space-y-2">
      <h2 className="font-medium text-ink">Явц</h2>
      <div ref={box} className="max-h-[28rem] overflow-y-auto rounded-xl border border-line bg-surface p-3 font-mono text-xs leading-relaxed">
        {events.map((e) => {
          const payload = e.payload as { step?: number; steps?: number }
          return (
            <div key={e.id} className={`flex gap-3 ${LEVEL[e.level] ?? LEVEL.info}`}>
              <span className="shrink-0 text-ink-3">{new Date(e.at).toTimeString().slice(0, 8)}</span>
              <span className="w-12 shrink-0 text-right text-ink-3">
                {payload.steps ? `[${payload.step}/${payload.steps}]` : ''}
              </span>
              <span className="whitespace-pre-wrap break-all">{e.message}</span>
            </div>
          )
        })}
      </div>
    </section>
  )
}

const WINDOW_TITLES: Record<string, string> = {
  h2h: 'Хоорондын тоглолтууд',
  mine: 'Манай багийн тоглолтууд',
  theirs: 'Өрсөлдөгчийн тоглолтууд',
}

function Result({ result, words }: { result: JobResult; words: Record<string, string> }) {
  const totals = Object.entries(result.totals).filter(([, counts]) => tally(counts, words))
  return (
    <section className="space-y-4">
      <h2 className="font-medium text-ink">Үр дүн</h2>
      {totals.length > 0 && (
        <ul className="flex flex-wrap gap-4 text-sm text-ink-2">
          {totals.map(([stage, counts]) => (
            <li key={stage}>
              <span className="text-ink-3">{stage}:</span> {tally(counts, words)}
            </li>
          ))}
        </ul>
      )}
      {result.windows &&
        Object.entries(result.windows).map(([key, matches]) => (
          <Matches key={key} title={WINDOW_TITLES[key] ?? key} matches={matches} />
        ))}
      <Matches title="Энэ хоёр багийн parse хийгдсэн бүх тоглолт" matches={result.parsed_matches} />
    </section>
  )
}

function Matches({ title, matches }: { title: string; matches: MatchSummary[] }) {
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-ink-2">
        {title} <span className="text-ink-3">({matches.length})</span>
      </h3>
      {matches.length === 0 ? (
        <p className="text-sm text-ink-3">Хүсээгүй эсвэл олдсонгүй.</p>
      ) : (
        <ul className="divide-y divide-line-soft rounded-xl border border-line bg-surface">
          {matches.map((m) => (
            <li key={m.hltv_id} className="space-y-1 px-4 py-2 text-sm">
              <div className="flex flex-wrap items-baseline gap-x-2">
                {m.match_id && m.maps.some((map) => map.parsed) ? (
                  <Link to={`/matches/${m.match_id}`} className="font-medium text-ct hover:underline">
                    {m.team1} {m.score || 'vs'} {m.team2}
                  </Link>
                ) : (
                  <span className="font-medium text-ink">
                    {m.team1} {m.score || 'vs'} {m.team2}
                  </span>
                )}
                <a href={`https://www.hltv.org${m.url}`} target="_blank" rel="noreferrer" className="text-xs text-ink-3 hover:underline">
                  HLTV
                </a>
                <span className="text-ink-3">{m.tournament}</span>
                <span className="text-ink-3">{m.played_at}</span>
                <span className="ml-auto text-xs text-ink-3">{DEMO[m.demo] ?? m.demo}</span>
              </div>
              {m.maps.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {m.maps.map((map) => (
                    <span key={map.map_number} className={`rounded px-2 py-0.5 text-xs ${map.parsed ? 'bg-good/10 text-good' : 'bg-surface-2 text-ink-3'}`}>
                      {map.map} {map.scoreline} · {map.rounds} раунд
                    </span>
                  ))}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

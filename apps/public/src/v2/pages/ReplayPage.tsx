// v2 screen 02, the 2D Replay: the v1 player in the design's layout, with the
// Round's buys on top, the notes and drawing beside both fives, and the Round's
// key moments (its weightiest Findings) under it.
import { useCallback, useMemo, useRef, useState } from 'react'
import { Navigate, useParams, useSearchParams } from 'react-router'
import { $api } from '../../api/client'
import type { ReplayBridge } from '../../replay/player'
import { CLIP_SECONDS } from '../../review/format'
import { NotesProvider, RoundNotes } from '../../review/Notes'
import type { PenHooks } from '../../review/notesContext'
import { LoadError } from '../../ui/LoadError'
import { PageSkeleton } from '../../ui/Skeleton'
import { CRIT, GOOD, mmss, shortDate } from '../format'
import ReplayV2 from '../ReplayV2'
import { at, useTeam } from '../team'
import { Button, Empty, Panel } from '../ui'

const BUY: Record<string, string> = { pistol: 'Pistol', eco: 'Eco', force: 'Force buy', full: 'Full buy' }

/** /v2/t/:team/replay: the my team's latest parsed Match Map. */
export function ReplayIndex() {
  const team = useTeam()
  const q = $api.useQuery('get', '/v2/teams/{team_id}/matches', { params: { path: { team_id: team.id } } })
  if (q.error) return <LoadError error={q.error} what="Тоглолтууд" retry={() => void q.refetch()} />
  if (!q.data) return <PageSkeleton />
  for (const m of q.data.matches) {
    const mm = m.maps.find((x) => x.parsed)
    if (mm) return <Navigate to={at(team.id, 'replay', m.match_id, mm.map_number)} replace />
  }
  return <Empty>Replay хийх parse хийгдсэн тоглолт алга.</Empty>
}

export default function ReplayPage() {
  const team = useTeam()
  const { matchId = '', mapNumber = '1' } = useParams()
  const match = Number(matchId)
  const n = Number(mapNumber)
  return (
    <NotesProvider key={`${match}-${n}`} matchId={match} mapNumber={n} staff>
      <ReplayBody teamId={team.id} matchId={match} mapNumber={n} />
    </NotesProvider>
  )
}

function ReplayBody({ teamId, matchId, mapNumber }: { teamId: number; matchId: number; mapNumber: number }) {
  const path = { params: { path: { match_id: matchId, map_number: mapNumber } } }
  const detail = $api.useQuery('get', '/matches/{match_id}/maps/{map_number}', path)
  const report = $api.useQuery('get', '/v2/teams/{team_id}/matches/{match_id}/maps/{map_number}/report', {
    params: { path: { team_id: teamId, match_id: matchId, map_number: mapNumber } },
  })
  const review = $api.useQuery('get', '/matches/{match_id}/maps/{map_number}/review', path, {
    staleTime: 5 * 60_000,
    retry: false,
    enabled: !!detail.data?.parsed,
  })
  const [search] = useSearchParams()
  const startRound = Number(search.get('round')) || undefined
  const startAt = useRef<{ t: number; sid: string | null } | null>(
    search.get('t') ? { t: Number(search.get('t')) || 0, sid: search.get('player') } : null,
  )
  const [round, setRound] = useState<number | null>(startRound ?? null)
  const pens = useRef<PenHooks | null>(null)
  const onPens = useCallback((hooks: PenHooks | null) => {
    pens.current = hooks
  }, [])
  const bridge = useMemo<ReplayBridge>(
    () => ({
      pen: () => pens.current?.pen() ?? null,
      onShape: (shape) => pens.current?.onShape(shape),
      shapes: (r, t) => pens.current?.shapes(r, t) ?? [],
      onRound: (r: number) => {
        setRound(r)
        const moment = startAt.current
        if (moment) {
          startAt.current = null
          setTimeout(() => bridge.goto?.(r, moment.t, moment.sid, false), 0)
        }
      },
    }),
    [],
  )
  const goto = useCallback(
    (r: number, t: number, sid: string | null, play = true) => {
      if (bridge.goto) bridge.goto(r, t, sid, play)
      else setRound(r)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    },
    [bridge],
  )
  const [copied, setCopied] = useState(false)
  const share = () => {
    const now = bridge.now?.()
    if (!now) return
    const url = `${window.location.origin}${at(teamId, 'replay', matchId, mapNumber)}?round=${now.round}&t=${now.t}`
    void navigator.clipboard?.writeText(url).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }
  const [recording, setRecording] = useState(false)
  const clip = () => {
    const now = bridge.now?.()
    if (!now || recording) return
    const ok = bridge.record?.(CLIP_SECONDS, (blob) => {
      setRecording(false)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `match${matchId}-map${mapNumber}-R${now.round}-${Math.floor(now.t)}s.webm`
      a.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    })
    if (ok) setRecording(true)
  }

  if (detail.error) return <LoadError error={detail.error} what="Replay" retry={() => void detail.refetch()} />
  if (!detail.data) return <PageSkeleton />
  const { scene, rounds, scoreboard, label, parsed } = detail.data
  if (!scene)
    return (
      <Empty>
        {parsed ? `${label}-ийн tick дата хадгалагдаагүй тул replay хийх боломжгүй.` : `${label} parse хийгдээгүй байна.`}
      </Empty>
    )
  const team1 = { name: scoreboard[0]?.team.name ?? 'Team 1', score: scoreboard[0]?.score ?? null }
  const team2 = { name: scoreboard[1]?.team.name ?? 'Team 2', score: scoreboard[1]?.score ?? null }
  const r = report.data
  const shown = round ?? rounds[0]?.number ?? 1
  const row = r?.rounds.find((x) => x.n === shown)
  const names = Object.fromEntries((review.data?.players ?? []).map((p) => [p.sid, p.name]))
  const moments = (review.data?.findings ?? [])
    .filter((f) => f.round === shown && f.t != null)
    .sort((a, b) => Math.abs(b.swing) - Math.abs(a.swing))
    .slice(0, 6)
    .sort((a, b) => (a.t ?? 0) - (b.t ?? 0))

  return (
    <>
      <ReplayV2
        key={`${matchId}-${mapNumber}`}
        matchId={matchId}
        mapNumber={mapNumber}
        scene={scene}
        rounds={rounds}
        startRound={startRound}
        team1={team1}
        team2={team2}
        bridge={bridge}
        head={
          <span className="lbl">
            {label} · {r?.kind === 'scrim' ? 'Scrim' : 'Албан'} · {shortDate(r?.played_at)} · vs {r?.them?.name}
          </span>
        }
        actions={
          row && (
            <div className="flex flex-wrap gap-2">
              <Badge side={row.side}>
                Бид {(row.side ?? '').toUpperCase()} · {BUY[row.our_buy] ?? row.our_buy} {money(row.ours)}
              </Badge>
              <Badge side={row.side === 'ct' ? 't' : 'ct'}>
                {row.side === 'ct' ? 'T' : 'CT'} · {BUY[row.their_buy] ?? row.their_buy} {money(row.theirs)}
              </Badge>
            </div>
          )
        }
        aside={
          <>
            <div className="flex flex-wrap gap-2">
              <Button onClick={clip} disabled={recording}>
                {recording ? '● Бичиж байна…' : `Клип хадгалах (${CLIP_SECONDS}с)`}
              </Button>
              <Button primary onClick={share}>
                {copied ? 'Холбоос хуулсан ✓' : 'Хуваалцах'}
              </Button>
            </div>
            <div className="rounded-lg border border-line bg-surface p-3.5">
              <RoundNotes round={shown} bridge={bridge} onPens={onPens} names={names} onGoto={goto} />
            </div>
          </>
        }
      />
      <section className="grid grid-cols-[repeat(auto-fit,minmax(min(300px,100%),1fr))] gap-3">
        {review.isPending && detail.data.parsed ? (
          <Empty>Review уншиж байна…</Empty>
        ) : moments.length === 0 ? (
          <Panel>
            <Empty>Энэ раундад Review-ийн онцлох агшин алга.</Empty>
          </Panel>
        ) : (
          moments.map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => goto(shown, Math.max(0, (f.t ?? 0) - 3), f.sids[0] ?? null)}
              className="flex items-start gap-3 rounded-lg border border-line bg-surface p-3.5 text-left hover:border-line-strong"
            >
              <span className="num rounded bg-chip px-2 py-1 text-[13px]">{mmss(f.t)}</span>
              <span className="flex flex-col gap-1">
                <span className="text-sm font-semibold">
                  {f.title}{' '}
                  <span className="num text-xs" style={{ color: f.swing >= 0 ? GOOD : CRIT }}>
                    {f.swing >= 0 ? '+' : ''}
                    {Math.round(100 * f.swing)}%
                  </span>
                </span>
                <span className="text-[13px] leading-snug text-ink-3">{f.text}</span>
              </span>
            </button>
          ))
        )}
      </section>
    </>
  )
}

function money(v: number | null | undefined) {
  return v == null ? '' : `$${v.toLocaleString('mn-MN').replace(/,/g, ' ')}`
}

function Badge({ side, children }: { side: string | null | undefined; children: React.ReactNode }) {
  const ct = side === 'ct'
  return (
    <span
      className="cond rounded px-2.5 py-1.5 text-sm font-semibold"
      style={{ background: ct ? 'var(--ct-soft)' : 'var(--accent-soft)', color: ct ? 'var(--ct)' : 'var(--t)' }}
    >
      {children}
    </span>
  )
}

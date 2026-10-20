import { Link, NavLink, useParams } from 'react-router'
import { $api } from '../api/client'
import type { components } from '../api/schema'
import MapReview from '../review/MapReview'
import MatchOverview from '../review/MatchOverview'

type MatchInfo = components['schemas']['MatchInfo']

/**
 * `/matches/:id` is the Match's «Тойм» (each Team's Summary over its Maps);
 * `/matches/:id/m/:n` is one Map: its Summary, Replay and Round by Round Review.
 */
export default function MatchPage() {
  const { matchId = '', mapNumber } = useParams()
  const id = Number(matchId)
  const match = $api.useQuery('get', '/matches/{match_id}', { params: { path: { match_id: id } } })

  if (match.error) return <p className="text-crit">Тоглолт олдсонгүй.</p>
  if (!match.data) return <p className="text-ink-3">Уншиж байна…</p>
  const info = match.data
  const parsed = info.maps.some((m) => m.parsed)

  return (
    <div className="space-y-6">
      <Header info={info} />
      <MapTabs info={info} />
      {mapNumber !== undefined ? (
        // Keyed: each map starts with its own round and its own Replay bridge.
        <MapReview key={`${id}-${mapNumber}`} matchId={id} mapNumber={Number(mapNumber)} />
      ) : parsed ? (
        <MatchOverview matchId={id} />
      ) : (
        <p className="rounded-xl border border-line bg-surface p-6 text-ink-2">
          None of this match's maps has been parsed, so there is nothing to review. Run an analysis that
          includes {info.hltv_id ? `match ${info.hltv_id}` : 'this match'} first.
        </p>
      )}
    </div>
  )
}

function Header({ info }: { info: MatchInfo }) {
  return (
    <div className="space-y-1">
      <p className="font-mono text-xs text-ink-3">
        {info.team1 && <Link to={`/teams/${info.team1.id}`} className="hover:underline">{info.team1.name}</Link>}
        {info.team1 && info.team2 && ' / '}
        {info.team2 && <Link to={`/teams/${info.team2.id}`} className="hover:underline">{info.team2.name}</Link>}
      </p>
      <h1 className="text-2xl font-semibold text-ink">
        {info.team1?.name ?? '?'} <span className="font-mono">{info.score || '–'}</span>{' '}
        {info.team2?.name ?? (info.opponent_label || '?')}
      </h1>
      <p className="font-mono text-xs text-ink-3">
        {info.tournament || 'unknown event'} ·{' '}
        {info.played_at
          ? new Date(info.played_at).toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
          : 'date unknown'}{' '}
        {info.hltv_url ? (
          <>
            ·{' '}
            <a href={info.hltv_url} target="_blank" rel="noreferrer" className="text-ct hover:underline">HLTV</a>
          </>
        ) : (
          <> · uploaded</>
        )}
        {info.kind === 'scrim' && (
          <span
            title="Scrim: reviewed like a Match, counted in no Own form, habit or Pool"
            className="ml-2 rounded border border-line px-1.5 text-[10px] uppercase tracking-wide text-ink-2"
          >
            scrim
          </span>
        )}
      </p>
    </div>
  )
}

const TAB = ({ isActive }: { isActive: boolean }) =>
  `rounded-t-md border border-b-0 px-4 py-2 text-sm ${isActive ? 'border-line bg-surface text-ink' : 'border-transparent text-ink-2 hover:bg-surface'}`

function MapTabs({ info }: { info: MatchInfo }) {
  return (
    <div className="flex flex-wrap gap-1 border-b border-line">
      <NavLink to={`/matches/${info.id}`} end className={TAB}>
        Тойм
      </NavLink>
      {info.maps.map((m) => {
        const inner = (
          <>
            {m.label}
            <span className="ml-2 font-mono text-xs text-ink-3">{m.scoreline}</span>
          </>
        )
        return m.playable ? (
          <NavLink key={m.map_number} to={`/matches/${info.id}/m/${m.map_number}`} className={TAB}>
            {inner}
          </NavLink>
        ) : (
          <span key={m.map_number} title="Not parsed — nothing to replay" className="px-4 py-2 text-sm text-ink-3">
            {inner}
          </span>
        )
      })}
    </div>
  )
}

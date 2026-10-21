import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router'
import type { components } from '../api/schema'
import { KIND_ORDER } from './format'

type Review = components['schemas']['Review']
type Finding = components['schemas']['ReviewFinding']
type Round = components['schemas']['ReviewRound']

export type Side = 'ct' | 't'
export type Buy = 'pistol' | 'eco' | 'force' | 'full'

/**
 * The Review's filters, kept in the page URL so a link shows the same view:
 * `?team=12&side=t&buy=force&player=7656…&kind=mistake,missed_chance`. The Team
 * and Side also pick which Summary is shown; the rest narrow the Rounds and
 * Findings.
 */
export interface Filters {
  team: number | null
  side: Side | null
  buy: Buy | null
  player: string | null
  kinds: Set<string>
  /** With a Player: every Finding they are in, not only the ones about them. */
  involved: boolean
}

const ALL_KINDS = new Set<string>(KIND_ORDER)

export function useFilters(): [Filters, (patch: Partial<Filters>) => void, () => void] {
  const [params, setParams] = useSearchParams()
  const filters = useMemo<Filters>(() => {
    const team = Number(params.get('team'))
    const side = params.get('side')
    const buy = params.get('buy')
    const kinds = (params.get('kind') || '').split(',').filter((k) => ALL_KINDS.has(k))
    return {
      team: Number.isFinite(team) && team > 0 ? team : null,
      side: side === 'ct' || side === 't' ? side : null,
      buy: buy === 'pistol' || buy === 'eco' || buy === 'force' || buy === 'full' ? buy : null,
      player: params.get('player') || null,
      kinds: kinds.length ? new Set(kinds) : new Set(ALL_KINDS),
      involved: params.get('involved') === '1',
    }
  }, [params])

  const set = useCallback(
    (patch: Partial<Filters>) =>
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          const put = (key: string, value: string | null) => (value ? next.set(key, value) : next.delete(key))
          if ('team' in patch) put('team', patch.team ? String(patch.team) : null)
          if ('side' in patch) put('side', patch.side ?? null)
          if ('buy' in patch) put('buy', patch.buy ?? null)
          if ('player' in patch) put('player', patch.player ?? null)
          if ('involved' in patch) put('involved', patch.involved ? '1' : null)
          if (patch.kinds) {
            const all = patch.kinds.size === 0 || patch.kinds.size === ALL_KINDS.size
            put('kind', all ? null : KIND_ORDER.filter((k) => patch.kinds!.has(k)).join(','))
          }
          return next
        },
        { replace: true },
      ),
    [setParams],
  )
  const clear = useCallback(
    () =>
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          for (const key of ['team', 'side', 'buy', 'player', 'kind', 'involved']) next.delete(key)
          return next
        },
        { replace: true },
      ),
    [setParams],
  )
  return [filters, set, clear]
}

export function isActive(f: Filters): boolean {
  return f.team !== null || f.side !== null || f.buy !== null || f.player !== null || f.kinds.size < ALL_KINDS.size
}

// A Team's Findings: every Player listed shares them, not just the first.
const TEAM_CODES = new Set(['time_out', 'kitless', 'advantage_lost', 'late_execute'])
export const isAbout = (f: Finding, sid: string) =>
  f.sids[0] === sid || (TEAM_CODES.has(f.code) && f.sids.includes(sid))

/** The Side a Team played in a Round, or null when it is neither. */
export function sideOf(r: Round, team: number | null): Side | null {
  if (team === null) return null
  if (r.ct_team_id === team) return 'ct'
  if (r.t_team_id === team) return 't'
  return null
}

/** Does a Round pass the Team, Side and Buy filters? */
export function roundPasses(r: Round, f: Filters): boolean {
  const mine = sideOf(r, f.team)
  if (f.team !== null && mine === null) return false
  if (f.side !== null && f.team !== null && mine !== f.side) return false
  if (f.buy !== null) {
    const sides: Side[] = f.team !== null ? [mine!] : f.side !== null ? [f.side] : ['ct', 't']
    if (!sides.some((s) => (s === 'ct' ? r.ct_buy : r.t_buy) === f.buy)) return false
  }
  return true
}

/** Does a Finding pass every filter (its Round included)? */
export function findingPasses(finding: Finding, f: Filters, rounds: Map<number, Round>): boolean {
  if (!f.kinds.has(finding.kind)) return false
  if (f.player !== null && !(f.involved ? finding.sids.includes(f.player) : isAbout(finding, f.player))) return false
  if (f.team !== null && finding.team_id !== f.team) return false
  if (f.side !== null && finding.side !== f.side) return false
  if (finding.round === null) return f.buy === null && f.side === null
  const r = rounds.get(finding.round)
  if (!r || !roundPasses(r, f)) return false
  if (f.buy !== null && (finding.side === 'ct' ? r.ct_buy : r.t_buy) !== f.buy) return false
  return true
}

/** What the filters leave: the Findings, and the Rounds worth stepping through. */
export function applyFilters(review: Review, f: Filters) {
  const rounds = new Map(review.rounds.map((r) => [r.n, r]))
  const findings = review.findings.filter((x) => findingPasses(x, f, rounds))
  const narrowed = f.player !== null || f.kinds.size < ALL_KINDS.size
  const withFindings = new Set(findings.map((x) => x.round))
  const matching = review.rounds
    .filter((r) => roundPasses(r, f) && (!narrowed || withFindings.has(r.n)))
    .map((r) => r.n)
  return { findings, matching: new Set(matching) }
}

// What each game-plan panel's `data` holds -- the shapes app/services/gameplan_view.py
// builds. The OpenAPI schema types the envelope (GameplanPanel) and leaves `data`
// open because it differs per tab; these are its per-tab shapes.

export type Scope = 'mine' | 'theirs'

export interface DecisionCard {
  value: string
  unit: string
  label: string
  action: string
  detail: string
  tone: string
}
export interface ForecastSeries {
  format: string
  pct: number
  p: number
  word: string
  tone: string
  often: string
  trust: string
}
export interface DecisionForecast {
  series: ForecastSeries[]
  ratings: { team: string; rating: number | null; series: number; region: string; last: string }[]
  maps: { map: string; pct: number; played_mine: number; played_theirs: number }[]
  maps_used: boolean
  limits: string[]
  /** FC-6: what the chance rests on, the Ratings' gap and their trend. */
  why?: string[]
  model: string
}
export interface DecisionPanel {
  decision: {
    call: string
    label: string
    tone: string
    lead: string
    forecast: DecisionForecast
    cards: DecisionCard[]
    moves: { what: string; why: string; tone: string }[]
    confidence: string
  }
  h2h_maps: number
}

export interface VerdictPanel {
  headline: string
  points: string[]
  record: { won: number; lost: number }
  worst_side: string | null
  sample: { my_maps: number; opponent_maps: number; pool_teams: number }
}

export interface TodoPanel {
  actions: { what: string; why: string }[]
  maps: PlaybookMap[]
}

// ----------------------------------------------------------------- Playbook --
export interface PlaybookMap {
  map: string
  label: string
  call: string
  call_label: string
  mine: number
  theirs: number
  h2h: number
}

export type Strength = 'weak' | 'medium' | 'strong'

export interface RoundRef {
  match: number
  map: number
  round: number
}

export interface Evidence {
  n: number
  of: number
  maps: number
  h2h: number
  strength: Strength
  refs: RoundRef[]
  // What n and of count when they are not Rounds (a trade line counts deaths).
  unit?: string
}

export interface Habit {
  kind: string
  title: string
  detail: string
  counter: string
  // What the Reviews add about this Player or place, when they tie to it exactly.
  review?: string
  evidence: Evidence
}

// A Lever (what to use) or a Caution (what to watch out for), CONTEXT.md. A pair
// is my Strength meeting their Weakness (or theirs meeting mine) on facing Sides.
export interface Advice {
  role: 'lever' | 'caution'
  pair: boolean
  title: string
  facts: string[]
  counter: string
  proofs: { whose: 'mine' | 'theirs'; label: string; evidence: Evidence }[]
  strength: Strength
  weight: number
  weight_label: string
}

export interface AdviceSide {
  side: 'ct' | 't'
  label: string
  levers: Advice[]
  cautions: Advice[]
}

export interface TeamSample {
  maps: number
  /** On this Map in the window before the current five's era narrowed them (TM-3). */
  all_maps?: number
  h2h_maps: number
  rounds: { ct: number; t: number }
  economy: boolean
}

export interface PlaybookPanel {
  map: string
  label: string
  my_team: string
  opponent: string
  sample: { theirs: TeamSample; mine: TeamSample }
  /** GP-9: the Rounds the habits were read over, of all of theirs on this Map. */
  view?: { buy?: string; days?: number; rounds: number; of: number }
  sites_known: boolean
  plan: { side: 'ct' | 't'; title: string; counter: string; strength: Strength }[]
  advice: { limits: string[]; sides: AdviceSide[] }
  sections: { key: string; title: string; habits: Habit[] }[]
  pistols: { ref: RoundRef; h2h: boolean; text: string; next: string }[]
  /** GP-5: both Teams' pistols on this Map and what they made of them, against the Pool. */
  conversion: { team: string; pistols: string; converted: string; broken: string; both: string }[]
  economy: {
    known: boolean
    buys?: Record<'eco' | 'force' | 'full', { n: number; won: number }>
    after_pistol_loss?: Record<string, number>
    habits: Habit[]
  }
  players: { player: string; tags: string[]; lines: string[]; duels: string }[]
  self_scout: { side: 'ct' | 't'; label: string; habits: Habit[] }[]
  /** GP-6: the answers that held them below their usual on this Map, with Replay refs. */
  beaten_by: { side: 'ct' | 't'; text: string; evidence: Evidence }[]
  /** GP-11: how readable our first moves are, official Matches only. */
  predictability: { side: 'ct' | 't'; text: string; predictable: boolean }[]
}

export interface MetricRow {
  label: string
  why: string
  value: number
  unit: string
  pool_mean: number
  z: number
}
export interface Profile {
  empty_note: boolean
  maps: number
  rounds: number
  pool_n: number
  strengths: MetricRow[]
  weaknesses: MetricRow[]
  best_relative: MetricRow[]
  worst_relative: MetricRow[]
}
export interface MetricsPanel {
  chart: string
  mine: Profile
  theirs: Profile
}

export interface H2HPanel {
  totals: {
    maps_played?: number
    maps_won?: number
    maps_lost?: number
    map_win_pct?: number
    rounds_for?: number
    rounds_against?: number
  }
  continuity_note: string
  delta_rows: {
    label: string
    why: string
    own: number
    versus: number
    delta: number
    unit: string
    worse: boolean
    // TM-9: past its unit's bar and beyond chance; a sample big enough to tell.
    clear: boolean
    enough: boolean
  }[]
  own_rounds: number
  versus_rounds: number
  chart: string
  by_map: {
    map: string
    map_label: string
    played: number
    won: number
    lost: number
    win_pct: number
    rounds_for: number
    rounds_against: number
    round_diff: number
  }[]
  matches: {
    match_id: number | null
    played_at: string
    my_maps_won: number
    their_maps_won: number
    maps: {
      map_label: string
      map_number: number | null
      my_score: number | null
      their_score: number | null
      won: boolean
    }[]
  }[]
  continuity: {
    stale: boolean
    sides: { scope: Scope; team: string; n: number; of: number; current: string[]; unseen: string[] }[]
  } | null
}

export interface Record_ {
  won: number
  lost: number
  win_pct: number
  thin?: boolean
}
export interface SetupRow {
  name: string
  role: string
  post: string
  post_kills: number
  total_kills: number
  concentration: number
}
export interface PlaceCount {
  place: string
  count: number
}
export interface MapsPanel {
  chart: string
  board: {
    map: string
    map_label: string
    mine: Record_ | null
    theirs: Record_ | null
    h2h: Record_ | null
    call: string
    call_label: string
    confidence: string
  }[]
  bombsite: { healthy: boolean; mismatched: number; checked: number }
  cards: {
    map: string
    map_label: string
    call: string
    call_label: string
    confidence: string
    ours: Record_ | null
    theirs: (Record_ & { median_plant_sec: number | null }) | null
    sides: {
      key: 'ct' | 't'
      label: string
      their_label: string
      plan: string[]
      mine: SetupRow[]
      theirs: SetupRow[]
      their_kills_from: PlaceCount[]
      their_dies_at: PlaceCount[]
    }[]
    cautions: string[]
  }[]
}

export interface Form {
  rounds: number
  adr: number
  kd: number
  kast_pct?: number
  opening_win_pct: number
  opening_kills: number
  opening_deaths: number
  hs_pct: number
}
export interface PlayersPanel {
  cards: {
    scope: Scope
    team: string
    id: number
    name: string
    /** A new signing: the team their numbers come from. */
    elsewhere: string
    roles: { side: string; label: string; role: string; fit: string; declared: boolean; mix: string }[]
    own: Form | null
    vs: Form | null
    instructions: { title: string; text: string; tone: string }[]
    /** What the evidence settles: role KPIs past their test (PL-3), the Reviews' Swing and Findings (PL-7). */
    proven: { strengths: string[]; weaknesses: string[]; tendencies: string[]; swing: string }
  }[]
  hidden: string[]
}

export interface DuelsPanel {
  chart: string
  has_rows: boolean
  totals: { name: string; for: number; against: number; net: number; duels: number }[]
  dropped: { mine: string[]; theirs: string[] }
}

export interface RolesPanel {
  chart: string
  comparison: {
    side: string
    side_label: string
    role: string
    mine: string
    mine_fit: number | null
    theirs: string | null
    theirs_fit: number | null
    delta: number | null
  }[]
  teams: {
    scope: Scope
    team: string
    maps: number
    missing: { side: string; label: string; roles: string[] }[]
    players: {
      name: string
      elsewhere: string
      rating: number | null
      rounds: number
      adr: number
      kd_ratio: number
      sides: {
        side: string
        label: string
        role: string
        confidence: string
        fit: string
        fit_score: number | null
        cohort_size: number | null
        blurb: string
        evidence: { signal: string; value: number | string | null; z: number }[]
      }[]
    }[]
  }[]
}

export interface Linchpin {
  name: string
  player_id: number
  early_deaths: number
  early_won: number
  early_pct: number
  other_rounds: number
  other_won: number
  other_pct: number
  swing: number
  // Against his teammates: of the rounds the team lost its first man early, how much
  // worse it did when that was him, by Side and buy, and whether that beats chance (PL-8).
  first_deaths: number
  vs_teammates: number
  p: number
  significant: boolean
}
export interface EdgePanel {
  teams: {
    scope: Scope
    team: string
    man_advantage: {
      up: { reached: number; won: number; win_pct: number }
      down: { reached: number; won: number; win_pct: number }
      rounds: number
    } | null
    linchpins: Linchpin[]
  }[]
}

// --- the map grid --------------------------------------------------------------
export interface GridIndex {
  maps: string[]
  levels: Record<string, string[]>
  teams: { id: number; name: string; players: { id: number; name: string }[] }[]
  sides: { key: string; label: string }[]
  kinds: { key: string; label: string }[]
  available: Record<string, number>
  combinations: number
}
export interface GridWords {
  map: string
  team: string
  player: string
  all_players: string
  side: string
  pick: string
  nothing: string
  drawing: string
  failed: string
  no_background: string
  floor: string
  floors: { key: string; label: string }[]
  play?: string
  pause?: string
  replay?: string
  step?: string
  scrub?: string
}
export interface GridPanel {
  index: GridIndex
  words: GridWords
}

export interface TableSpec {
  title: string
  note: string
  columns: { label: string; num?: boolean }[]
  rows: { v: string; tone: string | null }[][]
}
export interface SceneStep {
  place: string
  x: number
  y: number
  kills: number
  deaths: number
  counted: boolean
}
export interface SceneRoute {
  route_key: string
  side: string
  player: string
  share: number
  rounds: number
  traced: number
  kills: number
  deaths: number
  verdict: string
  delta: number | null
  colour: string
  steps: SceneStep[]
}
export interface Track {
  route_key: string
  player: string
  side: string
  rounds_seen: number
  points: [number, number][]
  steps: { i: number; place: string }[]
  lvl?: (string | null)[]
}
export interface Scene {
  plate: { url: string | null; width: number; height: number; extent: [number, number, number, number] }
  routes: SceneRoute[]
  labels: { name: string; x: number; y: number }[]
  pooled: boolean
  tracks?: Track[]
}
export interface Shot {
  empty?: boolean
  title?: string
  subtitle?: string
  renderer?: string
  // heatmap
  kind?: string
  cmap?: string
  points?: [number, number][]
  heat?: boolean
  labels?: { name: string; x: number; y: number }[]
  level?: string
  plate?: {
    url: string | null
    lower: string | null
    width: number
    height: number
    extent: [number, number, number, number]
  } | null
  // movement
  routes?: number
  tables?: TableSpec[]
  scene?: Scene | null
}

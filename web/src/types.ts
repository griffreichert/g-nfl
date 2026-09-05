export type PickType = 'regular' | 'best_bet' | 'survivor' | 'underdog' | 'mnf'

export interface WeeksResponse {
  weeks: number[]
  max_week: number | null
  /** The week the pool is on. What a page opens to, in preference to max_week. */
  current_week: number | null
}

export interface AppConfig {
  pickers: string[]
  cur_season: number
  cur_week: number
  survivor_used_teams: string[]
  /** The current season's weeks, so a page needs no second round trip (#124). */
  weeks: WeeksResponse | null
}

export interface GameLine {
  game_id: string
  away_team: string
  home_team: string
  pool_spread: number | null
  market_spread: number | null
  market_total: number | null
  is_mnf: boolean
}

export interface Pick {
  game_id: string
  team_picked: string
  pick_type: PickType
  spread: number | null
  /** why this pick was made, captured at pick time (#70) */
  note?: string | null
}

export interface PickRecord extends Pick {
  picker: string
  season: number
  week: number
  /** When the row was written, ISO 8601. Null on anything saved before #131. */
  submitted_at: string | null
}

export interface RecordStats {
  wins: number
  losses: number
  pushes: number
  pending: number
  win_pct: number | null
}

export interface WeeklyRecord extends RecordStats {
  week: number
  units: number
  cum_units: number
  cum_win_pct: number | null
}

export interface PickerStanding {
  picker: string
  ats: RecordStats
  units: number
  by_type: Record<string, RecordStats>
  no_spread: number
  weekly: WeeklyRecord[]
}

export interface StandingsResponse {
  season: number
  break_even_pct: number
  graded_through_week: number | null
  standings: PickerStanding[]
}

export interface CutRow {
  key: string
  picks: number
  games: number
  /** naive per-pick rate, carried so the inflation stays visible */
  pick_pct: number | null
  /** the honest one: per distinct game, votes on a game collapsed to one */
  pct: number | null
  shrunk_pct: number | null
  units: number
  z: number | null
}

export interface Cut {
  name: string
  label: string
  note: string
  rows: CutRow[]
}

export interface TeamAppetite {
  team: string
  available: number
  picked_games: number
  picks: number
  appetite: number | null
  votes_per_pick: number | null
  pct: number | null
  units: number
}

export interface AnalyticsResponse {
  season: number
  picks: number
  games: number
  votes_per_game: number
  base_pct: number
  break_even_pct: number
  cuts: Cut[]
  teams: TeamAppetite[]
}

export interface InjuryReport {
  team: string
  name: string
  position: string | null
  status: string | null
  practice: string | null
}

export interface TeamWeekStat {
  week: number
  team: string
  plays: number | null
  off_epa_play: number | null
  def_epa_play: number | null
  off_success_rate: number | null
  def_success_rate: number | null
  off_explosive_rate: number | null
  def_explosive_rate: number | null
  off_pass_epa: number | null
  off_rush_epa: number | null
}

export interface GamePick {
  picker: string
  team_picked: string
  pick_type: PickType
  note: string | null
  outcome: string | null
}

/** Context fields are null until scripts/update_game_context.py runs for the week. */
export interface GameDetail {
  game_id: string
  season: number
  week: number
  away_team: string
  home_team: string
  gameday: string | null
  gametime: string | null
  roof: string | null
  surface: string | null
  temp: number | null
  wind: number | null
  stadium: string | null
  div_game: boolean | null
  away_rest: number | null
  home_rest: number | null
  away_qb: string | null
  home_qb: string | null
  away_coach: string | null
  home_coach: string | null
  referee: string | null
  injuries: InjuryReport[]
  pool_spread: number | null
  market_spread: number | null
  market_total: number | null
  away_score: number | null
  home_score: number | null
  result: number | null
  graded_line: number | null
  /** which table graded_line came from — the API decides, not the client */
  graded_line_source: 'pool' | 'market' | null
  team_weeks: TeamWeekStat[]
  picks: GamePick[]
}

/** One fitted veto rule from GET /api/guardrails (#58). */
export interface Guardrail {
  id: string
  label: string
  blurb: string
  /** shrunk hit rate for sides this rule matches */
  pct: number
  /** the field's own rate over the same sample */
  base_pct: number
  games: number
  picks: number
  units: number
  bad_seasons: number
  seasons: number
  /** reads data unavailable at pick time, so it advises and never vetoes */
  advisory: boolean
  reason: string
}

export interface SideFlag {
  game_id: string
  team: string
  rule_ids: string[]
}

export interface GuardrailsResponse {
  season: number
  week: number | null
  rules: Guardrail[]
  /** fitted and rejected, kept so the room can see what did not survive */
  rejected: Guardrail[]
  flags: SideFlag[]
  fitted_on: number[]
}

export interface LoginResponse {
  /** empty on /api/auth/me, which only confirms an existing token */
  token: string
  picker: string
}

export interface LedgerWeek {
  week: number
  entry: string
  points: number
  available: number
  running: number
  /** which member "Best member" was following that week */
  leader: string | null
}

export interface LedgerEntry {
  entry: string
  points: number
  available: number
  weeks: number
  share: number | null
}

export interface LedgerResponse {
  season: number
  weeks: LedgerWeek[]
  standings: LedgerEntry[]
}

/** One team's game in one week — a square of the season matrix. */
export interface SurvivorCell {
  team: string
  week: number
  game_id: string
  opponent: string
  home: boolean
  /** this team's own margin, positive = favoured */
  spread: number
  win_prob: number
  /** 'market' when a book has priced it, 'model' from power ratings */
  source: 'market' | 'model'
  /** the margin's standard deviation, widened by whatever is doubted here */
  stdev: number
}

/** What one picker thinks of one team, past what the ratings say. */
export interface SurvivorBelief {
  team: string
  /**
   * How well this team's rating holds up across a season, 1-5, 3 = no
   * opinion. 5 is "they are this all year"; 1 is an injury or a hot seat
   * away from being someone else. Bites harder the further out the week is.
   */
  confidence: number
  /** set only when reading the whole room's beliefs for comparison */
  picker?: string | null
}

export interface SurvivorLeg {
  week: number
  team: string
  /** absent on a pick already played */
  prob: number | null
  /** reserved by you, as opposed to placed by the solver */
  pinned: boolean
}

export interface SurvivorBestWeek {
  week: number
  win_prob: number
  spread: number | null
}

export interface SurvivorCandidate {
  team: string
  opponent: string | null
  home: boolean | null
  spread: number | null
  win_prob: number
  /** survival of the best plan that spends this team here */
  plan_survival: number
  /** log-survival given up versus the unconstrained plan; 0 = free */
  forward_cost: number | null
  /** the week this team is strongest, the reason to wait */
  best_week: SurvivorBestWeek | null
}

export interface SurvivorResponse {
  season: number
  week: number
  picker: string | null
  spent: string[]
  history: SurvivorLeg[]
  pins: Record<string, string>
  weeks: number[]
  cells: SurvivorCell[]
  plan: SurvivorLeg[]
  survival: number | null
  /** the same solve without your pins — what insisting costs */
  best_survival: number | null
  candidates: SurvivorCandidate[]
  /** team -> confidence actually applied to this board */
  doubts: Record<string, number>
  ratings_through: { season: number; week: number }
  generated_at: string
}

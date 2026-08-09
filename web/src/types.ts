export type PickType = 'regular' | 'best_bet' | 'survivor' | 'underdog' | 'mnf'

export interface AppConfig {
  pickers: string[]
  cur_season: number
  cur_week: number
  survivor_used_teams: string[]
}

export interface WeeksResponse {
  weeks: number[]
  max_week: number | null
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

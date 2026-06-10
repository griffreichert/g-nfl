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
}

export interface PickRecord extends Pick {
  picker: string
  season: number
  week: number
}

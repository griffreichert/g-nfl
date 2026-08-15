import type { GameDetail, InjuryReport, PickType, TeamWeekStat } from '../types'

export const SLOT_LABEL: Record<PickType, string> = {
  regular: 'Regular',
  best_bet: 'Best bet',
  survivor: 'Survivor',
  underdog: 'Underdog',
  mnf: 'MNF',
}

/** Out first — the report is read for who is missing, not alphabetically. */
const STATUS_ORDER = ['out', 'doubtful', 'questionable']
const statusRank = (s: string | null) => {
  const i = STATUS_ORDER.indexOf((s ?? '').toLowerCase())
  return i === -1 ? STATUS_ORDER.length : i
}

/** Away team first, then home, then anything the feed gave us that is neither. */
export function groupInjuries(
  injuries: InjuryReport[],
  away: string,
  home: string,
): { team: string; players: InjuryReport[] }[] {
  const byTeam = new Map<string, InjuryReport[]>()
  for (const i of injuries) byTeam.set(i.team, [...(byTeam.get(i.team) ?? []), i])
  const rest = [...byTeam.keys()].filter((t) => t !== away && t !== home).sort()
  return [away, home, ...rest]
    .filter((t) => byTeam.has(t))
    .map((team) => ({
      team,
      players: byTeam
        .get(team)!
        .sort((a, b) => statusRank(a.status) - statusRank(b.status) || a.name.localeCompare(b.name)),
    }))
}

export interface EpaPoint {
  week: number
  awayOff: number | null
  awayDef: number | null
  homeOff: number | null
  homeDef: number | null
}

/** Both teams' EPA/play on one week axis. A bye leaves a null, not a gap in x. */
export function epaSeries(stats: TeamWeekStat[], away: string, home: string): EpaPoint[] {
  const weeks = [...new Set(stats.map((s) => s.week))].sort((a, b) => a - b)
  const at = (team: string, week: number) => stats.find((s) => s.team === team && s.week === week)
  return weeks.map((week) => {
    const a = at(away, week)
    const h = at(home, week)
    return {
      week,
      awayOff: a?.off_epa_play ?? null,
      awayDef: a?.def_epa_play ?? null,
      homeOff: h?.off_epa_play ?? null,
      homeDef: h?.def_epa_play ?? null,
    }
  })
}

const CONTEXT_FIELDS = [
  'roof',
  'surface',
  'temp',
  'wind',
  'stadium',
  'div_game',
  'away_rest',
  'home_rest',
  'away_qb',
  'home_qb',
  'away_coach',
  'home_coach',
  'referee',
] as const

/** False until scripts/update_game_context.py has pushed this week. */
export const hasContext = (g: GameDetail) =>
  CONTEXT_FIELDS.some((k) => g[k] !== null && g[k] !== undefined)

export function fmtKickoff(gameday: string | null, gametime: string | null): string | null {
  if (!gameday) return gametime
  // Parsed with an explicit time: a bare YYYY-MM-DD is UTC midnight, which
  // renders as the day before anywhere west of Greenwich.
  const d = new Date(`${gameday}T00:00:00`)
  const day = Number.isNaN(d.getTime())
    ? gameday
    : d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
  return gametime ? `${day} · ${gametime}` : day
}

/** `result` is the home margin, same convention as the pool spread. */
export function marginLabel(g: Pick<GameDetail, 'result' | 'away_team' | 'home_team'>) {
  if (g.result === null || g.result === undefined) return null
  if (g.result === 0) return 'Tie'
  return `${g.result > 0 ? g.home_team : g.away_team} by ${Math.abs(g.result)}`
}

/** Spread from one team's side; stored home-perspective, as everywhere else. */
export const sideSpread = (spread: number | null, team: string, home: string) =>
  spread === null ? null : team === home ? spread : -spread

import type { GameLine, PickRecord, PickType } from '../types'

/** The entry Reichert actually submits — an output, so it never votes in the consensus. */
export const TEAM_PICKER = 'TEAM'

/** Pool points a pick is worth (#62): best bet 2, regular and MNF 1 each.
 *  Survivor and underdog are separate pools and never enter the spread consensus. */
const WEIGHT: Partial<Record<PickType, number>> = { best_bet: 2, regular: 1, mnf: 1 }

export interface SidePick {
  picker: string
  bb: boolean
}

export interface ConsensusRow {
  game: GameLine
  /** the side the field leans to; on a dead split, the away team */
  side: string
  other: string
  /** pool spread from `side`'s perspective */
  spread: number | null
  /** headcount on `side` */
  pk: number
  /** best bets among them */
  bb: number
  /** weighted points for `side` minus the other side — never negative */
  net: number
  sidePicks: SidePick[]
  otherPicks: SidePick[]
  teamPick: string | null
  /** false when TEAM went against the field; null when TEAM has no pick */
  teamAgrees: boolean | null
}

/** Pool spread carried as the away-team number, so flip it for the home side. */
export function spreadFor(game: GameLine, team: string) {
  if (game.pool_spread === null) return null
  return team === game.away_team ? game.pool_spread : -game.pool_spread
}

export function buildConsensus(games: GameLine[], picks: PickRecord[]): ConsensusRow[] {
  const byGame = new Map<string, PickRecord[]>()
  for (const p of picks) {
    if (!(p.pick_type in WEIGHT)) continue
    const list = byGame.get(p.game_id)
    if (list) list.push(p)
    else byGame.set(p.game_id, [p])
  }

  const rows = games.map((game) => {
    const gamePicks = byGame.get(game.game_id) ?? []
    const team = gamePicks.find((p) => p.picker === TEAM_PICKER)
    const field = gamePicks.filter((p) => p.picker !== TEAM_PICKER)

    const points = (t: string) =>
      field
        .filter((p) => p.team_picked === t)
        .reduce((sum, p) => sum + (WEIGHT[p.pick_type] ?? 0), 0)
    const on = (t: string): SidePick[] =>
      field
        .filter((p) => p.team_picked === t)
        .map((p) => ({ picker: p.picker, bb: p.pick_type === 'best_bet' }))
        .sort((a, b) => a.picker.localeCompare(b.picker))

    const away = points(game.away_team)
    const home = points(game.home_team)
    const [side, other] = home > away ? [game.home_team, game.away_team] : [game.away_team, game.home_team]
    const sidePicks = on(side)

    return {
      game,
      side,
      other,
      spread: spreadFor(game, side),
      pk: sidePicks.length,
      bb: sidePicks.filter((p) => p.bb).length,
      net: Math.abs(home - away),
      sidePicks,
      otherPicks: on(other),
      teamPick: team?.team_picked ?? null,
      teamAgrees: team ? team.team_picked === side : null,
    }
  })

  // strongest agreement first; dead splits sink to the bottom, where the call has work to do
  return rows
    .filter((r) => r.sidePicks.length + r.otherPicks.length > 0 || r.teamPick !== null)
    .sort(
      (a, b) => b.net - a.net || b.pk - a.pk || a.game.away_team.localeCompare(b.game.away_team),
    )
}

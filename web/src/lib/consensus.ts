import type { GameLine, PickRecord, PickType } from '../types'

/** The entry Reichert actually submits — an output, so it never votes in the consensus. */
export const TEAM_PICKER = 'TEAM'

/** Pool points a pick is worth (#62): best bet 2, regular and MNF 1 each.
 *  Survivor and underdog are separate pools and never enter the spread consensus. */
const WEIGHT: Partial<Record<PickType, number>> = { best_bet: 2, regular: 1, mnf: 1 }

export const isAtsPick = (t: PickType) => t in WEIGHT

/**
 * Spread bands, from `notes/team-page-consensus-analysis.md`.
 * 2025, 777 graded ATS picks by the eight of us, graded on the pool line.
 * The only cut in that dataset significant at both tails, and the reason the
 * board is banded at all.
 *
 * ponytail: hard-coded rather than served from an endpoint — one season, and
 * it moves once a year. Recompute with scratch/analysis when 2026 grades out.
 */
export const BANDS = [
  { max: 3, label: '0-3', pct: 57.1, n: 238, tone: 'good' },
  { max: 7, label: '3-7', pct: 44.0, n: 365, tone: 'bad' },
  { max: Infinity, label: '7+', pct: 42.2, n: 174, tone: 'bad' },
] as const

export type Band = (typeof BANDS)[number]

export const bandFor = (spread: number | null): Band | null =>
  spread === null ? null : (BANDS.find((b) => Math.abs(spread) < b.max) ?? BANDS[BANDS.length - 1])

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
  band: Band | null
  /** headcount on `side` */
  pk: number
  /** best bets among them */
  bb: number
  /** weighted points for `side` minus the other side — never negative */
  net: number
  /** independent blocs on each side, after collapsing pickers who always agree */
  blocSide: number
  blocOther: number
  /** 0 = unanimous, 1 = dead split. How much the call has left to decide. */
  contention: number
  sidePicks: SidePick[]
  otherPicks: SidePick[]
  teamPick: string | null
  /** false when TEAM went against the field; null when TEAM has no pick */
  teamAgrees: boolean | null
}

/**
 * Pool spread is stored home-perspective, same convention as nflverse
 * `spread_line` (positive = home favored). Verified against 2025: corr with
 * `spread_line` = +0.99.
 */
export function spreadFor(game: GameLine, team: string) {
  if (game.pool_spread === null) return null
  return team === game.home_team ? game.pool_spread : -game.pool_spread
}

/**
 * Pickers who pick the same side often enough that counting both double-counts
 * one opinion. Ben submits bModel verbatim (69/69 in 2025), so a "5-2" that
 * contains both is really 4-2.
 */
export function findBlocs(picks: PickRecord[], threshold = 0.9, minGames = 10): string[][] {
  const byPicker = new Map<string, Map<string, string>>()
  for (const p of picks) {
    if (!isAtsPick(p.pick_type) || p.picker === TEAM_PICKER) continue
    const m = byPicker.get(p.picker) ?? new Map()
    m.set(p.game_id, p.team_picked)
    byPicker.set(p.picker, m)
  }

  const names = [...byPicker.keys()].sort()
  // union-find over "agrees >= threshold on >= minGames shared games"
  const parent = new Map(names.map((n) => [n, n]))
  const find = (x: string): string => {
    const p = parent.get(x)!
    if (p === x) return x
    const r = find(p)
    parent.set(x, r)
    return r
  }

  for (let i = 0; i < names.length; i++) {
    for (let j = i + 1; j < names.length; j++) {
      const a = byPicker.get(names[i])!
      const b = byPicker.get(names[j])!
      let shared = 0
      let agree = 0
      for (const [gid, team] of a) {
        const other = b.get(gid)
        if (other === undefined) continue
        shared++
        if (other === team) agree++
      }
      if (shared >= minGames && agree / shared >= threshold) {
        parent.set(find(names[i]), find(names[j]))
      }
    }
  }

  const groups = new Map<string, string[]>()
  for (const n of names) {
    const root = find(n)
    groups.set(root, [...(groups.get(root) ?? []), n])
  }
  return [...groups.values()].filter((g) => g.length > 1).sort((a, b) => b.length - a.length)
}

/** How many independent opinions a list of pickers really represents. */
function blocCount(picks: SidePick[], blocs: string[][]): number {
  const seen = new Set<number>()
  let count = 0
  for (const p of picks) {
    const idx = blocs.findIndex((b) => b.includes(p.picker))
    if (idx === -1) count++
    else if (!seen.has(idx)) {
      seen.add(idx)
      count++
    }
  }
  return count
}

export function buildConsensus(
  games: GameLine[],
  picks: PickRecord[],
  blocs: string[][] = [],
): ConsensusRow[] {
  const byGame = new Map<string, PickRecord[]>()
  for (const p of picks) {
    if (!isAtsPick(p.pick_type)) continue
    const list = byGame.get(p.game_id)
    if (list) list.push(p)
    else byGame.set(p.game_id, [p])
  }

  const rows = games.map((game): ConsensusRow => {
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
    const [side, other] =
      home > away ? [game.home_team, game.away_team] : [game.away_team, game.home_team]
    const sidePicks = on(side)
    const otherPicks = on(other)
    const spread = spreadFor(game, side)

    const blocSide = blocCount(sidePicks, blocs)
    const blocOther = blocCount(otherPicks, blocs)
    const totalBlocs = blocSide + blocOther

    return {
      game,
      side,
      other,
      spread,
      band: bandFor(spread),
      pk: sidePicks.length,
      bb: sidePicks.filter((p) => p.bb).length,
      net: Math.abs(home - away),
      blocSide,
      blocOther,
      // 1 when the independent blocs are evenly split, 0 when they all agree
      contention: totalBlocs === 0 ? 0 : blocOther / Math.max(blocSide, blocOther) || 0,
      sidePicks,
      otherPicks,
      teamPick: team?.team_picked ?? null,
      teamAgrees: team ? team.team_picked === side : null,
    }
  })

  return rows.filter((r) => r.sidePicks.length + r.otherPicks.length > 0 || r.teamPick !== null)
}

/**
 * Call agenda order: most contested first.
 *
 * Deliberately the opposite of ranking by agreement. In 2025 the unanimous
 * games went 45.2% and the contested ones 52.4%, and consensus strength
 * predicted nothing overall — so the games worth the room's time are the ones
 * it hasn't settled, not the ones it has.
 */
export const byContention = (a: ConsensusRow, b: ConsensusRow) =>
  b.contention - a.contention ||
  b.sidePicks.length + b.otherPicks.length - (a.sidePicks.length + a.otherPicks.length) ||
  a.game.away_team.localeCompare(b.game.away_team)

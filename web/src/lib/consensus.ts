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

/**
 * Whose club is whose. A homer vote is a picker backing their own team, which
 * is the one bias the room can name out loud.
 *
 * Hunter's CLE is the real one; he drifts to CHI and WAS, so all three count.
 * Models have no club. Griffin's list is Chuck's neighbour, not a typo — three
 * of the eight are Browns fans.
 */
export const HOMER_TEAMS: Record<string, string[]> = {
  Ben: ['WAS'],
  Chuck: ['CHI'],
  Hunter: ['CLE', 'CHI', 'WAS'],
  Harry: ['CLE'],
  Griffin: ['CLE'],
}

/**
 * What the call was worth in 2025, from `notes/team-page-consensus-analysis.md`.
 * TEAM took 39.5% of available pool points — last, behind every individual
 * member — while following the field majority on 82 of its 83 games. The room
 * is not being paid to average; it is being paid to disagree. This is the
 * uncomfortable number and it belongs where the picks get made.
 *
 * ponytail: hard-coded alongside BANDS, same reasoning — one season, and it
 * moves once a year. Recompute when 2026 grades out.
 */
export const TEAM_2025 = { rate: 39.5, rubberStamp: '82 of 83', best: 'bModel', bestRate: 54.0 }

/** Break-even at -110, and the field's own rate across all 777 graded 2025 picks. */
export const BREAK_EVEN = 52.4
const FIELD_BASE = 48.5

/**
 * How many times this season a picker has already taken a given team.
 * Key is `picker|team`. Built from the season fetch the board already makes.
 */
export function buildAttachment(seasonPicks: PickRecord[]): Map<string, number> {
  const counts = new Map<string, number>()
  for (const p of seasonPicks) {
    if (!isAtsPick(p.pick_type) || p.picker === TEAM_PICKER) continue
    const key = `${p.picker}|${p.team_picked}`
    counts.set(key, (counts.get(key) ?? 0) + 1)
  }
  return counts
}

/** Prior picks on this team, not counting the one being scored. */
const priorPicks = (attachment: Map<string, number>, picker: string, team: string) =>
  Math.max(0, (attachment.get(`${picker}|${team}`) ?? 0) - 1)

/** Backing the same team this many times is a habit, not a read. */
const ATTACH_MIN = 4

export const isHomer = (picker: string, team: string) =>
  (HOMER_TEAMS[picker] ?? []).includes(team)

/**
 * Homer and attachment are judgement, not history: nothing in the dataset
 * grades them, so their combined effect is floored here. They exist to nudge a
 * tie, never to outvote the spread band.
 */
const JUDGEMENT_FLOOR = -6

export interface ScorePart {
  label: string
  /** points of expected ATS%, signed against break-even */
  value: number
  /** false when the number is a judgement call rather than something we graded */
  measured: boolean
}

export interface Score {
  /** 0-10. 5.0 is break-even at -110; above 5 is worth a slot. */
  rating: number
  /** rating points per point of expected ATS%, for rendering the breakdown */
  slope: number
  parts: ScorePart[]
}

/**
 * The best and worst a side can realistically look, in points of expected ATS%
 * against break-even. Best is a close line the room is split on, taken on the
 * road. Worst is a big line everyone agreed on at home, with a slot or a
 * judgement flag on top.
 */
const BEST_CASE = 10.2
const WORST_CASE = 20

/**
 * Percentage points to a 0-10 rating, anchored so 5.0 is the -110 break-even.
 *
 * The underlying numbers are hit rates off one season, and a rate printed to a
 * decimal invites more trust than n=238 has earned. The rating keeps the
 * ordering and drops the false precision — nothing on the board claims to be a
 * win probability.
 *
 * The two sides of 5 use different slopes on purpose. Losing sides run much
 * further from break-even than winning ones do (a 7+ line is -10.2 on its own,
 * before anything else), so a single slope pinned most of the board at 0.0 and
 * threw away the ordering exactly where the room needs it: choosing the least
 * bad of six mediocre games.
 */
export const toRating = (edgePoints: number) =>
  edgePoints >= 0
    ? Math.min(10, 5 + (edgePoints / BEST_CASE) * 5)
    : Math.max(0, 5 + (edgePoints / WORST_CASE) * 5)

/** Scale a part by the same slope the total used, so a breakdown adds up. */
export const partRating = (value: number, slope: number) => value * slope

const BAND_LABEL: Record<string, string> = {
  '0-3': 'close line',
  '3-7': 'mid line',
  '7+': 'big line',
}

export function scoreSide(
  row: ConsensusRow,
  team: string,
  attachment: Map<string, number>,
): Score {
  const picks = team === row.side ? row.sidePicks : row.otherPicks
  const parts: ScorePart[] = []
  const add = (label: string, value: number, measured = true) => {
    if (value !== 0) parts.push({ label, value, measured })
  }

  // Every term is a delta against break-even, so the breakdown sums to the pill.
  // Band and contention describe the game, so both sides carry them. Slot,
  // venue and the judgement terms are what actually separate the two sides.
  add(
    row.band ? BAND_LABEL[row.band.label] : 'no pool line',
    (row.band?.pct ?? FIELD_BASE) - BREAK_EVEN,
  )

  const contested = row.blocSide > 0 && row.blocOther > 0
  add(contested ? "we're split" : 'we all agree', contested ? 3.9 : -3.3)
  if (picks.some((p) => p.bb)) add('best-bet slot', -7.1)

  const isHome = team === row.game.home_team
  add(isHome ? 'home side' : 'road side', isHome ? -3.3 : 1.6)

  // judgement terms, floored so they can never swamp the band
  const homers = picks.filter((p) => isHomer(p.picker, team))
  const attached = picks.filter((p) => priorPicks(attachment, p.picker, team) >= ATTACH_MIN)
  const judgement = Math.max(JUDGEMENT_FLOOR, homers.length * -3 + attached.length * -1.5)
  if (judgement !== 0) {
    const who = [
      homers.length ? `${homers.map((p) => p.picker).join(', ')} homer` : '',
      attached.length ? `${attached.map((p) => p.picker).join(', ')} stuck on them` : '',
    ]
      .filter(Boolean)
      .join(' \u00b7 ')
    parts.push({ label: who, value: judgement, measured: false })
  }

  const edge = parts.reduce((sum, p) => sum + p.value, 0)
  const rating = toRating(edge)
  return { rating, slope: edge === 0 ? 0 : (rating - 5) / edge, parts }
}

/** The better of the two sides — what this game is worth to the room at all. */
export const bestSide = (row: ConsensusRow, attachment: Map<string, number>) => {
  const a = scoreSide(row, row.side, attachment)
  const b = scoreSide(row, row.other, attachment)
  return a.rating >= b.rating
    ? { team: row.side, score: a, other: row.other, otherScore: b }
    : { team: row.other, score: b, other: row.side, otherScore: a }
}

/**
 * Board order: best expected side first, most contested breaking ties.
 *
 * This is not "most agreed first" wearing a hat — agreement is a negative term
 * in the score, so a unanimous 7+ point favourite sorts to the bottom, which is
 * exactly where 2025 says it belongs.
 */
export const byScore =
  (best: Map<string, number>) => (a: ConsensusRow, b: ConsensusRow) =>
    (best.get(b.game.game_id) ?? 0) - (best.get(a.game.game_id) ?? 0) ||
    b.contention - a.contention ||
    a.game.away_team.localeCompare(b.game.away_team)

import type { GameLine, PickRecord, PickType } from '../types'

/** The entry Reichert actually submits — an output, so it never votes in the consensus. */
export const TEAM_PICKER = 'TEAM'
/** Scratch profile for exercising the save path against real data. */
export const TEST_PICKER = 'TEST'
/** Neither of these is an opinion, so neither counts toward the field. */
const NON_VOTING = new Set([TEAM_PICKER, TEST_PICKER])
export const isVoter = (picker: string) => !NON_VOTING.has(picker)

/** Pool points a pick is worth (#62): best bet 2, regular and MNF 1 each.
 *  Survivor and underdog are separate pools and never enter the spread consensus. */
const WEIGHT: Partial<Record<PickType, number>> = { best_bet: 2, regular: 1, mnf: 1 }

export const isAtsPick = (t: PickType) => t in WEIGHT

/**
 * Spread bands crossed with venue. 2020-2025, every graded ATS pick on a pool
 * line from the six seasons #56 recovered, against 2025 alone before.
 *
 * Each game-side is weighted by the share of the room on it, so a game split
 * 3-3 contributes 0.5 to each side and cancels, while a 6-0 game counts fully.
 * The previous build counted each game-side once instead — but the room takes
 * both sides of 54% of the games it picks (82% in 2025), and for those the two
 * rows are exact complements, so the table was measuring which team covered
 * rather than whether the room was right. Rates are then shrunk toward the
 * lean-weighted base of 47.8% so a thin cell cannot shout.
 *
 * Three of six cells reversed under the correction. The clearest casualty was
 * "home 3-7", previously the worst cell at 41.8% off 71 games and now 50.8%.
 * Per-season stability tables are in `notes/pick-behaviour.md`.
 *
 * What survived: line size crossed with venue. What did not: the best-bet
 * slot, venue on its own, and whether the room was split.
 *
 * ponytail: hard-coded rather than served from an endpoint — it moves once a
 * year. Recompute when 2026 grades out.
 */
export const BANDS = [
  { max: 3, label: '0-3', pct: 50.4, n: 219, tone: 'good' },
  { max: 7, label: '3-7', pct: 48.5, n: 410, tone: 'bad' },
  { max: Infinity, label: '7+', pct: 44.4, n: 235, tone: 'bad' },
] as const

/**
 * Shrunk ATS% by band and venue — the one cut with anything left in it.
 *
 * The stable cells, and the two worth acting on: **road sides of a 7+ line are
 * 39.3%**, and bad in all four full seasons (34.7 / 36.3 / 38.8 / 41.8), while
 * **home sides of a close game are 45.5%**, also bad in all four (42.6 / 45.5 /
 * 45.7 / 47.0). "7+ home" is the unstable one (27.7 to 66.7), which is why
 * shrinkage leaves it near the base rate.
 */
export const BAND_VENUE: Record<string, { home: number; road: number }> = {
  '0-3': { home: 45.5, road: 53.7 },
  '3-7': { home: 50.8, road: 46.6 },
  '7+': { home: 50.6, road: 39.3 },
}

export type Band = (typeof BANDS)[number]

/**
 * The single worst thing we buy: a road favourite laying 7 or more.
 * 33.6% over 336 picks across 2020-2025 (z = -5.46 on the pool-line subset),
 * and negative in every season — 32.4%, 24.1%, 28.6%, 40.1%. The same games
 * covered 42.5% from the road side league-wide, so the cell is mildly bad and
 * our selection inside it is much worse. The home side of those same games
 * went 55.8% when we took it.
 *
 * This replaces an earlier "home side laying or getting 3-7" claim built on 71
 * games of 2025. Over six seasons that cell is 49.3% (n = 740) — neutral. See
 * notes/pick-behaviour.md.
 *
 * Exposed as its own predicate rather than left implicit in the rating,
 * because the pick pages have no rating on them and this is where the
 * money actually leaves.
 */
export const WORST_CELL = {
  label: 'road favourite of 7+',
  pct: 33.6,
  games: 336,
  league: 42.5,
} as const

/** `spread` is home-perspective, the nflverse convention. */
export const isWorstCell = (spread: number | null, pickedHome: boolean) =>
  !pickedHome && spread !== null && spread <= -7

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
    if (!isAtsPick(p.pick_type) || !isVoter(p.picker)) continue
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
    const field = gamePicks.filter((p) => isVoter(p.picker))

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

/** Break-even at -110, and the field's own rate over 225 graded 2025 games. */
export const BREAK_EVEN = 52.4
const FIELD_BASE = 47.4

/**
 * How many times this season a picker has already taken a given team.
 * Key is `picker|team`. Built from the season fetch the board already makes.
 */
export function buildAttachment(seasonPicks: PickRecord[]): Map<string, number> {
  const counts = new Map<string, number>()
  for (const p of seasonPicks) {
    if (!isAtsPick(p.pick_type) || !isVoter(p.picker)) continue
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
  // One measured term now, not four: line size crossed with venue. The slot,
  // venue-alone and split-vs-unanimous terms that used to sit here all shrank
  // onto the base rate once games stopped being counted once per vote, so
  // keeping them at any weight would be fitting noise. See BANDS.
  const isHome = team === row.game.home_team
  const bandLabel = row.band ? BAND_LABEL[row.band.label] : null
  const measured = row.band
    ? BAND_VENUE[row.band.label][isHome ? 'home' : 'road']
    : FIELD_BASE
  add(
    bandLabel ? `${bandLabel}, ${isHome ? 'home' : 'road'}` : 'no pool line',
    measured - BREAK_EVEN,
  )

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


/**
 * The entry Reichert submits each week: one best bet at 2pts, five regulars at
 * 1pt, and the Monday game. All on distinct games (notes/SCORING.md), which one
 * pick per game gives us for free.
 */
export type SlotType = 'best_bet' | 'regular' | 'mnf'
export type SlotPick = { team: string; type: SlotType }
export type Slate = Record<string, SlotPick>
/** A room decision that overrules the proposal; null means "we took this off". */
export type Overrides = Record<string, SlotPick | null>

export const MAX_REGULAR = 5

export const slotCounts = (slate: Slate) => {
  const v = Object.values(slate)
  return {
    regular: v.filter((x) => x.type === 'regular').length,
    bb: v.filter((x) => x.type === 'best_bet').length,
    mnf: v.filter((x) => x.type === 'mnf').length,
  }
}

/**
 * What one tap on a side does, as a patch over the current slate.
 *
 * Unpicked, regular, best bet, unpicked — the same cycle the picks page uses.
 * Two rules the room expects and would otherwise have to discover:
 *
 * - Tapping the *other* side of a game already in the entry switches sides and
 *   keeps the slot. It does not silently demote a best bet to a regular.
 * - Promoting a second side to best bet demotes the incumbent to a regular
 *   rather than refusing. The swap is net-zero on the regular count, so it can
 *   never overflow the entry.
 *
 * Returns an empty patch when the tap is a no-op (a full slate, new game).
 */
export function cycleSlot(slate: Slate, gameId: string, team: string, isMnf: boolean): Overrides {
  const now = slate[gameId]
  const counts = slotCounts(slate)

  if (isMnf) return { [gameId]: now?.team === team ? null : { team, type: 'mnf' } }

  if (!now || now.team !== team) {
    if (!now && counts.regular >= MAX_REGULAR && counts.bb > 0) return {}
    return {
      [gameId]: {
        team,
        type: now ? now.type : counts.regular < MAX_REGULAR ? 'regular' : 'best_bet',
      },
    }
  }

  if (now.type === 'regular') {
    const patch: Overrides = { [gameId]: { team, type: 'best_bet' } }
    const incumbent = Object.entries(slate).find(([, v]) => v.type === 'best_bet')
    if (incumbent) patch[incumbent[0]] = { ...incumbent[1], type: 'regular' }
    return patch
  }

  return { [gameId]: null }
}

/**
 * How the pool line compares to the market on one side of a game.
 *
 * Positive `edge` means the pool is giving this side more points than the
 * market does. Picks made into a negative edge went 45.2% over 1098 picks
 * (z = -3.20); a non-negative edge went 49.9%. That is the largest single
 * leak in six seasons of picks.
 *
 * Read it as a nudge, not an instruction. The 45.2% is measured against the
 * closing line, which nobody has when picks are due, and the market number
 * this app stores is pulled ~66 hours before kickoff — earlier than the pool
 * line itself. See notes/pool-spread-edge.md.
 *
 * Both spreads are home-perspective, the nflverse convention.
 */
export const poolEdge = (
  poolSpread: number | null,
  marketSpread: number | null,
  pickedHome: boolean,
): number | null => {
  if (poolSpread === null || marketSpread === null) return null
  const gap = marketSpread - poolSpread
  return pickedHome ? gap : -gap
}

export const POOL_EDGE = { badPct: 45.2, badGames: 1098, okPct: 49.9 } as const

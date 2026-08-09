import type { CutRow, TeamAppetite } from '../types'

export const fmtPct = (p: number | null | undefined) =>
  p === null || p === undefined ? '—' : `${(p * 100).toFixed(1)}%`

export const fmtUnits = (u: number) => `${u > 0 ? '+' : ''}${u.toFixed(2)}`

/**
 * A cell that landed exactly on the base rate.
 *
 * `shrink()` returns `base` unchanged when method of moments finds no excess
 * spread between the cells, so this equality is the backend saying "this split
 * carries nothing" rather than a rounding coincidence. The epsilon only guards
 * the JSON round-trip. Rows that pass this must not be read as findings.
 */
export const isFlat = (row: CutRow, base: number) =>
  row.shrunk_pct !== null && Math.abs(row.shrunk_pct - base) < 1e-9

export const cutHasSignal = (rows: CutRow[], base: number) =>
  rows.some((r) => !isFlat(r, base))

/** The naive per-pick rate only differs from the per-game rate where the room
 *  doubled up. One pick per game (the picker cut) leaves nothing to inflate,
 *  so striking it through there would imply an error that isn't in the number. */
export const isInflated = (row: CutRow) =>
  row.pick_pct !== null && row.pct !== null && Math.abs(row.pick_pct - row.pct) > 5e-4

/**
 * Took them in three of every five chances and hit at least this far under the
 * field's own rate. Median appetite is 0.62, so a bare "above half" catches
 * fourteen teams and says nothing; and half the room is below the base rate by
 * construction, so the rate needs daylight too. Per-team samples are ~15
 * games — this names a habit, it does not establish one.
 */
export const HABIT_APPETITE = 0.6
export const HABIT_GAP = 0.05

export const isHabit = (t: TeamAppetite, base: number) =>
  (t.appetite ?? 0) >= HABIT_APPETITE && t.pct !== null && t.pct < base - HABIT_GAP

export type TeamSortKey = 'team' | 'appetite' | 'picked_games' | 'picks' | 'pct' | 'units'

/**
 * Sort the team table. Nulls sort last in both directions — a team nobody
 * picked has no rate, which is not the same as the worst rate. Ties break on
 * team code so the order is stable across re-sorts.
 */
export function sortTeams(
  teams: TeamAppetite[],
  key: TeamSortKey,
  desc: boolean,
): TeamAppetite[] {
  return [...teams].sort((a, b) => {
    if (key === 'team') {
      return desc ? b.team.localeCompare(a.team) : a.team.localeCompare(b.team)
    }
    const x = a[key]
    const y = b[key]
    if (x === null || y === null) {
      if (x === y) return a.team.localeCompare(b.team)
      return x === null ? 1 : -1
    }
    if (x === y) return a.team.localeCompare(b.team)
    return desc ? y - x : x - y
  })
}

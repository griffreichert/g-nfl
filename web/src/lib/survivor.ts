import type { SurvivorCell, SurvivorLeg } from '../types'

/**
 * The survivor planner's pure parts (#72), kept out of the page so they
 * can be tested — the repo has no React test harness, only node --test
 * over the lib.
 */

export const LAST_WEEK = 18
export const ALL_WEEKS = Array.from({ length: LAST_WEEK }, (_, i) => i + 1)

/** Confidence runs 1-5 and 3 is no opinion, so a fresh board is untouched. */
export const NEUTRAL = 3
export const STEPS = [1, 2, 3, 4, 5]

export const STEP_LABELS: Record<number, string> = {
  1: 'could be anyone by December',
  2: 'shaky',
  3: 'no opinion',
  4: 'steady',
  5: 'this all season',
}

export type Pins = Record<number, string>

/**
 * Click a square: pin it, unpin it, or move that team's pin here.
 *
 * A team holds at most one pin, because it can be spent at most once —
 * so pinning it somewhere new has to release the old week rather than
 * reserve it twice.
 */
export function togglePin(pins: Pins, team: string, week: number): Pins {
  const next: Pins = { ...pins }
  if (next[week] === team) {
    delete next[week]
    return next
  }
  for (const [w, t] of Object.entries(next)) if (t === team) delete next[Number(w)]
  next[week] = team
  return next
}

/** The week a team is reserved for, if any. */
export function reservedWeek(pins: Pins, team: string): number | null {
  const hit = Object.entries(pins).find(([, t]) => t === team)
  return hit ? Number(hit[0]) : null
}

/**
 * Win probability as ink, not as a traffic light.
 *
 * Green and red are spoken for by win/loss everywhere else on the site
 * (index.css), so a plan must never be readable as a result. 35% is
 * invisible, 85% is solid.
 */
export function shade(winProb: number): string {
  const t = Math.max(0, Math.min(1, (winProb - 0.35) / 0.5))
  return `color-mix(in srgb, var(--pick) ${Math.round(t * 82)}%, transparent)`
}

/**
 * Rows read top to bottom the way the plan reads left to right: the team
 * the solver spends first is the first row, unplanned teams sink to the
 * bottom ordered by their best week, and spent teams sit at the end.
 */
export function sortTeams(
  cells: SurvivorCell[],
  plan: SurvivorLeg[],
  spent: string[]
): string[] {
  const planned = new Map(plan.map((l) => [l.team, l.week]))
  const best = new Map<string, number>()
  for (const c of cells) best.set(c.team, Math.max(best.get(c.team) ?? 0, c.win_prob))
  const live = [...new Set(cells.map((c) => c.team))]
  return [...live, ...spent.filter((t) => !best.has(t))].sort((a, b) => {
    const aw = planned.get(a) ?? LAST_WEEK + 1
    const bw = planned.get(b) ?? LAST_WEEK + 1
    if (aw !== bw) return aw - bw
    return (best.get(b) ?? -1) - (best.get(a) ?? -1)
  })
}

/**
 * What the pins cost, as a share of the survival the solver could have
 * had without them. This is the number that keeps the solver a tool: it
 * prices your preference instead of overriding it.
 */
export function pinCost(survival: number | null, best: number | null): number {
  if (!survival || !best) return 0
  return 1 - survival / best
}

/**
 * A candidate's forward cost is reported in log-survival. Turn it into
 * the share of the season's survival given up, which is what a person
 * can actually weigh.
 */
export function costShare(forwardCost: number | null | undefined): number {
  return 1 - Math.exp(-(forwardCost ?? 0))
}

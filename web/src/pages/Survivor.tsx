import { useCallback, useEffect, useMemo, useState } from 'react'
import { Pin, RotateCcw, Skull } from 'lucide-react'
import { api, teamLogo } from '../api'
import PageHeader from '../components/PageHeader'
import { EmptyState, ErrorNote, Loading } from '../components/PageState'
import { useAuth, useConfig, useSeasonWeek } from '../hooks'
import {
  ALL_WEEKS,
  costShare,
  pinCost,
  reservedWeek,
  shade,
  sortTeams,
  togglePin,
  type Pins,
} from '../lib/survivor'
import type { SurvivorCell, SurvivorResponse } from '../types'

/**
 * Survivor planning as an assignment over the whole season (#72).
 *
 * The pool takes one team a week and never gives it back, so the question
 * is never "who is the biggest favourite on Sunday" — it is which weeks
 * have nothing good in them, and which team you are saving for those. The
 * solver answers that; this page is where you argue with it, by reserving
 * teams for weeks and watching what the insistence costs.
 *
 * Three states a team can be in, and they are the solver's own vocabulary:
 * spent (submitted, gone), reserved (your pin, movable), free (the solver
 * places it). A reserved team greys out in every week except its own, in
 * both directions — one use, and the plan says which week it is.
 */

const read = (key: string | null): Pins => {
  if (!key) return {}
  try {
    return JSON.parse(localStorage.getItem(key) ?? '{}')
  } catch {
    return {}
  }
}

/**
 * Pins survive a reload but never reach the database — a plan is a sketch,
 * and only a submitted pick spends a team.
 *
 * Storage is read while rendering rather than in an effect, so switching
 * season shows that season's pins on the first paint instead of flashing
 * the previous one.
 */
function usePins(season: number | null) {
  const key = season ? `nohomers.survivor.pins.${season}` : null
  const stored = useMemo(() => read(key), [key])
  const [edited, setEdited] = useState<{ key: string | null; pins: Pins } | null>(null)
  const pins = edited && edited.key === key ? edited.pins : stored

  const write = useCallback(
    (next: Pins) => {
      setEdited({ key, pins: next })
      if (key) localStorage.setItem(key, JSON.stringify(next))
    },
    [key]
  )

  const toggle = useCallback(
    (team: string, week: number) => write(togglePin(pins, team, week)),
    [pins, write]
  )

  return { pins, toggle, clear: () => write({}) }
}

const pct = (p: number | null | undefined, dp = 0) =>
  p === null || p === undefined ? '—' : `${(p * 100).toFixed(dp)}%`

const fmtSpread = (s: number | null | undefined) =>
  s === null || s === undefined ? '' : s > 0 ? `-${Math.abs(s)}` : `+${Math.abs(s)}`

export default function Survivor() {
  const { picker } = useAuth()
  const { config } = useConfig(picker ?? undefined)
  const { season, setSeason, week, setWeek, weeks, seasons } = useSeasonWeek(config)
  const { pins, toggle, clear } = usePins(season)

  // Which week the drawer ranks. Clicking a column focuses it; changing the
  // week selector drops that focus, which is why the choice is stored with
  // the week it was made for rather than reset in an effect.
  const [focus, setFocus] = useState<{ of: number; week: number } | null>(null)
  const ranked = focus && focus.of === week ? focus.week : week
  const focusWeek = (w: number) => week !== null && setFocus({ of: week, week: w })

  const [data, setData] = useState<SurvivorResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (season === null || week === null) return
    api
      .survivor(season, week, picker ?? undefined, pins, ranked ?? undefined)
      .then((d) => {
        setData(d)
        setError(null)
      })
      .catch((e) => setError(String(e)))
  }, [season, week, picker, pins, ranked])

  const byTeamWeek = useMemo(() => {
    const m = new Map<string, SurvivorCell>()
    for (const c of data?.cells ?? []) m.set(`${c.team}|${c.week}`, c)
    return m
  }, [data])

  const planned = useMemo(() => {
    const m = new Map<string, number>()
    for (const leg of data?.plan ?? []) m.set(leg.team, leg.week)
    return m
  }, [data])

  const spent = useMemo(() => new Set(data?.spent ?? []), [data])
  const playedWeek = useMemo(() => {
    const m = new Map<number, string>()
    for (const leg of data?.history ?? []) m.set(leg.week, leg.team)
    return m
  }, [data])

  const teams = useMemo(
    () => sortTeams(data?.cells ?? [], data?.plan ?? [], data?.spent ?? []),
    [data]
  )

  if (error) return <ErrorNote>{error}</ErrorNote>
  if (season === null || week === null || !data) return <Loading />
  if (!data.cells.length)
    return (
      <EmptyState
        title="No board for this season"
        detail="Run make survivor-board to generate it, then commit the artifact."
      />
    )

  const cost = pinCost(data.survival, data.best_survival)
  const pinCount = Object.keys(data.pins).length

  return (
    <div className="space-y-5">
      <PageHeader
        title="Survivor"
        season={season}
        seasons={seasons}
        onSeason={setSeason}
        week={week}
        weeks={weeks}
        onWeek={setWeek}
      />

      {/* What the plan is worth, and what your pins cost it. */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border border-border bg-card px-4 py-3">
        <div>
          <p className="text-xs text-muted-foreground">Survive to week 18</p>
          <p className="text-2xl font-bold tabular-nums">{pct(data.survival, 2)}</p>
        </div>
        {pinCount > 0 && (
          <div>
            <p className="text-xs text-muted-foreground">
              {pinCount} pin{pinCount > 1 ? 's' : ''} cost you
            </p>
            <p className="text-2xl font-bold tabular-nums">{pct(cost, 0)}</p>
          </div>
        )}
        <p className="ml-auto max-w-sm text-xs text-muted-foreground">
          Ratings through {data.ratings_through.season} wk {data.ratings_through.week}.
          A week the book has priced uses the real line; the rest use the ratings.
        </p>
        {pinCount > 0 && (
          <button
            onClick={clear}
            className="flex h-8 items-center gap-1.5 rounded-md border border-border px-3 text-xs font-medium hover:bg-muted"
          >
            <RotateCcw className="size-3.5" /> Clear pins
          </button>
        )}
      </div>

      {/* The season as one line: what you spent, and what the plan spends next. */}
      <div className="overflow-x-auto">
        <div className="flex min-w-max gap-1">
          {ALL_WEEKS.map((w) => {
            const played = playedWeek.get(w)
            const leg = data.plan.find((l) => l.week === w)
            const team = played ?? leg?.team
            const isRanked = w === ranked
            return (
              <button
                key={w}
                onClick={() => focusWeek(w)}
                className={`w-[52px] rounded-md border p-1.5 text-center transition-colors ${
                  isRanked ? 'border-primary bg-accent' : 'border-border bg-card hover:bg-muted'
                }`}
              >
                <p className="text-[10px] text-muted-foreground">wk {w}</p>
                {team ? (
                  <img
                    src={teamLogo(team)}
                    alt={team}
                    className={`mx-auto size-7 ${played ? 'grayscale' : ''} ${
                      leg && !leg.pinned && !played ? 'opacity-45' : ''
                    }`}
                  />
                ) : (
                  <div className="mx-auto size-7" />
                )}
                <p className="truncate text-[10px] font-medium tabular-nums">
                  {played ? 'spent' : leg?.pinned ? 'pinned' : pct(leg?.prob)}
                </p>
              </button>
            )
          })}
        </div>
      </div>

      {/* The matrix. A row's bright square three weeks out is the whole point. */}
      <div className="overflow-x-auto rounded-lg border border-border bg-card">
        <table className="min-w-max border-separate border-spacing-0 text-[10px]">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-card px-2 py-1 text-left font-medium text-muted-foreground">
                team
              </th>
              {ALL_WEEKS.map((w) => (
                <th
                  key={w}
                  onClick={() => focusWeek(w)}
                  className={`w-8 cursor-pointer px-0 py-1 text-center font-medium ${
                    w === ranked ? 'text-primary' : 'text-muted-foreground'
                  } ${w < week ? 'opacity-40' : ''}`}
                >
                  {w}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {teams.map((team) => {
              const isSpent = spent.has(team)
              const reserved = reservedWeek(pins, team)
              return (
                <tr key={team} className={isSpent ? 'opacity-35' : ''}>
                  <td className="sticky left-0 z-10 bg-card px-2 py-0.5">
                    <span className="flex items-center gap-1.5">
                      <img src={teamLogo(team)} alt="" className="size-4" />
                      <span className={`font-medium ${isSpent ? 'line-through' : ''}`}>
                        {team}
                      </span>
                    </span>
                  </td>
                  {ALL_WEEKS.map((w) => {
                    const cell = byTeamWeek.get(`${team}|${w}`)
                    const pinnedHere = pins[w] === team
                    const suggested = !pinnedHere && planned.get(team) === w
                    // reserved elsewhere: still a real game, but not yours to spend
                    const blocked = reserved !== null && reserved !== w
                    if (!cell)
                      return (
                        <td key={w} className="h-6 w-8 border-b border-border/40 text-center">
                          <span className="text-muted-foreground/40">
                            {isSpent || w < week ? '' : '·'}
                          </span>
                        </td>
                      )
                    return (
                      <td
                        key={w}
                        onClick={() => !isSpent && toggle(team, w)}
                        title={`${team} ${cell.home ? 'vs' : '@'} ${cell.opponent} ${fmtSpread(
                          cell.spread
                        )} · ${pct(cell.win_prob)} · ${cell.source}`}
                        className={`h-6 w-8 cursor-pointer border-b border-border/40 text-center tabular-nums transition-opacity ${
                          blocked ? 'opacity-25' : ''
                        } ${pinnedHere ? 'ring-2 ring-inset ring-primary' : ''} ${
                          suggested ? 'ring-1 ring-inset ring-primary/40' : ''
                        }`}
                        style={{ backgroundColor: shade(cell.win_prob) }}
                      >
                        {Math.round(cell.win_prob * 100)}
                      </td>
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <span className="size-3 rounded-sm ring-2 ring-inset ring-primary" /> pinned by you
        </span>
        <span className="flex items-center gap-1">
          <span className="size-3 rounded-sm ring-1 ring-inset ring-primary/40" /> the solver's
          suggestion
        </span>
        <span className="flex items-center gap-1">
          <Skull className="size-3" /> struck through = spent, gone for good
        </span>
        <span>click a square to reserve that team for that week</span>
      </p>

      {/* The week in question, ranked by what each pick costs the season. */}
      <div>
        <h2 className="mb-2 text-sm font-semibold">
          Week {ranked} — every pick priced against the whole season
        </h2>
        {data.candidates.length === 0 ? (
          <EmptyState
            title={
              ranked !== null && ranked < week
                ? `Week ${ranked} is behind you`
                : 'Nothing legal left for this week'
            }
            detail={
              ranked !== null && ranked < week
                ? 'Planning starts at the week the pool is on.'
                : undefined
            }
          />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border bg-card">
            <table className="w-full min-w-max text-sm">
              <thead className="text-xs text-muted-foreground">
                <tr className="border-b border-border">
                  <th className="px-3 py-2 text-left font-medium">team</th>
                  <th className="px-3 py-2 text-left font-medium">game</th>
                  <th className="px-3 py-2 text-right font-medium">win now</th>
                  <th className="px-3 py-2 text-right font-medium">peaks</th>
                  <th className="px-3 py-2 text-right font-medium">costs</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {data.candidates.slice(0, 12).map((c) => {
                  const free = (c.forward_cost ?? 0) < 1e-9
                  const pinnedHere = pins[ranked as number] === c.team
                  return (
                    <tr key={c.team} className="border-b border-border/50 last:border-0">
                      <td className="px-3 py-1.5">
                        <span className="flex items-center gap-2 font-medium">
                          <img src={teamLogo(c.team)} alt="" className="size-5" />
                          {c.team}
                        </span>
                      </td>
                      <td className="px-3 py-1.5 text-muted-foreground">
                        {c.home ? 'vs' : '@'} {c.opponent} {fmtSpread(c.spread)}
                      </td>
                      <td className="px-3 py-1.5 text-right tabular-nums">
                        {pct(c.win_prob)}
                      </td>
                      <td className="px-3 py-1.5 text-right tabular-nums text-muted-foreground">
                        {c.best_week && c.best_week.week !== ranked
                          ? `${pct(c.best_week.win_prob)} wk ${c.best_week.week}`
                          : 'here'}
                      </td>
                      <td
                        className={`px-3 py-1.5 text-right tabular-nums ${
                          free ? 'text-muted-foreground' : ''
                        }`}
                      >
                        {free ? 'free' : pct(costShare(c.forward_cost), 0)}
                      </td>
                      <td className="px-3 py-1.5 text-right">
                        <button
                          onClick={() => toggle(c.team, ranked as number)}
                          className={`flex h-7 items-center gap-1 rounded-md border px-2 text-xs font-medium ${
                            pinnedHere
                              ? 'border-primary bg-accent text-primary'
                              : 'border-border hover:bg-muted'
                          }`}
                        >
                          <Pin className="size-3" />
                          {pinnedHere ? 'pinned' : 'pin'}
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-2 text-xs text-muted-foreground">
          "Costs" is how much whole-season survival you give up by spending that team
          here rather than letting the plan place it. A team that peaks later and costs
          nothing is one the plan has no better use for.
        </p>
      </div>
    </div>
  )
}

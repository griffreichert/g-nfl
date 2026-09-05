import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from './api'
import type { AppConfig, GuardrailsResponse } from './types'

export { useAuth } from './auth-context'

/**
 * Season, week, pickers and the survivor teams already spent.
 *
 * `picker` matters: the ban on reusing a survivor team is per entry, so the
 * list is empty until the API knows whose entry it is. It used to be one
 * global list in config.py covering the whole room.
 */
export function useConfig(picker?: string) {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    api.config(picker).then(setConfig).catch((e) => setError(String(e)))
  }, [picker])
  return { config, error }
}

// The last season/week a picker landed on, for a bare route to fall back to.
// A URL segment always wins when it's there; this only fills the gap a route
// without a week (Performance, Analytics, or a bare /picks after a fresh
// load) can't carry on its own — Picks wk8 -> Performance -> back to Picks
// used to snap to the current week because Performance's URL has no week to
// hand back. `SEASON_KEY` alone is what Performance/Analytics write, so
// picking a season there is remembered even though those pages have no week.
const SEASON_KEY = 'nohomers.season'
const WEEK_KEY = 'nohomers.week'

const readStored = <T,>(key: string): T | null => {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

const writeStored = (key: string, value: unknown) => {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Storage can be unavailable (private mode, quota) — the choice just
    // stops persisting, which is no worse than before this existed.
  }
}

/**
 * Season + week selectors, driven by the URL with the last visited pair as
 * the fallback default (#126 follow-up). An explicit URL
 * (`/picks/2026/week/8`) always wins; a bare route (`/picks`) resolves to
 * wherever the picker was last, or the current season/week on a first visit,
 * and then settles the address bar on the explicit form via a replace — so
 * every page has one shareable URL and the nav tabs always have a season/week
 * to carry into whichever tab is clicked next.
 */
export function useSeasonWeekRoute(
  config: AppConfig | null,
  buildPath: (season: number, week: number) => string,
) {
  const params = useParams<{ season?: string; week?: string }>()
  const navigate = useNavigate()
  const paramSeason = params.season ? Number(params.season) : null
  // Read once, on mount, rather than on every render: localStorage is a
  // mutable external source the compiler can't treat as a stable dependency,
  // and re-reading it live would let a write from one mounted selector (this
  // page, or briefly the one it's navigating from) change what another is
  // computing mid-render.
  const [stored] = useState(() =>
    paramSeason === null ? readStored<{ season: number; week: number }>(WEEK_KEY) : null,
  )
  const [storedSeason] = useState(() => readStored<number>(SEASON_KEY))
  const season = paramSeason ?? stored?.season ?? storedSeason ?? config?.cur_season ?? null

  const [fetched, setFetched] = useState<{ season: number; weeks: number[] } | null>(null)

  // The current season's weeks ride along on /api/config, so the common case
  // costs no request at all. Config, then weeks, then lines used to run in
  // series before a page could paint (#124).
  const inline = config?.weeks && season === config.cur_season ? config.weeks : null

  const weeks = useMemo(() => {
    const rows = inline?.weeks ?? (fetched?.season === season ? fetched.weeks : null)
    if (!rows) return []
    return rows.length ? rows : Array.from({ length: 18 }, (_, i) => i + 1)
  }, [inline, fetched, season])

  useEffect(() => {
    if (season === null || inline) return
    api.weeks(season).then((r) => setFetched({ season, weeks: r.weeks }))
  }, [season, inline])

  // Open on the week the pool is on, which holds until that week's last game
  // is graded. `max_week` is the furthest week we hold lines for, so it jumps
  // to 18 the moment anyone snapshots the whole season ahead.
  const opening = weeks.length
    ? (inline?.current_week ?? inline?.max_week ?? weeks[weeks.length - 1])
    : null
  const paramWeek = params.week ? Number(params.week) : null
  const week =
    paramWeek !== null && weeks.includes(paramWeek)
      ? paramWeek
      : paramSeason === null && stored?.season === season && weeks.includes(stored.week)
        ? stored.week
        : opening

  useEffect(() => {
    if (season === null || week === null) return
    writeStored(WEEK_KEY, { season, week })
    writeStored(SEASON_KEY, season)
    if (paramSeason === season && paramWeek === week) return
    navigate(buildPath(season, week), { replace: true })
    // Only the resolved values and what the URL currently holds decide
    // whether a redirect is due; buildPath is a fresh closure every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [season, week, paramSeason, paramWeek])

  const setSeason = (s: number) => {
    if (week === null) return
    navigate(buildPath(s, week))
  }
  const setWeek = (w: number) => {
    if (season === null) return
    navigate(buildPath(season, w))
  }

  const seasons = config
    ? Array.from({ length: config.cur_season - 2019 }, (_, i) => 2020 + i)
    : []

  return { season, setSeason, week, setWeek, weeks, seasons }
}

/** Season-only version of {@link useSeasonWeekRoute}, for pages that read a whole season. */
export function useSeasonRoute(config: AppConfig | null, buildPath: (season: number) => string) {
  const params = useParams<{ season?: string }>()
  const navigate = useNavigate()
  const paramSeason = params.season ? Number(params.season) : null
  const [stored] = useState(() => readStored<{ season: number; week: number }>(WEEK_KEY))
  const [storedSeason] = useState(() => readStored<number>(SEASON_KEY))
  const season = paramSeason ?? stored?.season ?? storedSeason ?? config?.cur_season ?? null

  useEffect(() => {
    if (season === null) return
    writeStored(SEASON_KEY, season)
    if (paramSeason === season) return
    navigate(buildPath(season), { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [season, paramSeason])

  const setSeason = (s: number) => navigate(buildPath(s))

  const seasons = config
    ? Array.from({ length: config.cur_season - 2019 }, (_, i) => 2020 + i)
    : []

  return { season, setSeason, seasons }
}

export const fmtSpread = (s: number | null | undefined) =>
  s === null || s === undefined ? 'TBD' : `${s > 0 ? '+' : ''}${s}`

/**
 * One colour per pool slot, shared by the ribbon dots, both picks pages, and
 * every promote button, so a pick reads as what it is everywhere it shows up
 * (#126 follow-up). `pick` covers Regular; the rest name their own slot.
 */
export type PoolColor = 'pick' | 'bb' | 'mnf' | 'underdog' | 'survivor'

/** Icon/dot colour, e.g. `text-bb`. */
export const POOL_TEXT: Record<PoolColor, string> = {
  pick: 'text-pick',
  bb: 'text-bb',
  mnf: 'text-mnf',
  underdog: 'text-underdog',
  survivor: 'text-survivor',
}

/** A filled shadcn `Button`'s tone once a slot is picked. */
export const POOL_TONE: Record<PoolColor, string> = {
  pick: 'bg-pick text-primary-foreground hover:bg-pick/90',
  bb: 'bg-bb text-primary-foreground hover:bg-bb/90',
  mnf: 'bg-mnf text-primary-foreground hover:bg-mnf/90',
  underdog: 'bg-underdog text-primary-foreground hover:bg-underdog/90',
  survivor: 'bg-survivor text-primary-foreground hover:bg-survivor/90',
}

/** A bordered pill/chip button (`SlotButton`, `PoolPicker`) in its on/off states. */
export const POOL_BUTTON: Record<PoolColor, { on: string; off: string }> = {
  pick: {
    on: 'border-pick bg-pick text-primary-foreground',
    off: 'border-pick/40 text-pick hover:border-pick hover:bg-pick/10',
  },
  bb: {
    on: 'border-bb bg-bb text-primary-foreground',
    off: 'border-bb/40 text-bb hover:border-bb hover:bg-bb/10',
  },
  mnf: {
    on: 'border-mnf bg-mnf text-primary-foreground',
    off: 'border-mnf/40 text-mnf hover:border-mnf hover:bg-mnf/10',
  },
  underdog: {
    on: 'border-underdog bg-underdog text-primary-foreground',
    off: 'border-underdog/40 text-underdog hover:border-underdog hover:bg-underdog/10',
  },
  survivor: {
    on: 'border-survivor bg-survivor text-primary-foreground',
    off: 'border-survivor/40 text-survivor hover:border-survivor hover:bg-survivor/10',
  },
}

/**
 * The fitted guardrails, and which sides of this week trip them (#58).
 *
 * Rules and rates both come from the API. The board holds no constants of its
 * own, so it cannot drift from the record the way the old hard-coded band
 * table did.
 */
export function useGuardrails(season: number | null, week: number | null) {
  const [data, setData] = useState<GuardrailsResponse | null>(null)

  useEffect(() => {
    if (season === null) return
    let live = true
    api
      .guardrails(season, week ?? undefined)
      .then((r) => live && setData(r))
      // a missing fit must not take the board down with it
      .catch(() => live && setData(null))
    return () => {
      live = false
    }
  }, [season, week])

  // Both memoised on `data`. The board derives its whole ranking from these,
  // and rebuilding them every render gave them a fresh identity every render,
  // which is why the memos downstream had to leave them out of their
  // dependencies and went stale instead (#124).
  return useMemo(() => {
    const flagged = new Map<string, string[]>()
    for (const f of data?.flags ?? []) flagged.set(`${f.game_id}|${f.team}`, f.rule_ids)
    const byId = new Map((data?.rules ?? []).map((r) => [r.id, r]))
    return {
      guardrails: data,
      /** rule ids this side trips, empty when it is clean */
      flagsFor: (gameId: string, team: string) => flagged.get(`${gameId}|${team}`) ?? [],
      ruleById: (id: string) => byId.get(id),
    }
  }, [data])
}

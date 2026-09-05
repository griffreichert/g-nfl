import { useEffect, useMemo, useState } from 'react'
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

/** Season + week selectors, weeks loaded from the API for the chosen season */
export function useSeasonWeek(config: AppConfig | null) {
  // The season defaults to the config's current one until someone picks another,
  // so it is derived rather than synced across from config in an effect.
  const [chosen, setSeason] = useState<number | null>(null)
  const season = chosen ?? config?.cur_season ?? null
  // Held with the season it was chosen for, so switching season falls back to
  // that season's opening week without an effect resetting it afterwards.
  const [picked, setPicked] = useState<{ season: number; week: number } | null>(null)
  const [fetched, setFetched] = useState<{ season: number; weeks: number[] } | null>(null)

  // The current season's weeks ride along on /api/config, so the common case
  // costs no request at all. Config, then weeks, then lines used to run in
  // series before a page could paint (#124).
  const inline =
    config?.weeks && season === config.cur_season ? config.weeks : null

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
  const week =
    picked && picked.season === season && weeks.includes(picked.week)
      ? picked.week
      : opening

  const setWeek = (w: number) => season !== null && setPicked({ season, week: w })

  const seasons = config
    ? Array.from({ length: config.cur_season - 2019 }, (_, i) => 2020 + i)
    : []

  return { season, setSeason, week, setWeek, weeks, seasons }
}

export const fmtSpread = (s: number | null | undefined) =>
  s === null || s === undefined ? 'TBD' : `${s > 0 ? '+' : ''}${s}`

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

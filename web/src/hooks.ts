import { useEffect, useState } from 'react'
import { api } from './api'
import type { AppConfig, GuardrailsResponse } from './types'

export function useConfig() {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    api.config().then(setConfig).catch((e) => setError(String(e)))
  }, [])
  return { config, error }
}

/** Season + week selectors, weeks loaded from the API for the chosen season */
export function useSeasonWeek(config: AppConfig | null) {
  // The season defaults to the config's current one until someone picks another,
  // so it is derived rather than synced across from config in an effect.
  const [chosen, setSeason] = useState<number | null>(null)
  const season = chosen ?? config?.cur_season ?? null
  const [week, setWeek] = useState<number | null>(null)
  const [weeks, setWeeks] = useState<number[]>([])

  useEffect(() => {
    if (season === null) return
    api.weeks(season).then((r) => {
      const ws = r.weeks.length ? r.weeks : Array.from({ length: 18 }, (_, i) => i + 1)
      setWeeks(ws)
      setWeek((w) => (w !== null && ws.includes(w) ? w : r.max_week ?? ws[ws.length - 1]))
    })
  }, [season])

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

  const flagged = new Map<string, string[]>()
  for (const f of data?.flags ?? []) flagged.set(`${f.game_id}|${f.team}`, f.rule_ids)

  const byId = new Map((data?.rules ?? []).map((r) => [r.id, r]))

  return {
    guardrails: data,
    /** rule ids this side trips, empty when it is clean */
    flagsFor: (gameId: string, team: string) => flagged.get(`${gameId}|${team}`) ?? [],
    ruleById: (id: string) => byId.get(id),
  }
}

import { useEffect, useState } from 'react'
import { api } from './api'
import type { AppConfig } from './types'

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

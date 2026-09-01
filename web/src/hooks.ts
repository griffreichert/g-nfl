import { useEffect, useState } from 'react'
import { api, token } from './api'
import type { AppConfig, GuardrailsResponse } from './types'

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
  const [week, setWeek] = useState<number | null>(null)
  const [weeks, setWeeks] = useState<number[]>([])

  useEffect(() => {
    if (season === null) return
    api.weeks(season).then((r) => {
      const ws = r.weeks.length ? r.weeks : Array.from({ length: 18 }, (_, i) => i + 1)
      setWeeks(ws)
      // Open on the week the pool is on, which holds until that week's last
      // game is graded. `max_week` is the furthest week we hold lines for, so
      // it jumps to 18 the moment anyone snapshots the whole season ahead.
      setWeek((w) =>
        w !== null && ws.includes(w)
          ? w
          : r.current_week ?? r.max_week ?? ws[ws.length - 1]
      )
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

/**
 * Who is signed in (#60).
 *
 * The picker used to be a dropdown, and the API believed it, so anyone could
 * submit as anyone. Now a PIN buys a token, the token names the picker, and
 * the dropdown is gone.
 */
export function useAuth() {
  const [picker, setPicker] = useState<string | null>(null)
  // No token means nothing to check, so the gate opens on the first render
  // rather than after an effect has run and set state again.
  const [checking, setChecking] = useState(() => token.get() !== null)

  useEffect(() => {
    if (!token.get()) return
    let live = true
    api
      .me()
      .then((r) => live && setPicker(r.picker))
      // an expired or tampered token is the same as no token
      .catch(() => {
        token.clear()
        if (live) setPicker(null)
      })
      .finally(() => live && setChecking(false))
    return () => {
      live = false
    }
  }, [])

  const login = async (who: string, passphrase: string) => {
    const r = await api.login(who, passphrase)
    token.set(r.token)
    setPicker(r.picker)
  }

  const logout = () => {
    token.clear()
    setPicker(null)
  }

  return { picker, checking, login, logout }
}

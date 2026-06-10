import { useEffect, useMemo, useState } from 'react'
import { api, teamLogo } from '../api'
import { fmtSpread, useConfig, useSeasonWeek } from '../hooks'
import type { PickRecord } from '../types'

const typeEmoji: Record<string, string> = {
  best_bet: '⭐️',
  survivor: '💀',
  underdog: '🐶',
  mnf: '🌙',
}

export default function ViewPicks() {
  const { config, error: configError } = useConfig()
  const { season, setSeason, week, setWeek, weeks, seasons } = useSeasonWeek(config)
  const [picks, setPicks] = useState<PickRecord[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (season === null || week === null) return
    api
      .picks(season, week)
      .then((p) => {
        setPicks(p)
        setError(null)
      })
      .catch((e) => setError(String(e)))
  }, [season, week])

  const byPicker = useMemo(() => {
    const grouped = new Map<string, PickRecord[]>()
    for (const p of picks) {
      if (!grouped.has(p.picker)) grouped.set(p.picker, [])
      grouped.get(p.picker)!.push(p)
    }
    const order = { best_bet: 0, regular: 1, mnf: 2, survivor: 3, underdog: 4 }
    for (const list of grouped.values()) {
      list.sort((a, b) => (order[a.pick_type] ?? 9) - (order[b.pick_type] ?? 9))
    }
    return [...grouped.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [picks])

  if (configError) return <p className="text-red-600">Failed to load config: {configError}</p>
  if (!config || season === null || week === null) return <p>Loading…</p>

  return (
    <div>
      <h1 className="text-2xl font-bold mb-3">🔍 View Picks</h1>

      <div className="flex gap-2 mb-4">
        <select value={season} onChange={(e) => setSeason(Number(e.target.value))} className="border rounded-md px-2 py-1.5 bg-white">
          {seasons.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={week} onChange={(e) => setWeek(Number(e.target.value))} className="border rounded-md px-2 py-1.5 bg-white">
          {weeks.map((w) => <option key={w} value={w}>Week {w}</option>)}
        </select>
      </div>

      {error && <p className="text-red-600">{error}</p>}
      {!error && byPicker.length === 0 && <p className="text-gray-600">No picks yet for week {week}.</p>}

      <div className="grid gap-4 sm:grid-cols-2">
        {byPicker.map(([picker, list]) => (
          <div key={picker} className="bg-white rounded-lg border border-gray-200 p-3">
            <h2 className="font-bold mb-2">👤 {picker}</h2>
            <ul className="space-y-1">
              {list.map((p, i) => (
                <li key={`${p.game_id}_${p.pick_type}_${i}`} className="flex items-center gap-2 text-sm">
                  <span className="w-5 text-center">{typeEmoji[p.pick_type] ?? ''}</span>
                  <img src={teamLogo(p.team_picked)} className="w-5 h-5" alt="" />
                  <span>
                    <b>{p.team_picked}</b>
                    {p.spread !== null && <span className="text-gray-500"> ({fmtSpread(p.spread)})</span>}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  )
}

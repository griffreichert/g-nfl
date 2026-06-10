import { useEffect, useState } from 'react'
import { api, teamLogo } from '../api'
import { fmtSpread, useConfig, useSeasonWeek } from '../hooks'
import type { GameLine } from '../types'

export default function ManageSpreads() {
  const { config, error: configError } = useConfig()
  const { season, setSeason, week, setWeek, weeks, seasons } = useSeasonWeek(config)
  const [games, setGames] = useState<GameLine[]>([])
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [status, setStatus] = useState<string | null>(null)

  const load = () => {
    if (season === null || week === null) return
    api.lines(season, week).then((g) => {
      setGames(g)
      setDrafts(Object.fromEntries(g.map((x) => [x.game_id, x.pool_spread?.toString() ?? ''])))
    })
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [season, week])

  const saveOne = async (g: GameLine) => {
    const raw = drafts[g.game_id]
    const spread = Number(raw)
    if (raw === '' || Number.isNaN(spread)) {
      setStatus(`Invalid spread for ${g.away_team} @ ${g.home_team}`)
      return
    }
    if (season === null || week === null) return
    try {
      await api.updatePoolSpread(season, week, g.game_id, spread)
      setStatus(`✅ Saved ${g.away_team} @ ${g.home_team}: ${fmtSpread(spread)}`)
      load()
    } catch (e) {
      setStatus(`❌ ${e}`)
    }
  }

  if (configError) return <p className="text-red-600">Failed to load config: {configError}</p>
  if (!config || season === null || week === null) return <p>Loading…</p>

  return (
    <div>
      <h1 className="text-2xl font-bold mb-3">⚙️ Manage Pool Spreads</h1>

      <div className="flex gap-2 mb-4">
        <select value={season} onChange={(e) => setSeason(Number(e.target.value))} className="border rounded-md px-2 py-1.5 bg-white">
          {seasons.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={week} onChange={(e) => setWeek(Number(e.target.value))} className="border rounded-md px-2 py-1.5 bg-white">
          {weeks.map((w) => <option key={w} value={w}>Week {w}</option>)}
        </select>
      </div>

      {status && <p className="text-sm bg-gray-100 rounded-md px-3 py-2 mb-3">{status}</p>}

      <div className="bg-white rounded-lg border border-gray-200 divide-y divide-gray-100">
        {games.map((g) => (
          <div key={g.game_id} className="flex items-center gap-2 px-3 py-2 text-sm">
            <img src={teamLogo(g.away_team)} className="w-6 h-6" alt="" />
            <span className="flex-1 whitespace-nowrap">
              {g.away_team} @ {g.home_team}
              <span className="text-gray-500 ml-2 hidden sm:inline">market {fmtSpread(g.market_spread)}</span>
            </span>
            <input
              type="number"
              step="0.5"
              value={drafts[g.game_id] ?? ''}
              placeholder="pool"
              onChange={(e) => setDrafts((d) => ({ ...d, [g.game_id]: e.target.value }))}
              className="border rounded-md px-2 py-1 w-20 text-right"
            />
            <button onClick={() => saveOne(g)} className="bg-green-600 hover:bg-green-700 text-white px-3 py-1 rounded-md">
              Save
            </button>
            <img src={teamLogo(g.home_team)} className="w-6 h-6" alt="" />
          </div>
        ))}
      </div>
    </div>
  )
}

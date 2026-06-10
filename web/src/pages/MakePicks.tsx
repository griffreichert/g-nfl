import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, teamLogo } from '../api'
import { fmtSpread, useConfig, useSeasonWeek } from '../hooks'
import type { GameLine, Pick } from '../types'

interface GamePick {
  team_picked: string
  pick_type: 'regular' | 'best_bet'
}

const MAX_REGULAR_PICKS = 6

export default function MakePicks() {
  const { config, error: configError } = useConfig()
  const { season, setSeason, week, setWeek, weeks, seasons } = useSeasonWeek(config)
  const [picker, setPicker] = useState<string>('')

  const [games, setGames] = useState<GameLine[]>([])
  const [picks, setPicks] = useState<Record<string, GamePick>>({})
  const [survivor, setSurvivor] = useState<string | null>(null)
  const [underdog, setUnderdog] = useState<string | null>(null)
  const [mnf, setMnf] = useState<string | null>(null)
  const [status, setStatus] = useState<{ kind: 'ok' | 'err'; msg: string } | null>(null)
  const [loading, setLoading] = useState(false)

  // Load games for the selected week
  useEffect(() => {
    if (season === null || week === null) return
    setLoading(true)
    api
      .lines(season, week)
      .then(setGames)
      .catch((e) => setStatus({ kind: 'err', msg: String(e) }))
      .finally(() => setLoading(false))
  }, [season, week])

  // Load existing picks when picker / week changes
  useEffect(() => {
    if (season === null || week === null || !picker) return
    api.picks(season, week, picker).then((existing) => {
      const regular: Record<string, GamePick> = {}
      let surv: string | null = null
      let dog: string | null = null
      let monday: string | null = null
      for (const p of existing) {
        if (p.pick_type === 'regular' || p.pick_type === 'best_bet') {
          regular[p.game_id] = { team_picked: p.team_picked, pick_type: p.pick_type }
        } else if (p.pick_type === 'survivor') surv = p.team_picked
        else if (p.pick_type === 'underdog') dog = p.team_picked
        else if (p.pick_type === 'mnf') monday = p.team_picked
      }
      setPicks(regular)
      setSurvivor(surv)
      setUnderdog(dog)
      setMnf(monday)
      setStatus(null)
    })
  }, [season, week, picker])

  const effectiveSpread = (g: GameLine) => g.pool_spread ?? g.market_spread

  // Click cycle: unselected -> regular -> best_bet (only one allowed) -> unselected
  const clickTeam = useCallback(
    (game: GameLine, team: string) => {
      if (game.is_mnf) {
        setMnf((cur) => (cur === team ? null : team))
        return
      }
      setPicks((cur) => {
        const next = { ...cur }
        const existing = cur[game.game_id]
        if (!existing || existing.team_picked !== team) {
          if (!existing && Object.keys(cur).length >= MAX_REGULAR_PICKS) return cur
          next[game.game_id] = { team_picked: team, pick_type: 'regular' }
        } else if (existing.pick_type === 'regular') {
          const hasBestBet = Object.values(cur).some((p) => p.pick_type === 'best_bet')
          next[game.game_id] = { team_picked: team, pick_type: hasBestBet ? 'regular' : 'best_bet' }
        } else {
          delete next[game.game_id]
        }
        return next
      })
    },
    []
  )

  // Favorites for survivor (excluding used teams), underdogs for the dog pool
  const { favorites, underdogs } = useMemo(() => {
    const used = new Set(config?.survivor_used_teams ?? [])
    const favs: { team: string; opp: string; spread: number; id: string }[] = []
    const dogs: { team: string; opp: string; spread: number; id: string }[] = []
    for (const g of games) {
      const s = effectiveSpread(g)
      if (s === null || s === undefined) continue
      const awayFav = s < 0
      const fav = awayFav ? g.away_team : g.home_team
      const dog = awayFav ? g.home_team : g.away_team
      const favSpread = awayFav ? s : -s
      if (!used.has(fav)) favs.push({ team: fav, opp: dog, spread: favSpread, id: g.game_id })
      dogs.push({ team: dog, opp: fav, spread: -favSpread, id: g.game_id })
    }
    favs.sort((a, b) => a.spread - b.spread)
    dogs.sort((a, b) => b.spread - a.spread)
    return { favorites: favs, underdogs: dogs }
  }, [games, config])

  // Summary text matching the Streamlit app's copy-paste format
  const summary = useMemo(() => {
    if (!picker || week === null) return ''
    const lines: string[] = []
    const describe = (team: string, g: GameLine) => {
      const s = g.market_spread
      const home = team === g.home_team
      const spread = s === null ? '' : ` (${fmtSpread(home ? -s : s)})`
      return `${team}${spread} ${home ? 'vs' : 'at'} ${home ? g.away_team : g.home_team}`
    }
    const gameOf = (team: string, id?: string) =>
      games.find((g) => (id ? g.game_id === id : g.away_team === team || g.home_team === team))
    const entries = Object.entries(picks)
    for (const [id, p] of entries.filter(([, p]) => p.pick_type === 'best_bet')) {
      const g = gameOf(p.team_picked, id)
      if (g) lines.push(`⭐️ ${describe(p.team_picked, g)}`)
    }
    for (const [id, p] of entries.filter(([, p]) => p.pick_type === 'regular')) {
      const g = gameOf(p.team_picked, id)
      if (g) lines.push(describe(p.team_picked, g))
    }
    for (const [emoji, team] of [['🌙', mnf], ['💀', survivor], ['🐶', underdog]] as const) {
      if (!team) continue
      const g = gameOf(team)
      if (g) lines.push(`${emoji} ${describe(team, g)}`)
    }
    return lines.length ? `${picker}'s Week ${week} Picks\n\n${lines.join('\n')}` : ''
  }, [picks, survivor, underdog, mnf, games, picker, week])

  const save = async () => {
    if (!picker || season === null || week === null) return
    const payload: Pick[] = Object.entries(picks).map(([game_id, p]) => ({
      game_id,
      team_picked: p.team_picked,
      pick_type: p.pick_type,
      spread: games.find((g) => g.game_id === game_id)?.market_spread ?? null,
    }))
    const special = (team: string | null, type: Pick['pick_type']) => {
      if (!team) return
      const g = games.find((x) => x.away_team === team || x.home_team === team)
      if (g) payload.push({ game_id: g.game_id, team_picked: team, pick_type: type, spread: g.market_spread })
    }
    special(survivor, 'survivor')
    special(underdog, 'underdog')
    special(mnf, 'mnf')
    if (!payload.length) {
      setStatus({ kind: 'err', msg: 'No picks to save' })
      return
    }
    try {
      const res = await api.savePicks(season, week, picker, payload)
      await navigator.clipboard.writeText(summary).catch(() => {})
      setStatus({ kind: 'ok', msg: `Saved ${res.saved} picks 📋 copied to clipboard` })
    } catch (e) {
      setStatus({ kind: 'err', msg: `Failed to save: ${e}` })
    }
  }

  const clearAll = () => {
    setPicks({})
    setSurvivor(null)
    setUnderdog(null)
    setMnf(null)
    setStatus(null)
  }

  if (configError) return <p className="text-red-600">Failed to load config: {configError}</p>
  if (!config || season === null || week === null) return <p>Loading…</p>

  const regularCount = Object.keys(picks).length
  const maxReached = regularCount >= MAX_REGULAR_PICKS

  const teamButton = (g: GameLine, team: string) => {
    const isMnfGame = g.is_mnf
    const pick = picks[g.game_id]
    const selected = isMnfGame ? mnf === team : pick?.team_picked === team
    const otherSelected = isMnfGame ? mnf !== null && mnf !== team : !!pick && pick.team_picked !== team
    const disabled = !picker || otherSelected || (!isMnfGame && !selected && maxReached)
    const isBest = !isMnfGame && selected && pick?.pick_type === 'best_bet'
    const label = `${isMnfGame ? '🌙 ' : isBest ? '⭐ ' : ''}${team}`
    const cls = selected
      ? isMnfGame
        ? 'bg-purple-500 text-white'
        : isBest
          ? 'bg-violet-400 text-white font-bold'
          : 'bg-green-600 text-white'
      : disabled
        ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
        : 'bg-white border border-gray-300 hover:bg-gray-100'
    return (
      <button
        onClick={() => clickTeam(g, team)}
        disabled={disabled}
        className={`w-full px-2 py-1.5 rounded-md text-xs sm:text-sm whitespace-nowrap ${cls}`}
      >
        {label}
      </button>
    )
  }

  const poolRow = (
    item: { team: string; opp: string; spread: number; id: string },
    selected: string | null,
    setSelected: (t: string | null) => void,
    emoji: string
  ) => (
    <div key={`${item.id}_${item.team}`} className="flex items-center gap-2 py-1">
      <img src={teamLogo(item.team)} className="w-7 h-7" alt="" />
      <span className="flex-1 text-sm">
        <b>{item.team}</b> ({fmtSpread(item.spread)}) vs {item.opp}
      </span>
      <button
        onClick={() => setSelected(selected === item.team ? null : item.team)}
        disabled={!picker}
        className={`px-3 py-1 rounded-md text-sm ${
          selected === item.team
            ? 'bg-green-600 text-white'
            : 'bg-white border border-gray-300 hover:bg-gray-100'
        }`}
      >
        {selected === item.team ? `${emoji} ${item.team}` : item.team}
      </button>
    </div>
  )

  return (
    <div>
      <h1 className="text-2xl font-bold mb-3">🎯 Make Picks</h1>

      <div className="flex flex-wrap gap-2 mb-4">
        <select value={season} onChange={(e) => setSeason(Number(e.target.value))} className="border rounded-md px-2 py-1.5 bg-white">
          {seasons.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={week} onChange={(e) => setWeek(Number(e.target.value))} className="border rounded-md px-2 py-1.5 bg-white">
          {weeks.map((w) => <option key={w} value={w}>Week {w}</option>)}
        </select>
        <select value={picker} onChange={(e) => setPicker(e.target.value)} className="border rounded-md px-2 py-1.5 bg-white flex-1 min-w-32">
          <option value="">👤 Choose your name…</option>
          {config.pickers.map((p) => <option key={p} value={p}>👤 {p}</option>)}
        </select>
      </div>

      {status && (
        <p className={`mb-3 text-sm rounded-md px-3 py-2 ${status.kind === 'ok' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
          {status.msg}
        </p>
      )}

      {!picker && <p className="text-amber-700 bg-amber-100 rounded-md px-3 py-2 mb-3">👆 Select your name to start making picks</p>}

      {loading ? (
        <p>Loading games…</p>
      ) : (
        <>
          <p className="text-sm text-gray-600 mb-2">
            <b>{regularCount}/{MAX_REGULAR_PICKS}</b> regular • {survivor ? '✅' : '⬜'} survivor • {underdog ? '✅' : '⬜'} underdog • {mnf ? '✅' : '⬜'} MNF
          </p>

          <div className="bg-white rounded-lg border border-gray-200 divide-y divide-gray-100">
            {games.map((g) => (
              <div key={g.game_id} className="grid grid-cols-[1.75rem_1fr_auto_1fr_1.75rem] items-center gap-1.5 sm:gap-2 px-2 py-2">
                <img src={teamLogo(g.away_team)} className="w-7 h-7" alt="" />
                {teamButton(g, g.away_team)}
                <span className="text-xs sm:text-sm text-center whitespace-nowrap px-1">
                  <b>{fmtSpread(g.pool_spread)}</b>
                  <span className="hidden sm:inline"> / {fmtSpread(g.market_spread)}</span>
                  <span className="hidden md:inline"> / {g.market_total ?? 'N/A'}</span>
                </span>
                {teamButton(g, g.home_team)}
                <img src={teamLogo(g.home_team)} className="w-7 h-7" alt="" />
              </div>
            ))}
          </div>

          <h2 className="text-lg font-bold mt-6 mb-1">💀 Survivor Pool</h2>
          <p className="text-sm text-gray-600 mb-2">Pick ONE favorite for the week</p>
          {config.survivor_used_teams.length > 0 && (
            <p className="text-xs text-gray-500 mb-2">🚫 Already used: {[...config.survivor_used_teams].sort().join(', ')}</p>
          )}
          <div className="bg-white rounded-lg border border-gray-200 px-3 py-2">
            {favorites.filter((f) => !survivor || f.team === survivor).map((f) => poolRow(f, survivor, setSurvivor, '💀'))}
          </div>

          <h2 className="text-lg font-bold mt-6 mb-1">🐶 Underdog Pool</h2>
          <p className="text-sm text-gray-600 mb-2">Pick ONE underdog for the week</p>
          <div className="bg-white rounded-lg border border-gray-200 px-3 py-2">
            {underdogs.filter((d) => !underdog || d.team === underdog).map((d) => poolRow(d, underdog, setUnderdog, '🐶'))}
          </div>

          {summary && (
            <>
              <h2 className="text-lg font-bold mt-6 mb-2">📋 Pick Summary</h2>
              <pre className="bg-gray-900 text-gray-100 rounded-lg p-3 text-sm whitespace-pre-wrap">{summary}</pre>
              <div className="flex gap-3 mt-3">
                <button onClick={save} className="bg-green-600 hover:bg-green-700 text-white font-medium px-4 py-2 rounded-md">
                  💾 Save Picks
                </button>
                <button onClick={clearAll} className="bg-white border border-gray-300 hover:bg-gray-100 px-4 py-2 rounded-md">
                  🗑️ Clear All
                </button>
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}

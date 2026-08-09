import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight, Dog, Moon, Skull, Star, Trash2 } from 'lucide-react'
import { api, teamLogo } from '../api'
import { WORST_CELL, isWorstCell } from '@/lib/consensus'
import { fmtSpread, useConfig, useSeasonWeek } from '../hooks'
import type { GameLine, Pick } from '../types'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface GamePick {
  team_picked: string
  pick_type: 'regular' | 'best_bet'
}

const MAX_REGULAR_PICKS = 6

// A note is keyed the way the API keys a pick: special slots are prefixed so a
// survivor and a regular pick on the same game keep separate notes.
const noteKey = (gameId: string, type: Pick['pick_type']) =>
  type === 'regular' || type === 'best_bet' ? gameId : `${type}_${gameId}`

const NOTE_INPUT_CLASS =
  'h-8 w-full rounded-md border border-input bg-transparent px-2 text-sm shadow-xs outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 dark:bg-input/30'

export default function MakePicks() {
  const { config, error: configError } = useConfig()
  const { season, setSeason, week, setWeek, weeks, seasons } = useSeasonWeek(config)
  const [picker, setPicker] = useState<string>('')

  const [games, setGames] = useState<GameLine[]>([])
  const [picks, setPicks] = useState<Record<string, GamePick>>({})
  const [survivor, setSurvivor] = useState<string | null>(null)
  const [underdog, setUnderdog] = useState<string | null>(null)
  const [mnf, setMnf] = useState<string | null>(null)
  const [notes, setNotes] = useState<Record<string, string>>({})
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
      const savedNotes: Record<string, string> = {}
      let surv: string | null = null
      let dog: string | null = null
      let monday: string | null = null
      for (const p of existing) {
        if (p.note) savedNotes[noteKey(p.game_id, p.pick_type)] = p.note
        if (p.pick_type === 'regular' || p.pick_type === 'best_bet') {
          regular[p.game_id] = { team_picked: p.team_picked, pick_type: p.pick_type }
        } else if (p.pick_type === 'survivor') surv = p.team_picked
        else if (p.pick_type === 'underdog') dog = p.team_picked
        else if (p.pick_type === 'mnf') monday = p.team_picked
      }
      setPicks(regular)
      setNotes(savedNotes)
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
          // Promote, demoting whoever held the slot -- the same swap the board
          // does in cycleSlot(). Previously this wrote 'regular' back over
          // itself whenever a best bet existed, so the side could not be
          // promoted OR dropped: the tap did nothing at all.
          const incumbent = Object.entries(cur).find(([, p]) => p.pick_type === 'best_bet')
          if (incumbent) next[incumbent[0]] = { ...incumbent[1], pick_type: 'regular' }
          next[game.game_id] = { team_picked: team, pick_type: 'best_bet' }
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

  // Summary text matching the Streamlit app's copy-paste format. The emoji here
  // are the message body pasted into the pool chat, not app chrome — leave them.
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
      note: notes[noteKey(game_id, p.pick_type)]?.trim() || null,
    }))
    const special = (team: string | null, type: Pick['pick_type']) => {
      if (!team) return
      const g = games.find((x) => x.away_team === team || x.home_team === team)
      if (g)
        payload.push({
          game_id: g.game_id,
          team_picked: team,
          pick_type: type,
          spread: g.market_spread,
          note: notes[noteKey(g.game_id, type)]?.trim() || null,
        })
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
      setStatus({ kind: 'ok', msg: `Saved ${res.saved} picks — summary copied to clipboard` })
    } catch (e) {
      setStatus({ kind: 'err', msg: `Failed to save: ${e}` })
    }
  }

  const clearAll = () => {
    setPicks({})
    setNotes({})
    setSurvivor(null)
    setUnderdog(null)
    setMnf(null)
    setStatus(null)
  }

  if (configError) return <p className="text-destructive">Failed to load config: {configError}</p>
  if (!config || season === null || week === null) return <p>Loading…</p>

  const mnfPickedHere = (g: GameLine) =>
    mnf !== null && (mnf === g.away_team || mnf === g.home_team)

  /**
   * The board has a rating to lean on; this page has nothing, and this page is
   * where most picks get made. One flag, on the one cell that cost us real
   * money in 2025, shown only once the pick is on the board so it reads as a
   * second thought rather than a lecture.
   */
  const worstCellWarning = (g: GameLine) => {
    const picked = g.is_mnf ? mnf : picks[g.game_id]?.team_picked
    if (picked !== g.home_team) return null
    if (!isWorstCell(effectiveSpread(g), true)) return null
    return (
      <p className="col-span-6 pt-1 text-xs text-muted-foreground">
        <span className="font-semibold text-foreground">Home {WORST_CELL.band}.</span>{' '}
        Our worst cell — {WORST_CELL.pct}% over {WORST_CELL.games} games, against a
        league that covered {WORST_CELL.league}% here.
      </p>
    )
  }

  const regularCount = Object.keys(picks).length
  const maxReached = regularCount >= MAX_REGULAR_PICKS

  const teamButton = (g: GameLine, team: string) => {
    const isMnfGame = g.is_mnf
    const pick = picks[g.game_id]
    const selected = isMnfGame ? mnf === team : pick?.team_picked === team
    const otherSelected = isMnfGame ? mnf !== null && mnf !== team : !!pick && pick.team_picked !== team
    const disabled = !picker || otherSelected || (!isMnfGame && !selected && maxReached)
    const isBest = !isMnfGame && selected && pick?.pick_type === 'best_bet'
    // Amber means picked, violet means best bet — the same two accents the rest
    // of the app uses. Never green/red: those are reserved for graded results.
    const tone = !selected
      ? ''
      : isBest
        ? 'bg-bb text-primary-foreground hover:bg-bb/90'
        : 'bg-pick text-primary-foreground hover:bg-pick/90'
    return (
      <Button
        variant={selected ? 'default' : 'outline'}
        size="sm"
        onClick={() => clickTeam(g, team)}
        disabled={disabled}
        className={`w-full font-medium ${tone}`}
      >
        {isMnfGame && selected && <Moon className="size-3.5" />}
        {isBest && <Star className="size-3.5 fill-current" />}
        {team}
      </Button>
    )
  }

  // Notes only appear once a pick exists — an empty box on all 16 games is
  // noise, and there is nothing to explain until a side is chosen.
  const noteInput = (key: string, label: string) => (
    <input
      type="text"
      value={notes[key] ?? ''}
      placeholder="Why? (optional)"
      onChange={(e) => setNotes((n) => ({ ...n, [key]: e.target.value }))}
      aria-label={`Note for ${label}`}
      className={NOTE_INPUT_CLASS}
    />
  )

  const poolRow = (
    item: { team: string; opp: string; spread: number; id: string },
    selected: string | null,
    setSelected: (t: string | null) => void,
    Icon: typeof Skull,
    slotType: Pick['pick_type']
  ) => {
    const on = selected === item.team
    return (
      <div key={`${item.id}_${item.team}`} className="py-1">
      <div className="flex items-center gap-2">
        <img src={teamLogo(item.team)} className="size-6 shrink-0" alt="" />
        <span className="flex-1 truncate text-sm">
          <span className="font-semibold">{item.team}</span>{' '}
          <span className="tabular text-muted-foreground">{fmtSpread(item.spread)}</span>{' '}
          <span className="text-muted-foreground">vs {item.opp}</span>
        </span>
        <Button
          variant={on ? 'default' : 'outline'}
          size="sm"
          onClick={() => setSelected(on ? null : item.team)}
          disabled={!picker}
          className={on ? 'w-24 bg-pick text-primary-foreground hover:bg-pick/90' : 'w-24'}
        >
          {on && <Icon className="size-3.5" />}
          {on ? item.team : 'Pick'}
        </Button>
      </div>
        {on && <div className="mt-1 pl-8">{noteInput(noteKey(item.id, slotType), item.team)}</div>}
      </div>
    )
  }

  const slot = (label: string, done: boolean) => (
    <span className={done ? 'text-pick' : 'text-muted-foreground'}>
      {done ? '●' : '○'} {label}
    </span>
  )

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-xl font-bold sm:text-2xl">Picks</h1>
        <Select value={String(season)} onValueChange={(v) => setSeason(Number(v))}>
          <SelectTrigger size="sm" className="w-24">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {seasons.map((s) => (
              <SelectItem key={s} value={String(s)}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={String(week)} onValueChange={(v) => setWeek(Number(v))}>
          <SelectTrigger size="sm" className="w-28">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {weeks.map((w) => (
              <SelectItem key={w} value={String(w)}>
                Week {w}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={picker || undefined} onValueChange={setPicker}>
          <SelectTrigger size="sm" className="w-full sm:w-40">
            <SelectValue placeholder="Your name" />
          </SelectTrigger>
          <SelectContent>
            {config.pickers.map((p) => (
              <SelectItem key={p} value={p}>
                {p}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {status && (
        <p
          className={`rounded-md px-3 py-2 text-sm ${
            status.kind === 'ok' ? 'bg-win/15 text-win' : 'bg-loss/15 text-loss'
          }`}
        >
          {status.msg}
        </p>
      )}

      {!picker && (
        <p className="rounded-md border border-border bg-card px-3 py-2 text-sm text-muted-foreground">
          Pick your name above to start.
        </p>
      )}

      {loading ? (
        <p className="text-muted-foreground">Loading games…</p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <span className="tabular font-semibold">
              {regularCount}/{MAX_REGULAR_PICKS}
            </span>
            <span className="text-muted-foreground">regular</span>
            {slot('survivor', !!survivor)}
            {slot('underdog', !!underdog)}
            {slot('MNF', !!mnf)}
          </div>

          <div className="divide-y divide-border rounded-lg border border-border bg-card">
            {games.map((g) => (
              <div
                key={g.game_id}
                className="grid grid-cols-[1.5rem_1fr_auto_1fr_1.5rem_1rem] items-center gap-1.5 px-2 py-2 sm:gap-2 sm:px-3"
              >
                <img src={teamLogo(g.away_team)} className="size-6" alt="" />
                {teamButton(g, g.away_team)}
                <span className="tabular whitespace-nowrap px-1 text-center text-xs sm:text-sm">
                  <span className="font-semibold">{fmtSpread(g.pool_spread)}</span>
                  <span className="hidden text-muted-foreground sm:inline">
                    {' '}
                    / {fmtSpread(g.market_spread)}
                  </span>
                  <span className="hidden text-muted-foreground md:inline">
                    {' '}
                    / {g.market_total ?? '—'}
                  </span>
                </span>
                {teamButton(g, g.home_team)}
                <img src={teamLogo(g.home_team)} className="size-6" alt="" />
                {/* Its own control: the team buttons are the pick, so the row can't be a link. */}
                <Link
                  to={`/game/${g.game_id}`}
                  aria-label={`Detail for ${g.away_team} at ${g.home_team}`}
                  title="Game detail"
                  className="text-muted-foreground hover:text-foreground"
                >
                  <ChevronRight className="size-4" />
                </Link>
                {worstCellWarning(g)}
                {(g.is_mnf ? mnfPickedHere(g) : !!picks[g.game_id]) && (
                  <div className="col-span-6 pt-1">
                    {noteInput(
                      noteKey(g.game_id, g.is_mnf ? 'mnf' : picks[g.game_id].pick_type),
                      `${g.away_team} at ${g.home_team}`
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="rounded-lg border border-border bg-card p-3">
            <h2 className="flex items-center gap-1.5 text-sm font-bold">
              <Skull className="size-4" /> Survivor
            </h2>
            <p className="mb-2 text-xs text-muted-foreground">
              One favourite for the week.
              {config.survivor_used_teams.length > 0 &&
                ` Already used: ${[...config.survivor_used_teams].sort().join(', ')}.`}
            </p>
            {favorites
              .filter((f) => !survivor || f.team === survivor)
              .map((f) => poolRow(f, survivor, setSurvivor, Skull, 'survivor'))}
          </div>

          <div className="rounded-lg border border-border bg-card p-3">
            <h2 className="flex items-center gap-1.5 text-sm font-bold">
              <Dog className="size-4" /> Underdog
            </h2>
            <p className="mb-2 text-xs text-muted-foreground">One underdog for the week.</p>
            {underdogs
              .filter((d) => !underdog || d.team === underdog)
              .map((d) => poolRow(d, underdog, setUnderdog, Dog, 'underdog'))}
          </div>

          {summary && (
            <div className="rounded-lg border border-border bg-card p-3">
              <h2 className="mb-2 text-sm font-bold">Summary</h2>
              <pre className="overflow-x-auto rounded-md bg-muted p-3 text-sm whitespace-pre-wrap">
                {summary}
              </pre>
              <div className="mt-3 flex gap-2">
                <Button size="sm" onClick={save}>
                  Save picks
                </Button>
                <Button size="sm" variant="outline" onClick={clearAll}>
                  <Trash2 className="size-3.5" /> Clear
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

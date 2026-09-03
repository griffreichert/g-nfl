import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight, Clipboard, Dog, Moon, Skull, Star, Trash2 } from 'lucide-react'
import { api, teamLogo } from '../api'
import { fmtSpread, useAuth, useConfig, useGuardrails, useSeasonWeek } from '../hooks'
import type { GameLine, Pick } from '../types'
import {
  MAX_ATS_NON_MNF,
  MAX_REGULAR,
  isComplete,
  shortfall,
  type SlotTally,
} from '@/lib/consensus'
import PageHeader from '@/components/PageHeader'
import ActionBar, { Slot } from '@/components/ActionBar'
import { ErrorNote, Loading } from '@/components/PageState'
import { Button } from '@/components/ui/button'

interface GamePick {
  team_picked: string
  pick_type: 'regular' | 'best_bet'
}

// A note is keyed the way the API keys a pick: special slots are prefixed so a
// survivor and a regular pick on the same game keep separate notes.
const noteKey = (gameId: string, type: Pick['pick_type']) =>
  type === 'regular' || type === 'best_bet' ? gameId : `${type}_${gameId}`

/**
 * A one-sentence explanation, out of the way until asked for.
 *
 * Native `title` for now, so it costs nothing. It does not open on a phone,
 * which is why the copy pass replaces this with a Radix popover that answers
 * to a tap as well as a hover.
 */
function Info({ text }: { text: string }) {
  return (
    <span
      title={text}
      aria-label={text}
      className="inline-flex size-3.5 cursor-help items-center justify-center rounded-full border border-current text-[9px] font-bold normal-case"
    >
      i
    </span>
  )
}

const NOTE_INPUT_CLASS =
  'h-8 w-full rounded-md border border-input bg-transparent px-2 text-sm shadow-xs outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 dark:bg-input/30'

/** Everything a half-finished week consists of. */
type Draft = {
  picks: Record<string, GamePick>
  survivor: string | null
  underdog: string | null
  mnf: string | null
  notes: Record<string, string>
}

const EMPTY: Draft = { picks: {}, survivor: null, underdog: null, mnf: null, notes: {} }

/**
 * A week in progress, kept in the browser until it is saved (#124).
 *
 * Picks, notes and the two pool slots lived in React state and nowhere else,
 * so changing the week selector or following a game link discarded the lot
 * with no warning. Keyed by picker as well as week: a shared laptop must not
 * hand one person's half-finished week to the next.
 */
const draftKeyFor = (picker: string, season: number, week: number) =>
  `nohomers.draft.${picker}.${season}.${week}`

const readDraft = (key: string): Draft | null => {
  try {
    const raw = localStorage.getItem(key)
    return raw ? { ...EMPTY, ...JSON.parse(raw) } : null
  } catch {
    return null
  }
}

export default function MakePicks() {
  const { picker: signedIn } = useAuth()
  const picker = signedIn ?? ''
  const { config, error: configError } = useConfig(signedIn ?? undefined)
  const { season, setSeason, week, setWeek, weeks, seasons } = useSeasonWeek(config)
  const { flagsFor, ruleById } = useGuardrails(season, week)

  // Games are stamped with the week they were fetched for, so "still loading"
  // is derived from a stale stamp rather than flagged from inside the effect.
  const [fetched, setGames] = useState<{ key: string; rows: GameLine[] }>({
    key: '',
    rows: [],
  })
  const weekKey = `${season}-${week}`
  const games = fetched.key === weekKey ? fetched.rows : []
  const [picks, setPicks] = useState<Record<string, GamePick>>({})
  const [survivor, setSurvivor] = useState<string | null>(null)
  const [underdog, setUnderdog] = useState<string | null>(null)
  const [mnf, setMnf] = useState<string | null>(null)
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [status, setStatus] = useState<{ kind: 'ok' | 'err'; msg: string } | null>(null)
  // When the server last took this week from us. Null means never, and also
  // means "saved before #131 shipped", which reads as time unknown (#131).
  const [submitted, setSubmitted] = useState<{ key: string; at: string | null } | null>(null)
  const loading = season !== null && week !== null && fetched.key !== weekKey

  // Load games for the selected week
  useEffect(() => {
    if (season === null || week === null) return
    api
      .lines(season, week)
      .then((rows) => setGames({ key: `${season}-${week}`, rows }))
      .catch((e) => setStatus({ kind: 'err', msg: String(e) }))
  }, [season, week])

  // What the server holds for this week, as a string, so "you have unsaved
  // changes" is a comparison rather than a flag somebody has to remember to set.
  const [baseline, setBaseline] = useState<{ key: string; json: string } | null>(null)
  const draftKey =
    picker && season !== null && week !== null ? draftKeyFor(picker, season, week) : null
  const current: Draft = { picks, survivor, underdog, mnf, notes }
  const currentJson = JSON.stringify(current)
  const dirty = baseline?.key === weekKey && currentJson !== baseline.json

  // Load existing picks when picker / week changes, and prefer an unsaved
  // draft over them when one is sitting in this browser.
  useEffect(() => {
    if (season === null || week === null || !picker) return
    let live = true
    api.picks(season, week, picker).then((existing) => {
      if (!live) return
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
      const saved: Draft = {
        picks: regular,
        survivor: surv,
        underdog: dog,
        mnf: monday,
        notes: savedNotes,
      }
      setBaseline({ key: `${season}-${week}`, json: JSON.stringify(saved) })
      setSubmitted(
        existing.length
          ? {
              key: `${season}-${week}`,
              at: existing.map((p) => p.submitted_at).find(Boolean) ?? null,
            }
          : null,
      )

      const restored = readDraft(draftKeyFor(picker, season, week))
      const show = restored ?? saved
      setPicks(show.picks)
      setNotes(show.notes)
      setSurvivor(show.survivor)
      setUnderdog(show.underdog)
      setMnf(show.mnf)
      setStatus(
        restored
          ? { kind: 'ok', msg: 'Picked up where you left off. Nothing is saved yet.' }
          : null
      )
    })
    return () => {
      live = false
    }
  }, [season, week, picker])

  // Write the draft only once it differs from what the server holds, so a
  // clean week leaves nothing behind to restore.
  useEffect(() => {
    if (!draftKey || baseline?.key !== weekKey) return
    if (dirty) localStorage.setItem(draftKey, currentJson)
    else localStorage.removeItem(draftKey)
  }, [draftKey, weekKey, baseline, dirty, currentJson])

  const effectiveSpread = (g: GameLine) => g.pool_spread ?? g.market_spread

  /**
   * Where the pool prices a game differently from the market, and which side
   * that helps.
   *
   * Both lines are stored home-perspective, positive meaning the home team is
   * favoured. A pool number above the market's has the home side laying more
   * than the market says it should, so the away side is the one getting the
   * better of it, and vice versa.
   *
   * This is the largest single leak in six seasons of our own picks: the side
   * the pool prices worse than the market has gone 45.2% over 1098 picks
   * (z=-3.20). It is the one thing on this row worth looking for, so it is the
   * one thing on this row that carries colour.
   */
  const edge = (g: GameLine) => {
    if (g.pool_spread === null || g.market_spread === null) return null
    const diff = g.pool_spread - g.market_spread
    if (diff === 0) return null
    return { team: diff > 0 ? g.away_team : g.home_team, points: Math.abs(diff) }
  }

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
          if (!existing && Object.keys(cur).length >= MAX_ATS_NON_MNF) return cur
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

  // What the picker saw, from the side they took. Grading joins the line
  // tables and ignores this column, so it records rather than decides; it used
  // to store the market number even though the pool grades against its own.
  const spreadSeen = (game: GameLine | undefined, team: string) => {
    if (!game) return null
    const home = effectiveSpread(game)
    if (home === null) return null
    return team === game.home_team ? home : -home
  }

  const save = async (submitting: boolean) => {
    if (!picker || season === null || week === null) return
    if (submitting && !complete) {
      setStatus({ kind: 'err', msg: `Still short: ${missing.join(', ')}` })
      return
    }
    const payload: Pick[] = Object.entries(picks).map(([game_id, p]) => ({
      game_id,
      team_picked: p.team_picked,
      pick_type: p.pick_type,
      spread: spreadSeen(
        games.find((g) => g.game_id === game_id),
        p.team_picked
      ),
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
          spread: spreadSeen(g, team),
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
      const res = await api.savePicks(season, week, payload)
      // Saved is the new baseline, so the page stops calling itself unsaved
      // and the draft it was holding is no longer worth keeping.
      setBaseline({ key: weekKey, json: currentJson })
      if (draftKey) localStorage.removeItem(draftKey)
      setSubmitted({ key: weekKey, at: new Date().toISOString() })
      setStatus({
        kind: 'ok',
        msg: submitting
          ? `Submitted ${res.saved} picks for week ${week}`
          : `Saved ${res.saved} picks. Still short: ${missing.join(', ')}`,
      })
    } catch (e) {
      setStatus({ kind: 'err', msg: `Failed to save: ${e}` })
    }
  }

  // Its own button. Saving used to take the clipboard as a side effect and
  // tell you afterwards, and it swallowed the failure, so a browser that
  // blocked the write still got a message saying the summary had been copied.
  const copySummary = async () => {
    try {
      await navigator.clipboard.writeText(summary)
      setStatus({ kind: 'ok', msg: 'Summary copied — paste it in the chat' })
    } catch {
      setStatus({ kind: 'err', msg: 'Could not reach the clipboard. Select the text above.' })
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

  if (configError) return <ErrorNote>Failed to load config: {configError}</ErrorNote>
  if (!config) return <Loading />
  if (season === null || week === null) return <Loading />

  const mnfPickedHere = (g: GameLine) =>
    mnf !== null && (mnf === g.away_team || mnf === g.home_team)

  /**
   * The board has a rating to lean on; this page has nothing, and this page is
   * where most picks get made. Guardrails are served fitted from the record
   * (GET /api/guardrails), so this page holds no rates of its own. Shown only
   * once the pick is on the board, so it reads as a second thought rather than
   * a lecture.
   */
  const guardrailWarning = (g: GameLine) => {
    const picked = g.is_mnf ? mnf : picks[g.game_id]?.team_picked
    if (!picked) return null
    const tripped = flagsFor(g.game_id, picked)
    if (!tripped.length) return null
    return (
      <div className="col-span-6 space-y-1 pt-1">
        {tripped.map((id) => {
          const rule = ruleById(id)
          if (!rule) return null
          return (
            <p key={id} className="text-xs text-muted-foreground">
              <span className="font-semibold text-foreground">
                {rule.advisory ? 'Worth knowing' : 'Guardrail'}: {rule.label}.
              </span>{' '}
              {(rule.pct * 100).toFixed(1)}% over {rule.games.toFixed(0)} games,
              against {(rule.base_pct * 100).toFixed(1)}% for everything else we
              pick.
            </p>
          )
        })}
      </div>
    )
  }

  const tally: SlotTally = {
    bb: Object.values(picks).filter((p) => p.pick_type === 'best_bet').length,
    regular: Object.values(picks).filter((p) => p.pick_type === 'regular').length,
    mnf: mnf ? 1 : 0,
    underdog: underdog ? 1 : 0,
    survivor: survivor ? 1 : 0,
  }
  const missing = shortfall(tally)
  const complete = isComplete(tally)
  const maxReached = Object.keys(picks).length >= MAX_ATS_NON_MNF

  /** The line from one side's point of view, which is the side you tap. */
  const sideSpread = (g: GameLine, team: string) => {
    const home = effectiveSpread(g)
    if (home === null || home === undefined) return null
    return team === g.home_team ? home : -home
  }

  const teamButton = (g: GameLine, team: string, side: 'away' | 'home') => {
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
        // Capped and pushed toward the middle, so the two buttons stay the same
        // width on every row and meet the line column instead of drifting with
        // the width of the browser.
        // The spread sits inside the button, on the side it belongs to. It
        // used to be one of three numbers in a slash-separated cell in the
        // middle of the row, which meant reading `TBD / +3.5 / 44.5` and
        // working out which of the three applied to the team you were about to
        // tap. You pick a side, so the number rides that side.
        className={`w-full max-w-64 justify-between gap-3 font-medium ${
          side === 'away' ? 'justify-self-end' : 'justify-self-start'
        } ${tone}`}
      >
        <span className="flex items-center gap-1.5">
          {isMnfGame && selected && <Moon className="size-3.5" />}
          {isBest && <Star className="size-3.5 fill-current" />}
          {team}
        </span>
        <span className={`tabular text-sm ${selected ? '' : 'text-muted-foreground'}`}>
          {fmtSpread(sideSpread(g, team))}
        </span>
      </Button>
    )
  }

  /**
   * The gap, shown on the side that gains from it. Position carries the
   * direction, so the row needs no arrow and no second sentence.
   */
  const edgeChip = (g: GameLine, team: string) => {
    const e = edge(g)
    if (!e || e.team !== team) return null
    return (
      <span
        title={`Pool ${fmtSpread(g.pool_spread)} against market ${fmtSpread(g.market_spread)}`}
        className="tabular inline-flex h-5 shrink-0 items-center rounded bg-win/15 px-1 text-[11px] font-bold text-win"
      >
        +{e.points}
      </span>
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

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Picks"
        season={season}
        seasons={seasons}
        onSeason={setSeason}
        week={week}
        weeks={weeks}
        onWeek={setWeek}
      />

      {status && (
        <p
          className={`rounded-md px-3 py-2 text-sm ${
            status.kind === 'ok' ? 'bg-win/15 text-win' : 'bg-loss/15 text-loss'
          }`}
        >
          {status.msg}
        </p>
      )}

      {loading ? (
        <Loading />
      ) : (
        <>
          <ActionBar
            slots={
              <>
                <Slot label="best bet" have={tally.bb} need={1} />
                <Slot label="regular" have={tally.regular} need={MAX_REGULAR} />
                <Slot label="MNF" have={tally.mnf} need={1} />
                <Slot label="dog" have={tally.underdog} need={1} />
                <Slot label="survivor" have={tally.survivor} need={1} />
              </>
            }
          >
            {dirty && <span className="text-xs text-muted-foreground">unsaved</span>}
            {/* Save keeps a half-finished week; submit is the one that says
                the week is done. Both write the same rows — the difference is
                that submit refuses an incomplete slate and save does not, so a
                draft can survive a closed tab without pretending to be an
                entry (#128). */}
            <Button size="sm" variant="outline" onClick={() => save(false)} disabled={!dirty}>
              Save draft
            </Button>
            <Button size="sm" onClick={() => save(true)} disabled={!complete}>
              Submit picks
            </Button>
          </ActionBar>

          {/* The shortfall, named. "5/6 regular" tells you a number is wrong;
              this tells you what to go and do. */}
          {missing.length > 0 ? (
            <p className="text-sm text-muted-foreground">
              Still to pick: <b className="text-foreground">{missing.join(', ')}</b>.
            </p>
          ) : (
            submitted?.key === weekKey && (
              <p className="text-sm text-muted-foreground">
                Submitted{' '}
                {submitted.at
                  ? new Date(submitted.at).toLocaleString(undefined, {
                      weekday: 'short',
                      hour: 'numeric',
                      minute: '2-digit',
                    })
                  : 'at an unknown time'}
                .
              </p>
            )
          )}

          {/* Said once, not printed as "TBD" on sixteen rows. Until Friday the
              pool line does not exist, so there is no gap to show and the
              number on each side is the market's. */}
          {games.length > 0 && games.every((g) => g.pool_spread === null) && (
            <p className="text-sm text-muted-foreground">
              Pool lines are not in yet. Showing the market.
            </p>
          )}

          <div className="divide-y divide-border rounded-lg border border-border bg-card">
            {/* Same six columns as a game row, so the labels sit over what
                they name. */}
            <div className="grid grid-cols-[1.5rem_1fr_auto_1fr_1.5rem_1rem] items-center gap-1.5 px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground sm:gap-2 sm:px-3">
              <span />
              <span className="flex items-center justify-end gap-1">
                Away
                <Info text="The number on each side is the line that side is getting. A green number means the pool prices that side better than the market: our biggest measured edge, and the side without it has gone 45.2% over six seasons." />
              </span>
              <span className="w-10 text-center sm:w-12">Total</span>
              <span>Home</span>
              <span />
              <span />
            </div>
            {games.map((g) => (
              <div
                key={g.game_id}
                // Six columns, and the two that hold a button are the only
                // ones that grow. The middle used to be a slash-separated cell
                // three numbers wide, sized for its longest content, which is
                // what pushed the two buttons out to the edges and left a
                // third of the row empty.
                className="grid grid-cols-[1.5rem_1fr_auto_1fr_1.5rem_1rem] items-center gap-1.5 px-2 py-2 sm:gap-2 sm:px-3"
              >
                <img src={teamLogo(g.away_team)} className="size-6" alt="" />
                <span className="flex min-w-0 items-center justify-end gap-1.5">
                  {teamButton(g, g.away_team, 'away')}
                  {edgeChip(g, g.away_team)}
                </span>
                {/* The total plays no part in pool scoring, so it is the
                    quietest thing on the row rather than a third of its
                    width. */}
                <span className="tabular w-10 text-center text-xs text-muted-foreground sm:w-12 sm:text-sm">
                  {g.market_total ?? '—'}
                </span>
                <span className="flex min-w-0 items-center gap-1.5">
                  {edgeChip(g, g.home_team)}
                  {teamButton(g, g.home_team, 'home')}
                </span>
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
                {guardrailWarning(g)}
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
            {/* The whole list stays. It used to collapse to the chosen row, so
                changing your mind meant deselecting to see what else was there. */}
            {favorites.map((f) => poolRow(f, survivor, setSurvivor, Skull, 'survivor'))}
          </div>

          <div className="rounded-lg border border-border bg-card p-3">
            <h2 className="flex items-center gap-1.5 text-sm font-bold">
              <Dog className="size-4" /> Underdog
            </h2>
            <p className="mb-2 text-xs text-muted-foreground">One underdog for the week.</p>
            {underdogs.map((d) => poolRow(d, underdog, setUnderdog, Dog, 'underdog'))}
          </div>

          {summary && (
            <div className="rounded-lg border border-border bg-card p-3">
              <h2 className="mb-2 text-sm font-bold">Summary</h2>
              <pre className="overflow-x-auto rounded-md bg-muted p-3 text-sm whitespace-pre-wrap">
                {summary}
              </pre>
              <div className="mt-3 flex gap-2">
                <Button size="sm" variant="outline" onClick={copySummary}>
                  <Clipboard className="size-3.5" /> Copy for the chat
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

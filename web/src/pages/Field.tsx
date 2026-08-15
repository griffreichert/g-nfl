import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, ChevronRight, Star } from 'lucide-react'
import { api, teamLogo } from '../api'
import { fmtSpread, useConfig, useSeasonWeek } from '../hooks'
import type { GameLine, Pick, PickRecord } from '../types'
import {
  BANDS,
  bestSide,
  buildAttachment,
  buildConsensus,
  cycleSlot,
  byScore,
  partRating,
  findBlocs,
  isAtsPick,
  isVoter,
  MAX_REGULAR,
  slotCounts,
  scoreSide,
  spreadFor,
  TEAM_2025,
  TEAM_PICKER,
  type ConsensusRow,
  type Overrides,
  type Score,
  type Slate,
  type SlotType,
  type SidePick,
} from '@/lib/consensus'
import BandChart from '@/components/BandChart'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import PageHeader from '@/components/PageHeader'
import { ErrorNote, Loading } from '@/components/PageState'

/** The two side pools. Separate objectives, separate games, own state. */
type Pool = 'underdog' | 'survivor'
type Special = { game_id: string; team: string } | null

const pickerOrder = (a: string, b: string) =>
  a === TEAM_PICKER ? 1 : b === TEAM_PICKER ? -1 : a.localeCompare(b)

/**
 * One chip per independent opinion. Pickers who vote together get one chip
 * between them, so a duplicate vote can't read as two people agreeing.
 */
function Chip({ picks, bb }: { picks: string[]; bb: boolean }) {
  return (
    <span
      className={`inline-flex h-6 items-center gap-1 rounded-full border px-2 text-xs font-medium ${
        bb ? 'border-bb bg-bb-soft text-bb' : 'border-border text-muted-foreground'
      }`}
      title={picks.length > 1 ? `${picks.join(' and ')} vote together` : undefined}
    >
      {picks.join('+')}
      {bb && <Star className="size-3 fill-current" />}
    </span>
  )
}

/** Group a side's pickers into blocs, preserving order of first appearance. */
function toChips(picks: SidePick[], blocs: string[][]) {
  const out: { picks: string[]; bb: boolean }[] = []
  const seen = new Map<number, number>()
  for (const p of picks) {
    const idx = blocs.findIndex((b) => b.includes(p.picker))
    const at = idx === -1 ? undefined : seen.get(idx)
    if (at === undefined) {
      seen.set(idx, out.length)
      out.push({ picks: [p.picker], bb: p.bb })
    } else {
      out[at].picks.push(p.picker)
      out[at].bb = out[at].bb || p.bb
    }
  }
  return out
}

/**
 * 0-10, where 5 is the -110 break-even. Deliberately not a percentage: the
 * numbers behind it are one season of hit rates and a printed rate reads like a
 * win probability, which it is not.
 */
function Rating({ score }: { score: Score }) {
  const good = score.rating >= 5
  return (
    <span
      className={`tabular rounded px-1.5 py-0.5 text-sm font-bold ${
        good ? 'bg-win/15 text-win' : 'bg-loss/15 text-loss'
      }`}
      title={score.parts
        .map(
          (p) =>
            `${p.label}: ${partRating(p.value, score.slope) > 0 ? '+' : ''}${partRating(p.value, score.slope).toFixed(1)}${
              p.measured ? '' : ' (judgement)'
            }`,
        )
        .join('\n')}
    >
      {score.rating.toFixed(1)}
    </span>
  )
}

const SLOT_LABEL: Record<SlotType, string> = {
  best_bet: 'Best bet',
  regular: 'Regular',
  mnf: 'MNF',
}

/**
 * One side of a game, laid out to mirror the picks page: away on the left,
 * home on the right, facing each other. Rating and who is on it sit underneath
 * the team rather than beside it, so the columns line up down the board.
 */
function SideCell({
  team,
  spread,
  picks,
  score,
  blocs,
  slot,
  disabled,
  home,
  onPick,
}: {
  team: string
  spread: number | null
  picks: SidePick[]
  score: Score
  blocs: string[][]
  slot: SlotType | null
  disabled: boolean
  home: boolean
  onPick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onPick}
      disabled={disabled}
      className={`flex min-w-0 flex-col gap-1.5 rounded-md border p-2 transition-colors ${
        home ? 'items-end text-right' : 'items-start text-left'
      } ${
        slot
          ? slot === 'best_bet'
            ? 'border-bb bg-bb-soft'
            : 'border-pick bg-pick-soft'
          : 'border-border/40 hover:border-border'
      }`}
    >
      <span className={`flex items-center gap-1.5 ${home ? 'flex-row-reverse' : ''}`}>
        <img src={teamLogo(team)} alt="" className={`size-6 ${picks.length ? '' : 'opacity-40'}`} />
        <span className="font-semibold">{team}</span>
        <span className="tabular text-sm text-muted-foreground">{fmtSpread(spread)}</span>
      </span>

      <span className={`flex items-center gap-1.5 ${home ? 'flex-row-reverse' : ''}`}>
        <Rating score={score} />
        {slot && (
          <span className="inline-flex items-center gap-1 rounded bg-foreground px-1.5 py-0.5 text-[10px] font-bold text-background">
            {slot === 'best_bet' && <Star className="size-3 fill-current" />}
            {SLOT_LABEL[slot]}
          </span>
        )}
      </span>

      <span className={`flex flex-wrap gap-1 ${home ? 'justify-end' : ''}`}>
        {toChips(picks, blocs).map((c) => (
          <Chip key={c.picks.join('+')} picks={c.picks} bb={c.bb} />
        ))}
      </span>
    </button>
  )
}

function GameCard({
  row,
  attachment,
  blocs,
  slate,
  full,
  onPick,
  note,
  onNote,
}: {
  row: ConsensusRow
  attachment: Map<string, number>
  blocs: string[][]
  slate: Slate
  full: boolean
  onPick: (team: string) => void
  note: string
  onNote: (v: string) => void
}) {
  const chosen = slate[row.game.game_id]
  // A full slate locks games we haven't used; a game already in the entry stays
  // live so the room can switch sides without dismantling the slate first.
  const locked = full && !chosen
  const { away_team: away, home_team: home } = row.game

  return (
    <div
      className={`rounded-lg border bg-card p-2 ${
        chosen ? 'border-foreground/25' : 'border-border'
      } ${locked ? 'opacity-70' : ''}`}
    >
      <div className="flex items-center px-2 pb-1">
        {row.game.is_mnf && (
          <p className="text-[11px] font-medium text-muted-foreground">Monday night</p>
        )}
        {/* Its own control: tapping a side is a pick, so the card can't be a link. */}
        <Link
          to={`/game/${row.game.game_id}`}
          aria-label={`Detail for ${away} at ${home}`}
          title="Game detail"
          className="ml-auto flex items-center gap-0.5 text-[11px] text-muted-foreground hover:text-foreground"
        >
          detail <ChevronRight className="size-3.5" />
        </Link>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {[away, home].map((team) => (
          <SideCell
            key={team}
            team={team}
            spread={spreadFor(row.game, team)}
            picks={team === row.side ? row.sidePicks : row.otherPicks}
            score={scoreSide(row, team, attachment)}
            blocs={blocs}
            slot={chosen?.team === team ? chosen.type : null}
            disabled={locked}
            home={team === home}
            onPick={() => onPick(team)}
          />
        ))}
      </div>
      {/* The meeting's reasoning is the thing nothing else records — grading can
          reconstruct what we picked, never why. Only on games in the entry. */}
      {chosen && (
        <input
          type="text"
          value={note}
          placeholder="Why? (optional)"
          onChange={(e) => onNote(e.target.value)}
          aria-label={`Note for ${away} at ${home}`}
          className="mt-2 h-8 w-full rounded-md border border-input bg-transparent px-2 text-sm shadow-xs outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 dark:bg-input/30"
        />
      )}
    </div>
  )
}

/** Every side someone took, picker by picker — the dense view for a laptop. */
function Grid({ rows, pickers }: { rows: ConsensusRow[]; pickers: string[] }) {
  const sides = rows.flatMap((r) => [
    { team: r.side, spread: r.spread, picks: r.sidePicks, gameId: r.game.game_id },
    {
      team: r.other,
      spread: spreadFor(r.game, r.other),
      picks: r.otherPicks,
      gameId: r.game.game_id,
    },
  ])

  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="sticky left-0 bg-card">Side</TableHead>
            {pickers.map((p) => (
              <TableHead key={p} className="text-center">
                {p.slice(0, 3)}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {sides
            .filter((s) => s.picks.length > 0)
            .map((s) => (
              <TableRow key={`${s.gameId}-${s.team}`}>
                <TableCell className="sticky left-0 whitespace-nowrap bg-card">
                  <span className="flex items-center gap-1.5">
                    <img src={teamLogo(s.team)} className="size-5" alt="" />
                    <b>{s.team}</b>
                    <span className="tabular text-muted-foreground">{fmtSpread(s.spread)}</span>
                  </span>
                </TableCell>
                {pickers.map((p) => {
                  const hit = s.picks.find((x) => x.picker === p)
                  return (
                    <TableCell key={p} className="text-center">
                      {hit ? (
                        <span className={hit.bb ? 'font-bold text-bb' : 'text-pick'}>
                          {hit.bb ? '★' : '●'}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">·</span>
                      )}
                    </TableCell>
                  )
                })}
              </TableRow>
            ))}
        </TableBody>
      </Table>
    </div>
  )
}

/** Survivor is per-picker inventory, so it needs the whole season, not just this week. */
function Survivor({
  seasonPicks,
  week,
  weekPicks,
}: {
  seasonPicks: PickRecord[] | null
  week: number
  weekPicks: PickRecord[]
}) {
  const byPicker = useMemo(() => {
    const used = new Map<string, { week: number; team: string }[]>()
    for (const p of seasonPicks ?? []) {
      if (p.pick_type !== 'survivor') continue
      const list = used.get(p.picker) ?? []
      list.push({ week: p.week, team: p.team_picked })
      used.set(p.picker, list)
    }
    for (const list of used.values()) list.sort((a, b) => a.week - b.week)
    return [...used.entries()].sort(([a], [b]) => pickerOrder(a, b))
  }, [seasonPicks])

  const dogs = weekPicks
    .filter((p) => p.pick_type === 'underdog')
    .sort((a, b) => (b.spread ?? 0) - (a.spread ?? 0))

  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-lg border border-border bg-card p-3">
        <h2 className="mb-2 text-sm font-bold">Survivor — teams spent</h2>
        {seasonPicks === null && <Loading />}
        <div className="flex flex-col gap-2">
          {byPicker.map(([picker, used]) => (
            <div key={picker} className="flex flex-wrap items-center gap-2">
              <span className="w-16 shrink-0 text-sm font-bold">{picker}</span>
              {used.map((u) => (
                <span
                  key={`${u.week}-${u.team}`}
                  className={`inline-flex h-6 items-center gap-1 rounded-full border px-2 text-xs ${
                    u.week === week
                      ? 'border-pick font-bold text-pick'
                      : 'border-border text-muted-foreground line-through'
                  }`}
                  title={`week ${u.week}`}
                >
                  <img src={teamLogo(u.team)} alt="" className="size-3.5" />
                  {u.team}
                </span>
              ))}
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-lg border border-border bg-card p-3">
        <h2 className="mb-2 text-sm font-bold">Underdog — week {week}</h2>
        {dogs.length === 0 && <p className="text-sm text-muted-foreground">No dog picks yet.</p>}
        <div className="flex flex-col gap-1.5">
          {dogs.map((d) => (
            <div key={`${d.picker}-${d.game_id}`} className="flex items-center gap-2 text-sm">
              <span className="w-16 shrink-0 font-bold">{d.picker}</span>
              <img src={teamLogo(d.team_picked)} alt="" className="size-5" />
              <b>{d.team_picked}</b>
              <span className="tabular text-muted-foreground">{fmtSpread(d.spread)}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}

/**
 * A side pool: one team from a candidate list. Deliberately plainer than the
 * ATS board — neither pool is scored, so showing a rating here would imply a
 * model that does not exist.
 */
function PoolPicker({
  title,
  hint,
  options,
  chosen,
  onPick,
}: {
  title: string
  hint: string
  options: { game: GameLine; team: string; spread: number | null; disabled?: boolean }[]
  chosen: Special
  onPick: (value: Special) => void
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <h2 className="text-sm font-bold">{title}</h2>
      <p className="mb-2 text-xs text-muted-foreground">{hint}</p>
      <div className="flex flex-wrap gap-1.5">
        {options.map((o) => {
          const on = chosen?.team === o.team && chosen?.game_id === o.game.game_id
          return (
            <button
              key={`${o.game.game_id}_${o.team}`}
              type="button"
              disabled={o.disabled}
              onClick={() => onPick(on ? null : { game_id: o.game.game_id, team: o.team })}
              title={o.disabled ? 'Already spent this season' : undefined}
              className={`inline-flex h-8 items-center gap-1.5 rounded-md border px-2 text-sm transition-colors disabled:opacity-35 ${
                on
                  ? 'border-pick bg-pick-soft font-semibold'
                  : 'border-border/60 hover:border-border'
              }`}
            >
              <img src={teamLogo(o.team)} alt="" className="size-5" />
              {o.team}
              <span className="tabular text-xs text-muted-foreground">{fmtSpread(o.spread)}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

/** One slot of the entry: filled, or how many are still open. */
function Slot({ label, have, need }: { label: string; have: number; need: number }) {
  const done = have === need
  return (
    <span className={done ? 'flex items-center gap-1 text-foreground' : 'flex items-center gap-1 text-muted-foreground'}>
      {done ? <Check className="size-3.5 text-win" /> : null}
      {label} {have}/{need}
    </span>
  )
}

export default function Field() {
  const { config, error: configError } = useConfig()
  const { season, setSeason, week, setWeek, weeks, seasons } = useSeasonWeek(config)
  const [picks, setPicks] = useState<PickRecord[]>([])
  const [games, setGames] = useState<GameLine[]>([])
  const [fetchedSeason, setSeasonPicks] = useState<{
    key: string
    rows: PickRecord[]
  } | null>(null)
  const seasonKey = `${season}-${weeks.join(',')}`
  const seasonPicks = fetchedSeason?.key === seasonKey ? fetchedSeason.rows : null
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  // Both are keyed by season+week so switching weeks drops them without an effect.
  const [edits, setEdits] = useState<{ key: string; overrides: Overrides }>({
    key: '',
    overrides: {},
  })
  const [saved, setSaved] = useState<{ key: string; msg: string } | null>(null)
  // Underdog and survivor are separate pools on their own games, so they cannot
  // live in the slate (which is keyed by game and holds one ATS pick each).
  const [extras, setExtras] = useState<{ key: string; picks: Partial<Record<Pool, Special>> }>({
    key: '',
    picks: {},
  })

  useEffect(() => {
    if (season === null || week === null) return
    let cancelled = false
    Promise.all([api.picks(season, week), api.lines(season, week)])
      .then(([p, g]) => {
        if (cancelled) return
        setPicks(p)
        setGames(g)
        setError(null)
      })
      .catch((e) => !cancelled && setError(String(e)))
    return () => {
      cancelled = true
    }
  }, [season, week])

  // Blocs need the whole season — one week is far too little to tell a habit
  // from a coincidence. Survivor inventory rides along on the same fetch.
  useEffect(() => {
    if (season === null || weeks.length === 0) return
    let cancelled = false
    const key = `${season}-${weeks.join(',')}`
    Promise.all(weeks.map((w) => api.picks(season, w)))
      .then((all) => !cancelled && setSeasonPicks({ key, rows: all.flat() }))
      .catch(() => !cancelled && setSeasonPicks({ key, rows: [] }))
    return () => {
      cancelled = true
    }
  }, [season, weeks])

  const blocs = useMemo(() => findBlocs(seasonPicks ?? []), [seasonPicks])
  // Attachment rides on the season fetch the blocs already need — no extra call.
  const attachment = useMemo(() => buildAttachment(seasonPicks ?? []), [seasonPicks])
  const rows = useMemo(() => {
    const built = buildConsensus(games, picks, blocs)
    const best = new Map(
      built.map((r) => [r.game.game_id, bestSide(r, attachment).score.rating]),
    )
    return built.sort(byScore(best))
  }, [games, picks, blocs, attachment])
  const pickers = useMemo(
    () => [...new Set(picks.map((p) => p.picker))].sort(pickerOrder),
    [picks],
  )

  /**
   * Open the call with a slate already on the table. Arguing about a proposal is
   * faster than starting from sixteen blank games, and the proposal is the
   * ranking we already trust: the Monday game first because that slot is forced,
   * then the best remaining side as the best bet, then five regulars.
   *
   * Anything TEAM already submitted for the week wins over the proposal — that
   * is a decision the room made, and this page does not get to overwrite it.
   */
  const proposal = useMemo(() => {
    const submitted: Slate = {}
    for (const r of rows) {
      const t = picks.find(
        (p) => p.picker === TEAM_PICKER && p.game_id === r.game.game_id && isAtsPick(p.pick_type),
      )
      if (t) submitted[r.game.game_id] = { team: t.team_picked, type: t.pick_type as SlotType }
    }
    if (Object.keys(submitted).length > 0) return submitted

    const out: Slate = {}
    let regulars = 0
    let bb = false
    for (const r of rows) {
      const best = bestSide(r, attachment)
      if (r.game.is_mnf) out[r.game.game_id] = { team: best.team, type: 'mnf' }
      else if (!bb) {
        out[r.game.game_id] = { team: best.team, type: 'best_bet' }
        bb = true
      } else if (regulars < MAX_REGULAR) {
        out[r.game.game_id] = { team: best.team, type: 'regular' }
        regulars++
      }
    }
    return out
  }, [rows, picks, attachment])

  const weekKey = `${season}-${week}`
  const slate = useMemo(() => {
    const merged: Slate = { ...proposal }
    if (edits.key !== weekKey) return merged
    for (const [id, v] of Object.entries(edits.overrides)) {
      if (v === null) delete merged[id]
      else merged[id] = v
    }
    return merged
  }, [proposal, edits, weekKey])

  const counts = useMemo(() => slotCounts(slate), [slate])

  /**
   * Whatever TEAM already submitted, unless the room has changed it since. No
   * proposal here: the dog is outright-win EV against spread size and survivor
   * is a season-long allocation, and the board's rating models neither.
   */
  const extra = (pool: Pool): Special => {
    if (extras.key === weekKey && pool in extras.picks) return extras.picks[pool] ?? null
    const p = picks.find((x) => x.picker === TEAM_PICKER && x.pick_type === pool)
    return p ? { game_id: p.game_id, team: p.team_picked } : null
  }
  const underdog = extra('underdog')
  const survivor = extra('survivor')

  const pickExtra = (pool: Pool, value: Special) => {
    setExtras((cur) => ({
      key: weekKey,
      picks: { ...(cur.key === weekKey ? cur.picks : {}), [pool]: value },
    }))
  }

  /** Every dog on the board, biggest first — the payout is the spread itself. */
  const dogs = useMemo(
    () =>
      games
        .flatMap((g) => [g.away_team, g.home_team].map((t) => ({ game: g, team: t })))
        .map((x) => ({ ...x, spread: spreadFor(x.game, x.team) }))
        .filter((x) => x.spread !== null && x.spread > 0)
        .sort((a, b) => (b.spread ?? 0) - (a.spread ?? 0)),
    [games],
  )

  /**
   * Survivor is about our own inventory, not the field's: a team TEAM has
   * already spent this season is gone, whatever anyone else did with it.
   */
  const spent = useMemo(() => {
    const used = new Set(config?.survivor_used_teams ?? [])
    for (const p of seasonPicks ?? []) {
      if (p.pick_type === 'survivor' && p.picker === TEAM_PICKER && p.week !== week) {
        used.add(p.team_picked)
      }
    }
    return used
  }, [seasonPicks, config, week])

  const favourites = useMemo(
    () =>
      games
        .flatMap((g) => [g.away_team, g.home_team].map((t) => ({ game: g, team: t })))
        .map((x) => ({ ...x, spread: spreadFor(x.game, x.team) }))
        .filter((x) => x.spread !== null && x.spread < 0)
        .sort((a, b) => (a.spread ?? 0) - (b.spread ?? 0)),
    [games],
  )

  const cycle = (row: ConsensusRow, team: string) => {
    const patch = cycleSlot(slate, row.game.game_id, team, row.game.is_mnf)
    if (Object.keys(patch).length === 0) return
    setEdits((cur) => ({
      key: weekKey,
      overrides: { ...(cur.key === weekKey ? cur.overrides : {}), ...patch },
    }))
  }

  // Keyed like the API keys a pick, so a survivor note and a regular note on
  // the same game stay separate.
  const noteKeyFor = (gameId: string, type: Pick['pick_type']) =>
    type === 'regular' || type === 'best_bet' ? gameId : `${type}_${gameId}`

  // Saved notes are derived from the fetched picks and typing is held as an
  // overlay, the same shape `edits` uses for the slate. Deriving avoids an
  // effect that would clobber what someone is mid-sentence on when picks refetch.
  const savedNotes = useMemo(() => {
    const saved: Record<string, string> = {}
    for (const p of picks) {
      if (p.picker === TEAM_PICKER && p.note) {
        saved[noteKeyFor(p.game_id, p.pick_type)] = p.note
      }
    }
    return saved
  }, [picks])
  const [noteEdits, setNoteEdits] = useState<Record<string, string>>({})
  const notes = { ...savedNotes, ...noteEdits }

  const saveSlate = async () => {
    if (season === null || week === null) return
    setSaving(true)
    try {
      const payload: Pick[] = Object.entries(slate).map(([game_id, v]) => ({
        game_id,
        team_picked: v.team,
        pick_type: v.type,
        spread: games.find((g) => g.game_id === game_id)?.market_spread ?? null,
        note: notes[noteKeyFor(game_id, v.type)]?.trim() || null,
      }))
      for (const [pool, choice] of [
        ['underdog', underdog],
        ['survivor', survivor],
      ] as const) {
        if (!choice) continue
        payload.push({
          game_id: choice.game_id,
          team_picked: choice.team,
          pick_type: pool,
          spread: games.find((g) => g.game_id === choice.game_id)?.market_spread ?? null,
          note: notes[noteKeyFor(choice.game_id, pool)]?.trim() || null,
        })
      }
      const res = await api.savePicks(season, week, TEAM_PICKER, payload)
      setSaved({ key: weekKey, msg: `Submitted ${res.saved} picks as TEAM` })
    } catch (e) {
      setSaved({ key: weekKey, msg: `Failed to save: ${e}` })
    } finally {
      setSaving(false)
    }
  }

  // Who still owes us a slate. The call can't settle a game nobody has voted on.
  const missing = (config?.pickers ?? []).filter(
    (p) => isVoter(p) && !pickers.includes(p),
  )

  const bandCounts = useMemo(() => {
    const c: Record<string, number> = {}
    for (const r of rows) {
      const n = r.sidePicks.length + r.otherPicks.length
      if (r.band) c[r.band.label] = (c[r.band.label] ?? 0) + n
    }
    return c
  }, [rows])

  if (configError) return <ErrorNote>Failed to load config: {configError}</ErrorNote>
  if (!config || season === null || week === null) return <Loading />

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Team"
        season={season}
        seasons={seasons}
        onSeason={setSeason}
        week={week}
        weeks={weeks}
        onWeek={setWeek}
      />

      {error && <p className="text-destructive">{error}</p>}
      {!error && rows.length === 0 && (
        <p className="text-muted-foreground">No picks yet for week {week}.</p>
      )}

      {!error && rows.length > 0 && (
        <Tabs defaultValue="board">
          <TabsList className="mb-3">
            <TabsTrigger value="board">Board</TabsTrigger>
            <TabsTrigger value="grid">Grid</TabsTrigger>
            <TabsTrigger value="survivor">Survivor</TabsTrigger>
          </TabsList>

          <TabsContent value="board" className="flex flex-col gap-3">
            {/* What the call is here to produce, and how much of it is left. */}
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-border bg-card px-3 py-2">
              <span className="text-sm font-bold">TEAM entry</span>
              <span className="flex flex-wrap gap-x-3 gap-y-1 text-sm">
                <Slot label="Best bet" have={counts.bb} need={1} />
                <Slot label="Regulars" have={counts.regular} need={MAX_REGULAR} />
                <Slot label="MNF" have={counts.mnf} need={1} />
                <Slot label="Dog" have={underdog ? 1 : 0} need={1} />
                <Slot label="Survivor" have={survivor ? 1 : 0} need={1} />
              </span>
              <Button size="sm" className="ml-auto" onClick={saveSlate} disabled={saving}>
                {saving ? 'Saving…' : 'Submit as TEAM'}
              </Button>
            </div>

            {saved?.key === weekKey && <p className="text-sm text-win">{saved.msg}</p>}

            {/* Design consequence 5 from the analysis: the uncomfortable number
                is the one that changes behaviour, so it sits where picks get made. */}
            <p className="text-xs text-muted-foreground">
              In 2025 TEAM took {TEAM_2025.rate}% of available pool points — last, behind every
              one of us — and followed the majority on {TEAM_2025.rubberStamp} games.{' '}
              <b>Averaging is what loses.</b> The entry below is a starting point to argue with,
              not a vote to ratify.
            </p>

            <p className="text-xs text-muted-foreground">
              Tap a side to add it, tap again to make it the best bet, once more to drop it.{' '}
              <Link to="/help" className="text-primary underline-offset-4 hover:underline">
                How this works
              </Link>
            </p>

            {missing.length > 0 && (
              <p className="text-sm text-muted-foreground">
                No picks in yet from {missing.join(', ')}.
              </p>
            )}

            <div className="flex flex-col gap-2">
              {rows.map((r) => (
                <GameCard
                  key={r.game.game_id}
                  row={r}
                  attachment={attachment}
                  blocs={blocs}
                  slate={slate}
                  full={counts.regular >= MAX_REGULAR && counts.bb >= 1}
                  onPick={(team) => cycle(r, team)}
                  note={notes[r.game.game_id] ?? ''}
                  onNote={(v) => setNoteEdits((n) => ({ ...n, [r.game.game_id]: v }))}
                />
              ))}
            </div>

            <PoolPicker
              title="Underdog"
              hint="One dog. If it wins outright we score its spread, so the biggest number that can actually win is the play. Nothing if it loses."
              options={dogs}
              chosen={underdog}
              onPick={(v) => pickExtra('underdog', v)}
            />

            <PoolPicker
              title="Survivor"
              hint={`One team to win outright. Teams we have already spent are greyed out${
                spent.size ? `: ${[...spent].sort().join(', ')}` : ''
              }.`}
              options={favourites.map((f) => ({ ...f, disabled: spent.has(f.team) }))}
              chosen={survivor}
              onPick={(v) => pickExtra('survivor', v)}
            />

            <div className="rounded-lg border border-border bg-card p-3">
              <h2 className="text-sm font-bold">Where we win and lose</h2>
              <p className="mb-1 text-xs text-muted-foreground">
                2025, 225 graded games. Close lines 52%, 3-7 45%, 7+ 44% — and the worst cell in
                the record is a home team laying or getting 3-7, at 37%. The instruction is avoid
                big numbers, not close games are good: 52% is still under break-even.
              </p>
              <BandChart counts={bandCounts} />
              <p className="text-xs text-muted-foreground">
                This week we have{' '}
                {BANDS.map((b) => `${bandCounts[b.label] ?? 0} in ${b.label}`).join(', ')}.
              </p>
            </div>

            <p className="text-xs text-muted-foreground">
              Every side is rated 0-10, best first. <b>5.0 is break-even</b> at -110, so a side
              under 5 costs us money over time. One measured term builds it: line size crossed
              with home or road. The rating used to carry three more — the best-bet slot, venue on
              its own, whether the room was split — and all three vanished when the numbers were
              recomputed per game instead of per pick. We put three votes on the average game, so
              counting picks counted the same game three times. Homer and stuck-on-them are
              judgement, capped so they can only break a tie; hover a rating for the breakdown.
              Full working in <code>notes/pick-analytics.md</code>.
            </p>
          </TabsContent>

          <TabsContent value="grid">
            <Grid rows={rows} pickers={pickers} />
          </TabsContent>

          <TabsContent value="survivor">
            <Survivor seasonPicks={seasonPicks} week={week} weekPicks={picks} />
          </TabsContent>
        </Tabs>
      )}
    </div>
  )
}

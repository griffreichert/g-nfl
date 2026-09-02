import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight, Star } from 'lucide-react'
import { api, teamLogo } from '../api'
import { fmtSpread, useAuth, useConfig, useGuardrails, useSeasonWeek } from '../hooks'
import type { GameLine, Pick, PickRecord } from '../types'
import {
  bestSide,
  buildAttachment,
  buildCandidates,
  buildConsensus,
  cycleSlot,
  byScore,
  partRating,
  findBlocs,
  isAtsPick,
  isVoter,
  isComplete,
  MAX_REGULAR,
  shortfall,
  slotCounts,
  spreadFor,
  TEAM_2025,
  TEAM_PICKER,
  type Candidate,
  type ConsensusRow,
  type Overrides,
  type Score,
  type Slate,
  type SlotTally,
  type SlotType,
  type SidePick,
} from '@/lib/consensus'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import PageHeader from '@/components/PageHeader'
import ActionBar, { Slot } from '@/components/ActionBar'
import { EmptyState, ErrorNote, Loading } from '@/components/PageState'

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

/** The promote control. Off, regular, best bet, off — one tap each way. */
function SlotButton({
  slot,
  locked,
  onPick,
}: {
  slot: SlotType | null
  locked: boolean
  onPick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onPick}
      disabled={locked}
      aria-label={slot ? `${SLOT_LABEL[slot]} — tap to change` : 'Promote this side'}
      className={`inline-flex h-8 min-w-8 items-center justify-center gap-1 rounded-md border px-2 text-xs font-bold transition-colors disabled:opacity-35 ${
        slot === 'best_bet'
          ? 'border-bb bg-bb text-primary-foreground'
          : slot
            ? 'border-pick bg-pick text-primary-foreground'
            : 'border-border/60 text-muted-foreground hover:border-border hover:text-foreground'
      }`}
    >
      {slot === 'best_bet' && <Star className="size-3.5 fill-current" />}
      {slot ? SLOT_LABEL[slot] : '+'}
    </button>
  )
}

/**
 * One candidate, as a row of the promotion table.
 *
 * Phone keeps the four columns a decision needs — the side, what it is worth,
 * how many of us are on it, and the control. PK collapses blocs in parentheses
 * when they differ from the headcount, so a 5 that is really a 4 says so. BB,
 * NET and WHO appear as the screen widens; on a phone WHO sits under the row
 * when the entry holds the side, which is when it matters.
 */
function CandidateRow({
  c,
  blocs,
  slot,
  locked,
  flags,
  onPick,
  note,
  onNote,
}: {
  c: Candidate
  blocs: string[][]
  slot: SlotType | null
  locked: boolean
  flags: number
  onPick: () => void
  note: string
  onNote: (v: string) => void
}) {
  const { away_team: away, home_team: home } = c.row.game
  return (
    <div
      className={`border-t border-border first:border-t-0 ${
        slot ? 'bg-pick-soft/40' : ''
      } ${locked ? 'opacity-50' : ''}`}
    >
      <div className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-2 px-2 py-2 sm:grid-cols-[1fr_auto_auto_auto_auto_auto] sm:px-3">
        {/* SIDE */}
        <div className="flex min-w-0 items-center gap-2">
          <img src={teamLogo(c.team)} alt="" className="size-6 shrink-0" />
          <span className="min-w-0">
            <span className="flex items-center gap-1.5">
              <b>{c.team}</b>
              <span className="tabular text-sm text-muted-foreground">
                {fmtSpread(c.spread)}
              </span>
              {c.row.game.is_mnf && (
                <span className="rounded bg-muted px-1 text-[10px] font-semibold uppercase text-muted-foreground">
                  mon
                </span>
              )}
            </span>
            <Link
              to={`/game/${c.row.game.game_id}`}
              className="flex items-center text-[11px] text-muted-foreground hover:text-foreground"
            >
              {c.team === home ? `vs ${away}` : `at ${home}`}
              <ChevronRight className="size-3" />
            </Link>
          </span>
        </div>

        {/* SCORE */}
        <Rating score={c.score} />

        {/* PK — headcount, with independent opinions in parentheses when they differ */}
        <span className="tabular w-12 text-center text-sm">
          <b>{c.picks.length}</b>
          {c.blocs !== c.picks.length && (
            <span className="text-muted-foreground">({c.blocs})</span>
          )}
        </span>

        {/* BB */}
        <span className="tabular hidden w-8 text-center text-sm sm:block">
          {c.bb ? <b className="text-bb">{c.bb}</b> : <span className="text-muted-foreground">·</span>}
        </span>

        {/* NET */}
        <span className="tabular hidden w-10 text-center text-sm text-muted-foreground md:block">
          {c.net > 0 ? `+${c.net}` : c.net}
        </span>

        {/* SLOT */}
        <SlotButton slot={slot} locked={locked} onPick={onPick} />
      </div>

      {/* WHO — its own line on a phone, inline from lg up. Chips are the one
          thing that says a 5-2 is really a 4-2. */}
      <div className="flex flex-wrap items-center gap-1 px-2 pb-2 sm:px-3">
        {toChips(c.picks, blocs).map((chip) => (
          <Chip key={chip.picks.join('+')} picks={chip.picks} bb={chip.bb} />
        ))}
        {c.picks.length === 0 && (
          <span className="text-xs text-muted-foreground">nobody suggested this</span>
        )}
        {flags > 0 && (
          <span className="rounded bg-loss/15 px-1.5 py-0.5 text-[11px] font-medium text-loss">
            {flags} guardrail{flags > 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* The meeting's reasoning is the thing nothing else records — grading
          can reconstruct what we picked, never why. */}
      {slot && (
        <div className="px-2 pb-2 sm:px-3">
          <input
            type="text"
            value={note}
            placeholder="Why? (optional)"
            onChange={(e) => onNote(e.target.value)}
            aria-label={`Note for ${c.team}`}
            className="h-8 w-full rounded-md border border-input bg-transparent px-2 text-sm shadow-xs outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 dark:bg-input/30"
          />
        </div>
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

/**
 * Pool spreads, edited where the picks are made (#135).
 *
 * This was its own tab, which put a Saturday chore in the navigation all week
 * and meant nobody could correct a line without leaving the board. The pool
 * spread is what picks grade against, so a wrong one is worth fixing the
 * moment somebody notices it, not after a round trip through another page.
 */
function LinesEditor({
  games,
  season,
  week,
  onSaved,
}: {
  games: GameLine[]
  season: number
  week: number
  onSaved: () => void
}) {
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [status, setStatus] = useState<string | null>(null)

  const valueFor = (g: GameLine) =>
    drafts[g.game_id] ?? g.pool_spread?.toString() ?? ''

  const saveOne = async (g: GameLine) => {
    const raw = valueFor(g)
    const spread = Number(raw)
    if (raw === '' || Number.isNaN(spread)) {
      setStatus(`Invalid spread for ${g.away_team} @ ${g.home_team}`)
      return
    }
    try {
      await api.updatePoolSpread(season, week, g.game_id, spread)
      setStatus(`Saved ${g.away_team} @ ${g.home_team}: ${fmtSpread(spread)}`)
      setDrafts((d) => {
        const next = { ...d }
        delete next[g.game_id]
        return next
      })
      onSaved()
    } catch (e) {
      setStatus(String(e))
    }
  }

  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <h2 className="text-sm font-bold">Pool lines</h2>
      <p className="mb-2 text-xs text-muted-foreground">
        What picks grade against. Blank means the market line stands.
      </p>
      {status && <p className="mb-2 text-xs text-muted-foreground">{status}</p>}
      <div className="divide-y divide-border">
        {games.map((g) => {
          const saved = g.pool_spread?.toString() ?? ''
          const dirty = valueFor(g) !== saved
          return (
            <div key={g.game_id} className="flex items-center gap-2 py-1.5 text-sm">
              <span className="min-w-0 flex-1 truncate">
                {g.away_team} @ {g.home_team}
                <span className="tabular ml-2 hidden text-muted-foreground sm:inline">
                  market {fmtSpread(g.market_spread)}
                </span>
              </span>
              <input
                type="number"
                step="0.5"
                inputMode="decimal"
                value={valueFor(g)}
                placeholder={fmtSpread(g.market_spread)}
                onChange={(e) => setDrafts((d) => ({ ...d, [g.game_id]: e.target.value }))}
                aria-label={`Pool spread for ${g.away_team} at ${g.home_team}`}
                className="tabular h-8 w-20 rounded-md border border-input bg-transparent px-2 text-right text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 dark:bg-input/30"
              />
              {/* Only a changed row offers a save: sixteen live buttons is
                  noise, and it makes an unsaved edit obvious. */}
              <Button
                size="sm"
                variant={dirty ? 'default' : 'outline'}
                disabled={!dirty}
                onClick={() => saveOne(g)}
              >
                Save
              </Button>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** The phrase, and what counts as typing it (#129). */
const CONFIRM_PHRASE = 'I am not a homer'
const matchesPhrase = (typed: string) =>
  typed.trim().replace(/\s+/g, ' ').toLowerCase() === CONFIRM_PHRASE.toLowerCase()

/** A submission time, or an honest admission that we do not have one. */
const fmtWhen = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleString(undefined, {
        weekday: 'short',
        hour: 'numeric',
        minute: '2-digit',
      })
    : 'an unknown time'

export default function Field() {
  // The board builds TEAM's entry, so TEAM's own spent teams are the ones that
  // matter here.
  const { config, error: configError } = useConfig('TEAM')
  const { picker: signedIn } = useAuth()
  const { season, setSeason, week, setWeek, weeks, seasons } = useSeasonWeek(config)
  const { guardrails, flagsFor, ruleById } = useGuardrails(season, week)

  // The one measured term in every side's rating. Served fitted, so the board
  // and the backtest cannot disagree about what a bad side is.
  const penalties = useMemo(
    () => (gameId: string, team: string) =>
      flagsFor(gameId, team).flatMap((id) => {
        const rule = ruleById(id)
        return rule ? [{ label: rule.label, value: rule.pct * 100 - rule.base_pct * 100 }] : []
      }),
    [flagsFor, ruleById],
  )
  const [picks, setPicks] = useState<PickRecord[]>([])
  const [games, setGames] = useState<GameLine[]>([])
  const [fetchedSeason, setSeasonPicks] = useState<{
    key: string
    rows: PickRecord[]
  } | null>(null)
  const seasonKey = `${season}`
  const seasonPicks = fetchedSeason?.key === seasonKey ? fetchedSeason.rows : null
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  // Bumped after a pool spread is edited, so the board's spreads and every
  // rating built on them are rebuilt from the saved number (#135).
  const [linesVersion, setLinesVersion] = useState(0)
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
  // The confirmation gate (#129), and the lines panel (#135). Both keyed to
  // nothing: they are transient UI, and a week change closing them is right.
  const [gateOpen, setGateOpen] = useState(false)
  const [typed, setTyped] = useState('')
  const [editingLines, setEditingLines] = useState(false)

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
  }, [season, week, linesVersion])

  // Blocs need the whole season — one week is far too little to tell a habit
  // from a coincidence. Survivor inventory rides along on the same fetch.
  //
  // One request. This used to ask for the season a week at a time, eighteen
  // requests deep, because /api/picks made `week` required (#124).
  useEffect(() => {
    if (season === null) return
    let cancelled = false
    const key = `${season}`
    api
      .picks(season)
      .then((rows) => !cancelled && setSeasonPicks({ key, rows }))
      .catch(() => !cancelled && setSeasonPicks({ key, rows: [] }))
    return () => {
      cancelled = true
    }
  }, [season])

  const blocs = useMemo(() => findBlocs(seasonPicks ?? []), [seasonPicks])
  // Attachment rides on the season fetch the blocs already need — no extra call.
  const attachment = useMemo(() => buildAttachment(seasonPicks ?? []), [seasonPicks])
  const rows = useMemo(() => {
    const built = buildConsensus(games, picks, blocs)
    const best = new Map(
      built.map((r) => [r.game.game_id, bestSide(r, attachment, penalties).score.rating]),
    )
    return built.sort(byScore(best))
    // `penalties` belongs here: guardrails resolve after games and picks, and
    // without the dependency the whole ranking stayed computed from an empty
    // penalty set, so the board ranked sides it should have marked down (#124).
  }, [games, picks, blocs, attachment, penalties])
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
      const best = bestSide(r, attachment, penalties)
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
  }, [rows, picks, attachment, penalties])

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

  /** Every side worth arguing about, best first (#127). */
  const candidates = useMemo(
    () => buildCandidates(rows, attachment, penalties, blocs, slate),
    [rows, attachment, penalties, blocs, slate],
  )

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

  // What the room saw when it picked, from the picked side. Grading joins the
  // line tables and ignores this column, so it is a record rather than an
  // input; it used to store the market number even though the pool grades
  // against its own.
  const spreadSeen = (gameId: string, team: string) => {
    const game = games.find((g) => g.game_id === gameId)
    return game ? spreadFor(game, team) : null
  }

  // Overriding a guardrail is allowed and has to be explained. The rules find
  // bad picks reliably and cannot rank good ones, so the room keeps the last
  // word; what it does not keep is the ability to do it silently.
  const unexplained = Object.entries(slate)
    .filter(([gameId, v]) => flagsFor(gameId, v.team).length)
    .filter(([gameId, v]) => !notes[noteKeyFor(gameId, v.type)]?.trim())
    .map(([gameId, v]) => `${v.team} (${flagsFor(gameId, v.team).length})`)

  const saveSlate = async () => {
    if (season === null || week === null) return
    setSaving(true)
    try {
      const payload: Pick[] = Object.entries(slate).map(([game_id, v]) => ({
        game_id,
        team_picked: v.team,
        pick_type: v.type,
        spread: spreadSeen(game_id, v.team),
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
          spread: spreadSeen(choice.game_id, choice.team),
          note: notes[noteKeyFor(choice.game_id, pool)]?.trim() || null,
        })
      }
      const res = await api.savePicks(season, week, payload, TEAM_PICKER)
      setSaved({ key: weekKey, msg: `Submitted ${res.saved} picks as TEAM` })
      setGateOpen(false)
      setTyped('')
    } catch (e) {
      setSaved({ key: weekKey, msg: `Failed to save: ${e}` })
    } finally {
      setSaving(false)
    }
  }

  // Who still owes us a slate, and who has started one without finishing it.
  // A half-finished week is visible on purpose: hiding it would let someone
  // sit out the week invisibly (#128).
  const missing = (config?.pickers ?? []).filter(
    (p) => isVoter(p) && !pickers.includes(p),
  )

  const incomplete = useMemo(() => {
    const tally = new Map<string, SlotTally>()
    for (const p of picks) {
      if (!isVoter(p.picker)) continue
      const t =
        tally.get(p.picker) ?? { bb: 0, regular: 0, mnf: 0, underdog: 0, survivor: 0 }
      if (p.pick_type === 'best_bet') t.bb++
      else if (p.pick_type === 'regular') t.regular++
      else if (p.pick_type === 'mnf') t.mnf++
      else if (p.pick_type === 'underdog') t.underdog++
      else if (p.pick_type === 'survivor') t.survivor++
      tally.set(p.picker, t)
    }
    return [...tally.entries()]
      .filter(([, t]) => !isComplete(t))
      .map(([who, t]) => `${who} (${shortfall(t).join(', ')})`)
      .sort()
  }, [picks])

  /**
   * What the signed-in picker has of their own week, and when TEAM last went
   * in. Both drive the two entry points at the top of the page (#135, #131).
   */
  const mine = useMemo(
    () => (signedIn ? picks.filter((p) => p.picker === signedIn) : []),
    [picks, signedIn],
  )
  const mineComplete = useMemo(() => {
    const t: SlotTally = { bb: 0, regular: 0, mnf: 0, underdog: 0, survivor: 0 }
    for (const p of mine) {
      if (p.pick_type === 'best_bet') t.bb++
      else if (p.pick_type === 'regular') t.regular++
      else if (p.pick_type === 'mnf') t.mnf++
      else if (p.pick_type === 'underdog') t.underdog++
      else if (p.pick_type === 'survivor') t.survivor++
    }
    return isComplete(t)
  }, [mine])

  const teamEntry = useMemo(() => {
    const rows = picks.filter((p) => p.picker === TEAM_PICKER)
    if (!rows.length) return null
    return {
      by: rows.map((p) => p.submitted_by).find(Boolean) ?? null,
      at: rows.map((p) => p.submitted_at).find(Boolean) ?? null,
    }
  }, [picks])

  const flaggedSides = useMemo(() => {
    const c: Record<string, number> = {}
    for (const r of rows) {
      for (const team of [r.game.away_team, r.game.home_team]) {
        for (const id of flagsFor(r.game.game_id, team)) c[id] = (c[id] ?? 0) + 1
      }
    }
    return c
  }, [rows, flagsFor])

  if (configError) return <ErrorNote>Failed to load config: {configError}</ErrorNote>
  if (!config) return <Loading />
  if (season === null || week === null) return <Loading />

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Make Picks"
        season={season}
        seasons={seasons}
        onSeason={setSeason}
        week={week}
        weeks={weeks}
        onWeek={setWeek}
      />

      {/* Your own week, before the room's. The picks page left the navigation
          in #135: it is one job you do once, so it is a button here rather
          than a tab you walk past all week. */}
      {signedIn &&
        (mine.length === 0 ? (
          <Button asChild size="lg" className="w-full">
            <Link to="/picks">Make my picks for week {week}</Link>
          </Button>
        ) : (
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <span>
              Your week {week} slate is in
              {mineComplete ? '' : ', and still short'}
              {mine[0]?.submitted_at ? ` — ${fmtWhen(mine[0].submitted_at)}` : ''}.
            </span>
            <Button asChild size="sm" variant="outline">
              <Link to="/picks">Edit my picks</Link>
            </Button>
          </div>
        ))}

      {error && <p className="text-destructive">{error}</p>}
      {!error && rows.length === 0 && (
        <EmptyState
          title={`Nobody has picked week ${week} yet`}
          detail={
            signedIn
              ? 'The board fills in as picks land. Yours is the one that starts it.'
              : 'Sign in to put your slate in.'
          }
        />
      )}

      {!error && rows.length > 0 && (
        <Tabs defaultValue="board">
          <TabsList className="mb-3">
            <TabsTrigger value="board">Board</TabsTrigger>
            <TabsTrigger value="grid">Grid</TabsTrigger>
            <TabsTrigger value="survivor">Survivor</TabsTrigger>
          </TabsList>

          <TabsContent value="board" className="flex flex-col gap-3">
            {/* What the call is here to produce, and how much of it is left.
                Same bar, same place as the Picks page (#124). */}
            <ActionBar
              slots={
                <>
                  <span className="text-sm font-bold">TEAM</span>
                  <Slot label="best bet" have={counts.bb} need={1} />
                  <Slot label="regular" have={counts.regular} need={MAX_REGULAR} />
                  <Slot label="MNF" have={counts.mnf} need={1} />
                  <Slot label="dog" have={underdog ? 1 : 0} need={1} />
                  <Slot label="survivor" have={survivor ? 1 : 0} need={1} />
                </>
              }
            >
              <Button
                size="sm"
                variant="outline"
                onClick={() => setEditingLines((v) => !v)}
              >
                {editingLines ? 'Done with lines' : 'Edit lines'}
              </Button>
              <Button
                size="sm"
                onClick={() => setGateOpen(true)}
                disabled={saving || unexplained.length > 0 || gateOpen}
              >
                {saving ? 'Saving…' : 'Submit as TEAM'}
              </Button>
            </ActionBar>

            {/* The gate (#129). TEAM is the entry that came last in 2025 while
                agreeing with the room on 82 of 83 games, so submitting it costs
                a sentence typed on purpose. */}
            {gateOpen && (
              <div className="rounded-lg border border-bb bg-bb-soft/40 p-3">
                <h2 className="text-sm font-bold">Submit as TEAM</h2>
                {teamEntry && (
                  <p className="mt-1 text-sm text-loss">
                    {teamEntry.by
                      ? `TEAM was submitted by ${teamEntry.by} at ${fmtWhen(teamEntry.at)}.`
                      : `TEAM is already submitted for week ${week}.`}{' '}
                    Submitting again replaces it.
                  </p>
                )}
                <p className="mt-2 text-xs text-muted-foreground">
                  These picks go in as Team Reichert&apos;s entry. In 2025 TEAM took{' '}
                  {TEAM_2025.rate}% of available pool points, last behind every one of us,
                  and followed the room&apos;s majority on {TEAM_2025.rubberStamp} games.{' '}
                  <b>Averaging is what loses.</b>
                </p>
                <label
                  htmlFor="team-confirm"
                  className="mt-3 block text-xs font-medium text-foreground"
                >
                  Type <b>{CONFIRM_PHRASE}</b> to submit.
                </label>
                <input
                  id="team-confirm"
                  type="text"
                  value={typed}
                  autoComplete="off"
                  onChange={(e) => setTyped(e.target.value)}
                  placeholder={CONFIRM_PHRASE}
                  className="mt-1 h-9 w-full max-w-sm rounded-md border border-input bg-transparent px-2 text-sm shadow-xs outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 dark:bg-input/30"
                />
                {typed.trim() !== '' && !matchesPhrase(typed) && (
                  <p className="mt-1 text-xs text-loss">Type the phrase exactly.</p>
                )}
                <div className="mt-3 flex gap-2">
                  <Button size="sm" onClick={saveSlate} disabled={!matchesPhrase(typed) || saving}>
                    {saving ? 'Saving…' : 'Submit'}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setGateOpen(false)
                      setTyped('')
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            )}

            {unexplained.length > 0 && (
              <p className="rounded-md bg-loss/15 px-3 py-2 text-sm text-loss">
                {unexplained.join(', ')} {unexplained.length === 1 ? 'trips' : 'trip'} a
                guardrail. Say why in the note on that side before submitting. The rules
                do not get the last word, but an override should be on the record.
              </p>
            )}

            {saved?.key === weekKey && <p className="text-sm text-win">{saved.msg}</p>}

            {teamEntry && !gateOpen && (
              <p className="text-xs text-muted-foreground">
                {teamEntry.by
                  ? `TEAM submitted by ${teamEntry.by} at ${fmtWhen(teamEntry.at)}.`
                  : `TEAM submitted for week ${week}.`}
              </p>
            )}

            {editingLines && (
              <LinesEditor
                games={games}
                season={season}
                week={week}
                onSaved={() => setLinesVersion((v) => v + 1)}
              />
            )}

            <p className="text-xs text-muted-foreground">
              Every side below is one at least one of us took. Tap the control to add it,
              again to make it the best bet, once more to drop it.{' '}
              <Link to="/help" className="text-primary underline-offset-4 hover:underline">
                How this works
              </Link>
            </p>

            {missing.length > 0 && (
              <p className="text-sm text-muted-foreground">
                No picks in yet from {missing.join(', ')}.
              </p>
            )}
            {incomplete.length > 0 && (
              <p className="text-sm text-muted-foreground">
                Still short: {incomplete.join(', ')}.
              </p>
            )}

            {/* The promotion table (#127). Header row on a laptop; on a phone
                the columns speak for themselves and the header is dead height. */}
            <div className="overflow-hidden rounded-lg border border-border bg-card">
              <div className="hidden grid-cols-[1fr_auto_auto_auto_auto_auto] items-center gap-2 border-b border-border px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground sm:grid">
                <span>Side</span>
                <span className="w-10 text-center">Score</span>
                <span className="w-12 text-center">Pk</span>
                <span className="w-8 text-center">BB</span>
                <span className="hidden w-10 text-center md:block">Net</span>
                <span className="w-16 text-center">Slot</span>
              </div>
              {candidates.map((c) => {
                const chosen = slate[c.row.game.game_id]
                return (
                  <CandidateRow
                    key={`${c.row.game.game_id}_${c.team}`}
                    c={c}
                    blocs={blocs}
                    slot={chosen?.team === c.team ? chosen.type : null}
                    // A full entry locks sides it does not hold, so the room
                    // swaps deliberately rather than overflowing by accident.
                    locked={
                      counts.regular >= MAX_REGULAR &&
                      counts.bb >= 1 &&
                      !chosen &&
                      !c.row.game.is_mnf
                    }
                    flags={flagsFor(c.row.game.game_id, c.team).length}
                    onPick={() => cycle(c.row, c.team)}
                    note={notes[noteKeyFor(c.row.game.game_id, chosen?.type ?? 'regular')] ?? ''}
                    onNote={(v) =>
                      setNoteEdits((n) => ({
                        ...n,
                        [noteKeyFor(c.row.game.game_id, chosen?.type ?? 'regular')]: v,
                      }))
                    }
                  />
                )
              })}
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
              <h2 className="text-sm font-bold">Where we lose</h2>
              <p className="mb-2 text-xs text-muted-foreground">
                Fitted from{' '}
                {guardrails?.fitted_on.length
                  ? `${guardrails.fitted_on.length} seasons of our own picks`
                  : 'the pick record'}
                , refit on every deploy. A rule only appears here once it is below the
                field's own rate and below it in most seasons.
              </p>
              <ul className="flex flex-col gap-2">
                {(guardrails?.rules ?? []).map((r) => (
                  <li key={r.id} className="text-xs">
                    <span className="font-semibold text-foreground">{r.label}</span>{' '}
                    <span className="text-loss">{(r.pct * 100).toFixed(1)}%</span>{' '}
                    <span className="text-muted-foreground">
                      against {(r.base_pct * 100).toFixed(1)}%, over {r.games.toFixed(0)} games
                      {r.advisory ? ', advisory only' : ''}. {flaggedSides[r.id] ?? 0} sides
                      this week.
                    </span>
                  </li>
                ))}
                {!guardrails?.rules.length && (
                  <li className="text-xs text-muted-foreground">
                    No rule currently clears the bar.
                  </li>
                )}
              </ul>
              {!!guardrails?.rejected.length && (
                <p className="mt-2 text-[11px] text-muted-foreground">
                  Fitted and rejected:{' '}
                  {guardrails.rejected.map((r) => `${r.label} (${r.reason})`).join('; ')}.
                </p>
              )}
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

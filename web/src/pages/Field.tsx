import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight, Dog, Moon, Skull, Star } from 'lucide-react'
import { Popover as PopoverPrimitive } from 'radix-ui'
import { api, teamLogo } from '../api'
import {
  fmtSpread,
  POOL_BUTTON,
  POOL_TEXT,
  useAuth,
  useConfig,
  useGuardrails,
  useSeasonWeekRoute,
  type PoolColor,
} from '../hooks'
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
  pts,
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
import { Info } from '@/components/Info'
import ActionBar, {
  ActionBarSpacer,
  ClearButton,
  CopyButton,
  EditLinesButton,
  Slot,
} from '@/components/ActionBar'
import { LinesEditor } from '@/components/LinesEditor'
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
/** A bare name, styled like `Chip`'s unselected state. */
function NamePill({ name }: { name: string }) {
  return (
    <span className="inline-flex h-6 items-center rounded-full border border-border px-2 text-xs font-medium text-muted-foreground">
      {name}
    </span>
  )
}

function Chip({
  picks,
  bb,
  notes,
}: {
  picks: string[]
  bb: boolean
  notes: { picker: string; note: string }[]
}) {
  const [hover, setHover] = useState(false)
  const [pinned, setPinned] = useState(false)
  const open = notes.length > 0 && (hover || pinned)
  return (
    <PopoverPrimitive.Root
      open={open}
      onOpenChange={(v) => {
        if (!v) {
          setHover(false)
          setPinned(false)
        }
      }}
    >
      <PopoverPrimitive.Trigger asChild>
        <span
          onMouseEnter={() => setHover(true)}
          onMouseLeave={() => setHover(false)}
          onClick={() => notes.length > 0 && setPinned((p) => !p)}
          className={`inline-flex h-6 items-center gap-1 rounded-full border px-2 text-xs font-medium ${
            notes.length > 0 ? 'cursor-help' : ''
          } ${bb ? 'border-bb bg-bb-soft text-bb' : 'border-border text-muted-foreground'}`}
          title={picks.length > 1 ? `${picks.join(' and ')} vote together` : undefined}
        >
          {picks.join('+')}
          {bb && <Star className="size-3 fill-current" />}
          {notes.length > 0 && <span className="text-[10px] leading-none">💬</span>}
        </span>
      </PopoverPrimitive.Trigger>
      {notes.length > 0 && (
        <PopoverPrimitive.Portal>
          <PopoverPrimitive.Content
            side="top"
            sideOffset={6}
            className="z-50 flex max-w-64 flex-col gap-1 rounded-md border border-border bg-popover px-2.5 py-1.5 text-xs text-popover-foreground shadow-md"
          >
            {notes.map((n) => (
              <span key={n.picker}>
                <b>{n.picker}:</b> {n.note}
              </span>
            ))}
          </PopoverPrimitive.Content>
        </PopoverPrimitive.Portal>
      )}
    </PopoverPrimitive.Root>
  )
}

/** Group a side's pickers into blocs, preserving order of first appearance. */
function toChips(picks: SidePick[], blocs: string[][]) {
  const out: { picks: string[]; bb: boolean; notes: { picker: string; note: string }[] }[] = []
  const seen = new Map<number, number>()
  for (const p of picks) {
    const idx = blocs.findIndex((b) => b.includes(p.picker))
    const at = idx === -1 ? undefined : seen.get(idx)
    if (at === undefined) {
      seen.set(idx, out.length)
      out.push({
        picks: [p.picker],
        bb: p.bb,
        notes: p.note ? [{ picker: p.picker, note: p.note }] : [],
      })
    } else {
      out[at].picks.push(p.picker)
      out[at].bb = out[at].bb || p.bb
      if (p.note) out[at].notes.push({ picker: p.picker, note: p.note })
    }
  }
  return out
}

/**
 * 0-10, where 5 is the -110 break-even. Deliberately not a percentage: the
 * numbers behind it are one season of hit rates and a printed rate reads like a
 * win probability, which it is not.
 *
 * The breakdown used to ride a native `title`, which needs a mouse that sits
 * still — no tap, and no touch device at all, which is half the pool. Same
 * hover/tap Popover as `Info`, just with per-row content instead of one
 * fixed string.
 */
function Rating({ score }: { score: Score }) {
  const good = score.rating >= 5
  const [hover, setHover] = useState(false)
  const [pinned, setPinned] = useState(false)
  const open = hover || pinned

  return (
    <PopoverPrimitive.Root
      open={open}
      onOpenChange={(v) => {
        if (!v) {
          setHover(false)
          setPinned(false)
        }
      }}
    >
      <PopoverPrimitive.Trigger asChild>
        <button
          type="button"
          onMouseEnter={() => setHover(true)}
          onMouseLeave={() => setHover(false)}
          onClick={() => setPinned((p) => !p)}
          className={`tabular cursor-help rounded px-1.5 py-0.5 text-sm font-bold ${
            good ? 'bg-win/15 text-win' : 'bg-loss/15 text-loss'
          }`}
        >
          {score.rating.toFixed(1)}
        </button>
      </PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          side="top"
          sideOffset={6}
          className="z-50 flex max-w-64 flex-col gap-0.5 rounded-md border border-border bg-popover px-2.5 py-1.5 text-xs text-popover-foreground shadow-md"
        >
          {score.parts.map((p) => (
            <span key={p.label}>
              {p.label}: {partRating(p.value, score.slope) > 0 ? '+' : ''}
              {partRating(p.value, score.slope).toFixed(1)}
              {p.measured ? '' : ' (judgement)'}
            </span>
          ))}
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  )
}

type TableSortKey = 'score' | 'pts' | 'bb' | 'net'

/** A sortable column header: label, optional `Info`, click toggles asc/desc. */
function SortableHead({
  label,
  sortKey,
  sort,
  onSort,
  width,
  className = '',
  children,
}: {
  label: string
  sortKey: TableSortKey
  sort: { key: TableSortKey; desc: boolean } | null
  onSort: (key: TableSortKey) => void
  width: string
  className?: string
  children?: ReactNode
}) {
  const active = sort?.key === sortKey
  return (
    <span className={`flex ${width} items-center justify-center gap-1 ${className}`}>
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className={`cursor-pointer hover:text-foreground ${active ? 'text-foreground' : ''}`}
      >
        {label}
        {active && <span className="ml-0.5">{sort.desc ? '▾' : '▴'}</span>}
      </button>
      {children}
    </span>
  )
}

const SLOT_LABEL: Record<SlotType, string> = {
  best_bet: 'Best bet',
  regular: 'Regular',
  mnf: 'MNF',
}

/**
 * The promote control. Off, regular, best bet, off — one tap each way, except
 * the Monday game, which only ever toggles off/MNF: it can never become a
 * best bet, so it gets its own color and a moon icon in both states rather
 * than sharing the pick-blue "regular" look and reading like it could.
 */
function SlotButton({
  slot,
  isMnf,
  locked,
  onPick,
}: {
  slot: SlotType | null
  isMnf: boolean
  locked: boolean
  onPick: () => void
}) {
  const color: PoolColor = slot === 'best_bet' ? 'bb' : isMnf ? 'mnf' : 'pick'
  return (
    <button
      type="button"
      onClick={onPick}
      disabled={locked}
      aria-label={
        isMnf
          ? slot
            ? 'The Monday game — tap to drop'
            : 'Take the Monday game'
          : slot
            ? `${SLOT_LABEL[slot]} — tap to change`
            : 'Promote this side'
      }
      className={`inline-flex h-8 min-w-8 items-center justify-center gap-1 whitespace-nowrap rounded-md border px-2 text-xs font-bold transition-colors disabled:opacity-35 ${
        slot ? POOL_BUTTON[color].on : POOL_BUTTON[color].off
      }`}
    >
      {slot === 'best_bet' && <Star className="size-3.5 fill-current" />}
      {isMnf && <Moon className="size-3.5" />}
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
      <div className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-2 px-2 py-2 sm:grid-cols-[minmax(0,20rem)_1fr_3.5rem_2rem_3.5rem_4rem_7rem] sm:px-3">
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

        {/* WHO — fills the gap the name column leaves on a laptop instead of
            wasting it; chips are the one thing that says a 5-2 is really a
            4-2. Full-width below the row instead, on a phone, where this
            track doesn't exist. */}
        <div className="hidden flex-wrap items-center gap-1 sm:flex">
          {toChips(c.picks, blocs).map((chip) => (
            <Chip key={chip.picks.join('+')} picks={chip.picks} bb={chip.bb} notes={chip.notes} />
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

        {/* PTS — pool points this side carries, best bet worth two */}
        <span className="tabular w-14 text-center text-sm">
          <b>{pts(c.picks)}</b>
        </span>

        {/* BB */}
        <span className="tabular hidden w-8 text-center text-sm sm:block">
          {c.bb ? <b className="text-bb">{c.bb}</b> : <span className="text-muted-foreground">·</span>}
        </span>

        {/* NET */}
        <span className="tabular hidden w-14 text-center text-sm text-muted-foreground md:block">
          {c.net}
        </span>

        {/* SCORE */}
        <span className="flex w-16 justify-center">
          <Rating score={c.score} />
        </span>

        {/* PROMOTE */}
        <SlotButton
          slot={slot}
          isMnf={c.row.game.is_mnf}
          locked={locked}
          onPick={onPick}
        />
      </div>

      {/* WHO, phone only — the grid gains a column for this from sm up. */}
      <div className="flex flex-wrap items-center gap-1 px-2 pb-2 sm:hidden">
        {toChips(c.picks, blocs).map((chip) => (
          <Chip key={chip.picks.join('+')} picks={chip.picks} bb={chip.bb} notes={chip.notes} />
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
/**
 * Same row shape as `CandidateRow`/`SlotButton` — same grid columns as the
 * promotion table above (Pts/BB/Net/Score sit empty, unused here), so Side,
 * Pickers and Promote land in the exact same columns, and the same
 * `h-8 min-w-8` control in the Promote track, iconed for the pool instead of
 * a generic `+` (#126 follow-up: Griffin found the pill position and button
 * size inconsistent with the table above).
 */
function PoolPicker({
  title,
  icon: Icon,
  color,
  options,
  chosen,
  onPick,
}: {
  title: string
  icon: typeof Dog
  color: 'underdog' | 'survivor'
  options: {
    game: GameLine
    team: string
    spread: number | null
    disabled?: boolean
    pickers?: string[]
  }[]
  chosen: Special
  onPick: (value: Special) => void
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <h2 className="flex items-center gap-1.5 p-3 pb-2 text-sm font-bold">
        <Icon className="size-4" /> {title}
      </h2>
      {options.length === 0 ? (
        <p className="px-3 pb-3 text-sm text-muted-foreground">Nobody's suggested one yet.</p>
      ) : (
        <div className="divide-y divide-border">
          {options.map((o) => {
            const on = chosen?.team === o.team && chosen?.game_id === o.game.game_id
            const { away_team: away, home_team: home } = o.game
            return (
              <div
                key={`${o.game.game_id}_${o.team}`}
                className={on ? (color === 'underdog' ? 'bg-underdog-soft/40' : 'bg-survivor-soft/40') : ''}
              >
                <div className="grid grid-cols-[1fr_auto] items-center gap-2 px-2 py-2 sm:grid-cols-[minmax(0,20rem)_1fr_3.5rem_2rem_3.5rem_4rem_7rem] sm:px-3">
                  {/* SIDE */}
                  <div className="flex min-w-0 items-center gap-2">
                    <img src={teamLogo(o.team)} alt="" className="size-6 shrink-0" />
                    <span className="min-w-0">
                      <span className="flex items-center gap-1.5">
                        <b>{o.team}</b>
                        <span className="tabular text-sm text-muted-foreground">
                          {fmtSpread(o.spread)}
                        </span>
                      </span>
                      <Link
                        to={`/game/${o.game.game_id}`}
                        className="flex items-center text-[11px] text-muted-foreground hover:text-foreground"
                      >
                        {o.team === home ? `vs ${away}` : `at ${home}`}
                        <ChevronRight className="size-3" />
                      </Link>
                    </span>
                  </div>

                  {/* PICKERS — same track the table above calls Pickers */}
                  <div className="hidden flex-wrap items-center gap-1 sm:flex">
                    {o.pickers?.map((p) => <NamePill key={p} name={p} />)}
                  </div>

                  {/* PTS / BB / NET / SCORE — unused here, kept as empty
                      tracks so Pickers and Promote line up under the table
                      above regardless of screen width. */}
                  <span className="hidden sm:block" />
                  <span className="hidden sm:block" />
                  <span className="hidden sm:block" />
                  <span className="hidden sm:block" />

                  {/* PROMOTE — same size as SlotButton, iconed for the pool */}
                  <button
                    type="button"
                    disabled={o.disabled}
                    onClick={() => onPick(on ? null : { game_id: o.game.game_id, team: o.team })}
                    title={o.disabled ? 'Already spent this season' : undefined}
                    aria-label={on ? `${o.team} — tap to drop` : `Take ${o.team}`}
                    className={`inline-flex h-8 min-w-8 items-center justify-center gap-1 whitespace-nowrap rounded-md border px-2 text-xs font-bold transition-colors disabled:opacity-35 ${
                      on ? POOL_BUTTON[color].on : POOL_BUTTON[color].off
                    }`}
                  >
                    <Icon className="size-3.5" />
                    {on ? 'Taken' : '+'}
                  </button>
                </div>

                {/* Pickers, phone only — the grid gains the column from sm up. */}
                {o.pickers && o.pickers.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1 px-2 pb-2 sm:hidden">
                    {o.pickers.map((p) => (
                      <NamePill key={p} name={p} />
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
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
  const { season, setSeason, week, setWeek, weeks, seasons } = useSeasonWeekRoute(
    config,
    (s, w) => `/picks/${s}/week/${w}`,
  )
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
   * Whatever TEAM already submitted for the week — nothing else. This used to
   * default to an auto-built slate (Monday game, then best remaining side as
   * best bet, then five regulars) so the call opened with a proposal instead
   * of sixteen blank games. Griffin: that read as already-decided before
   * anyone had picked anything, and made "Submit As TEAM" look like it was
   * finalizing a choice that had, in effect, already been made. The bottom
   * bar and every slot button now start empty; a click is the only thing
   * that fills them.
   */
  const proposal = useMemo(() => {
    const submitted: Slate = {}
    for (const r of rows) {
      const t = picks.find(
        (p) => p.picker === TEAM_PICKER && p.game_id === r.game.game_id && isAtsPick(p.pick_type),
      )
      if (t) submitted[r.game.game_id] = { team: t.team_picked, type: t.pick_type as SlotType }
    }
    return submitted
  }, [rows, picks])

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

  // The Monday game isn't a candidate the room is ranking against the rest —
  // it's forced onto one game, so it gets its own section below the table
  // (like Underdog/Survivor) instead of a row the table's own sort can move
  // around.
  const mnfCandidates = useMemo(() => candidates.filter((c) => c.row.game.is_mnf), [candidates])
  const tableCandidates = useMemo(() => candidates.filter((c) => !c.row.game.is_mnf), [candidates])

  /** null keeps `buildCandidates`' own order (best score, then net, then contention). */
  const [tableSort, setTableSort] = useState<{ key: TableSortKey; desc: boolean } | null>(null)
  const sortedCandidates = useMemo(() => {
    if (!tableSort) return tableCandidates
    const sign = tableSort.desc ? -1 : 1
    const value = (c: Candidate) =>
      tableSort.key === 'score'
        ? c.score.rating
        : tableSort.key === 'pts'
          ? pts(c.picks)
          : tableSort.key === 'bb'
            ? c.bb
            : c.net
    return [...tableCandidates].sort((a, b) => sign * (value(a) - value(b)))
  }, [tableCandidates, tableSort])
  const toggleTableSort = (key: TableSortKey) =>
    setTableSort((s) => (s?.key === key ? { key, desc: !s.desc } : { key, desc: true }))

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

  const gameForId = (id: string) => rows.find((r) => r.game.game_id === id)?.game
  const gameForTeam = (team: string) =>
    rows.find((r) => r.game.away_team === team || r.game.home_team === team)?.game

  // Same chat-ready format as `MakePicks.tsx`'s summary, built off TEAM's
  // slate instead of an individual's picks (#126 follow-up: the Copy button
  // used to exist only on Submit My Picks).
  const summary = useMemo(() => {
    const lines: string[] = []
    const describe = (team: string, g: GameLine) => {
      const s = g.market_spread
      const home = team === g.home_team
      const spread = s === null ? '' : ` (${fmtSpread(home ? -s : s)})`
      return `${team}${spread} ${home ? 'vs' : 'at'} ${home ? g.away_team : g.home_team}`
    }
    const gameOf = (id: string) => games.find((g) => g.game_id === id)
    for (const [id, v] of Object.entries(slate).filter(([, v]) => v.type === 'best_bet')) {
      const g = gameOf(id)
      if (g) lines.push(`⭐️ ${describe(v.team, g)}`)
    }
    for (const [id, v] of Object.entries(slate).filter(([, v]) => v.type === 'regular')) {
      const g = gameOf(id)
      if (g) lines.push(describe(v.team, g))
    }
    for (const [id, v] of Object.entries(slate).filter(([, v]) => v.type === 'mnf')) {
      const g = gameOf(id)
      if (g) lines.push(`🌙 ${describe(v.team, g)}`)
    }
    for (const [emoji, choice] of [
      ['💀', survivor],
      ['🐶', underdog],
    ] as const) {
      if (!choice) continue
      const g = gameOf(choice.game_id)
      if (g) lines.push(`${emoji} ${describe(choice.team, g)}`)
    }
    return lines.length ? `TEAM's Week ${week} Picks\n\n${lines.join('\n')}` : ''
  }, [slate, survivor, underdog, games, week])

  // Drops back to `proposal` — whatever TEAM already submitted, or blank if
  // nothing has been yet. Nothing here writes to the server, so this is a
  // local, reversible reset, not an undo of a real submission.
  const clearSlate = () => {
    setEdits({ key: weekKey, overrides: {} })
    setExtras({ key: weekKey, picks: {} })
    setNoteEdits({})
  }
  const isEmpty = Object.keys(slate).length === 0 && !survivor && !underdog

  const [copyStatus, setCopyStatus] = useState<{ kind: 'ok' | 'err'; msg: string } | null>(null)
  const copySummary = async () => {
    try {
      await navigator.clipboard.writeText(summary)
      setCopyStatus({ kind: 'ok', msg: 'Summary copied — paste it in the chat' })
    } catch {
      setCopyStatus({ kind: 'err', msg: 'Could not reach the clipboard. Select the text above.' })
    }
  }

  // What the dots on the ribbon only count — the ribbon's expanded view. A
  // star marks the best bet rather than a repeated "Best Bet" label. One
  // ribbon row on a laptop, wide enough that the line rides right next to the
  // team instead of getting lost at the far edge; a stacked list on a phone,
  // where a row that wide would just wrap anyway.
  const pickItems = [
    ...Object.entries(slate)
      .filter(([, v]) => v.type === 'best_bet')
      .map(([id, v]) => ({ id, team: v.team, Icon: Star, color: 'bb' as const })),
    ...Object.entries(slate)
      .filter(([, v]) => v.type === 'regular')
      .map(([id, v]) => ({ id, team: v.team, Icon: null, color: 'pick' as const })),
    ...Object.entries(slate)
      .filter(([, v]) => v.type === 'mnf')
      .map(([id, v]) => ({ id, team: v.team, Icon: Moon, color: 'mnf' as const })),
    ...(underdog
      ? [{ id: underdog.game_id, team: underdog.team, Icon: Dog, color: 'underdog' as const }]
      : []),
    ...(survivor
      ? [{ id: survivor.game_id, team: survivor.team, Icon: Skull, color: 'survivor' as const }]
      : []),
  ]
  const pickDetail = (
    <div className="flex flex-col gap-1.5 text-sm sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-1 sm:gap-y-1.5">
      {pickItems.map((p, i) => {
        const g = gameForId(p.id) ?? gameForTeam(p.team)
        const spread = g ? spreadFor(g, p.team) : null
        return (
          <span key={i} className="flex items-center gap-1">
            {p.Icon ? (
              <p.Icon
                className={`size-3.5 shrink-0 ${POOL_TEXT[p.color]} ${p.Icon === Star ? 'fill-current' : ''}`}
              />
            ) : (
              <span className="size-3.5 shrink-0" />
            )}
            <img src={teamLogo(p.team)} className="size-4 shrink-0" alt="" />
            <span className="font-medium">{p.team}</span>
            <span className="tabular text-xs text-muted-foreground">
              {fmtSpread(spread)}
              {i < pickItems.length - 1 && <span className="hidden sm:inline">,</span>}
            </span>
          </span>
        )
      })}
      {pickItems.length === 0 && <p className="text-muted-foreground">No picks yet.</p>}
    </div>
  )

  const pickExtra = (pool: Pool, value: Special) => {
    setExtras((cur) => ({
      key: weekKey,
      picks: { ...(cur.key === weekKey ? cur.picks : {}), [pool]: value },
    }))
  }

  /**
   * Every dog on the board, biggest first — the payout is the spread itself.
   * `pickers` marks who's actually suggested it, sorted to the front, so a
   * submitted pick like Griffin's is never buried in the full sixteen-team
   * list (#126 follow-up: an earlier round tried filtering this list down to
   * suggested-only, which went to zero every time nobody had suggested
   * anything yet — a sort can't do that, a filter can).
   *
   * Griffin, final call: back to filtering to suggested-only — same rule
   * the main table already lives by (a side nobody suggested isn't a
   * candidate, #127), no fallback to the full schedule. Empty is a real,
   * expected state here, same as an empty promotion table. The spread-sign
   * check (must actually be an underdog) is dropped entirely rather than
   * exempting picked teams from it — sign said the wrong thing for a pick
   * made minutes ago, so it isn't trustworthy enough to gate on here even
   * for unpicked teams; open question, not resolved yet (see notes).
   */
  const dogs = useMemo(() => {
    const pickersFor = (team: string) =>
      picks.filter((p) => p.pick_type === 'underdog' && p.team_picked === team).map((p) => p.picker)
    return games
      .flatMap((g) => [g.away_team, g.home_team].map((t) => ({ game: g, team: t })))
      .map((x) => ({ ...x, spread: spreadFor(x.game, x.team), pickers: pickersFor(x.team) }))
      .filter((x) => x.pickers.length > 0)
      .sort((a, b) => (b.spread ?? 0) - (a.spread ?? 0))
  }, [games, picks])

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

  /** Same suggested-only rule as `dogs`, for survivor. */
  const favourites = useMemo(() => {
    const pickersFor = (team: string) =>
      picks.filter((p) => p.pick_type === 'survivor' && p.team_picked === team).map((p) => p.picker)
    return games
      .flatMap((g) => [g.away_team, g.home_team].map((t) => ({ game: g, team: t })))
      .map((x) => ({ ...x, spread: spreadFor(x.game, x.team), pickers: pickersFor(x.team) }))
      .filter((x) => x.pickers.length > 0)
      .sort((a, b) => (a.spread ?? 0) - (b.spread ?? 0))
  }, [games, picks])

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
    // "No Homers" is TEAM's own entry under another name — it has nothing to
    // submit here, so it never belongs on a list of humans still owing us a
    // slate.
    (p) => isVoter(p) && p !== 'No Homers' && !pickers.includes(p),
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
  const mineTally = useMemo(() => {
    const t: SlotTally = { bb: 0, regular: 0, mnf: 0, underdog: 0, survivor: 0 }
    for (const p of mine) {
      if (p.pick_type === 'best_bet') t.bb++
      else if (p.pick_type === 'regular') t.regular++
      else if (p.pick_type === 'mnf') t.mnf++
      else if (p.pick_type === 'underdog') t.underdog++
      else if (p.pick_type === 'survivor') t.survivor++
    }
    return t
  }, [mine])
  const mineShortfall = shortfall(mineTally)
  const mineComplete = mine.length > 0 && isComplete(mineTally)

  const teamSubmittedAt = useMemo(() => {
    const rows = picks.filter((p) => p.picker === TEAM_PICKER)
    if (!rows.length) return undefined
    return rows.map((p) => p.submitted_at).find(Boolean) ?? null
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

      {/* Your own week, before the room's. Separate card so it stays visible
          even when the board below has nothing yet (#135). */}
      {signedIn && (
        <section className="rounded-lg border border-border bg-card p-3">
          <h2 className="text-sm font-bold">My Picks</h2>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            {mine.length > 0 && (
              <p className="text-sm text-muted-foreground">
                {mineComplete
                  ? `Submitted ${mine[0]?.submitted_at ? fmtWhen(mine[0].submitted_at) : 'at an unknown time'}.`
                  : `${mineShortfall.join(', ')} still open.`}
              </p>
            )}
            {/* Natural width, not full width — a button sized to its label
                reads as a control, not a banner. */}
            <Button asChild size="sm">
              {/* Carries the week the board is on — the Picks page has no
                  selector of its own, so this link is the only way to reach
                  one (#126 follow-up). */}
              <Link to={`/picks/${season}/week/${week}/submit`}>
                {mine.length === 0
                  ? 'Make My Picks'
                  : mineComplete
                    ? 'Edit My Picks'
                    : 'Finish My Picks'}
              </Link>
            </Button>
          </div>
        </section>
      )}

      <section className="rounded-lg border border-border bg-card p-3">
        <h2 className="mb-3 text-sm font-bold">Team Picks</h2>

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
                  <Slot label="Best Bet" color="bb" have={counts.bb} need={1} />
                  <Slot label="Regular" color="pick" have={counts.regular} need={MAX_REGULAR} />
                  <Slot label="MNF" color="mnf" have={counts.mnf} need={1} />
                  <Slot label="Dog" color="underdog" have={underdog ? 1 : 0} need={1} />
                  <Slot label="Survivor" color="survivor" have={survivor ? 1 : 0} need={1} />
                </>
              }
              detail={pickDetail}
              status={copyStatus}
            >
              <CopyButton onClick={copySummary} disabled={!summary} />
              <EditLinesButton editing={editingLines} onClick={() => setEditingLines((v) => !v)} />
              <ClearButton onClick={clearSlate} disabled={isEmpty} />
              <Button
                size="sm"
                onClick={() => setGateOpen(true)}
                disabled={saving || unexplained.length > 0 || gateOpen}
              >
                {saving ? 'Saving…' : 'Submit As TEAM'}
              </Button>
            </ActionBar>

            {/* The gate (#129). TEAM is the entry that came last in 2025 while
                agreeing with the room on 82 of 83 games, so submitting it costs
                a sentence typed on purpose. */}
            {gateOpen && (
              <div className="rounded-lg border border-bb bg-bb-soft/40 p-3">
                <h2 className="text-sm font-bold">Submit as TEAM</h2>
                {teamSubmittedAt !== undefined && (
                  <p className="mt-1 text-sm text-loss">
                    {teamSubmittedAt
                      ? `TEAM was submitted at ${fmtWhen(teamSubmittedAt)}.`
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
                guardrail. Say why in the note on that side before submitting.
              </p>
            )}

            {saved?.key === weekKey && <p className="text-sm text-win">{saved.msg}</p>}

            {teamSubmittedAt !== undefined && !gateOpen && (
              <p className="text-xs text-muted-foreground">
                {teamSubmittedAt
                  ? `TEAM submitted at ${fmtWhen(teamSubmittedAt)}.`
                  : `TEAM submitted for week ${week}.`}
              </p>
            )}

            {editingLines && (
              <LinesEditor
                games={games}
                season={season}
                week={week}
                onSaved={() => {
                  setLinesVersion((v) => v + 1)
                  setEditingLines(false)
                }}
              />
            )}

            {missing.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground">
                No picks in yet from
                {missing.map((p) => (
                  <NamePill key={p} name={p} />
                ))}
              </div>
            )}
            {incomplete.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground">
                Still short:
                {incomplete.map((p) => (
                  <NamePill key={p} name={p} />
                ))}
              </div>
            )}

            {/* The promotion table (#127). Header row on a laptop; on a phone
                the columns speak for themselves and the header is dead height. */}
            <div className="overflow-hidden rounded-lg border border-border bg-card">
              <div className="hidden grid-cols-[minmax(0,20rem)_1fr_3.5rem_2rem_3.5rem_4rem_7rem] items-center gap-2 border-b border-border px-3 py-1.5 text-sm font-semibold text-muted-foreground sm:grid">
                <span>Side</span>
                <span>Pickers</span>
                <SortableHead label="Pts" sortKey="pts" sort={tableSort} onSort={toggleTableSort} width="w-14">
                  <Info text="Pool points this side carries: a best bet is worth two, everything else one." />
                </SortableHead>
                <SortableHead label="BB" sortKey="bb" sort={tableSort} onSort={toggleTableSort} width="w-8" />
                <SortableHead
                  label="Net"
                  sortKey="net"
                  sort={tableSort}
                  onSort={toggleTableSort}
                  width="w-14"
                  className="hidden md:flex"
                >
                  <Info text="Points this side has over the other, weighted the way the pool scores." />
                </SortableHead>
                <SortableHead label="Score" sortKey="score" sort={tableSort} onSort={toggleTableSort} width="w-16">
                  <Info text="0-10, best first. 5.0 is break-even at -110; tap a score for the breakdown." />
                </SortableHead>
                <span className="w-28 text-center">Promote</span>
              </div>
              {sortedCandidates.map((c) => {
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

            {/* Its own section, not a row in the table above — forced onto
                one game, so ranking it against the rest (or letting the
                table's sort move it around) doesn't mean anything. */}
            {mnfCandidates.length > 0 && (
              <div className="overflow-hidden rounded-lg border border-border bg-card">
                <h2 className="flex items-center gap-1.5 px-3 pt-2 text-sm font-bold">
                  <Moon className="size-4" /> Monday Night
                </h2>
                <div className="divide-y divide-border">
                  {mnfCandidates.map((c) => {
                    const chosen = slate[c.row.game.game_id]
                    return (
                      <CandidateRow
                        key={`${c.row.game.game_id}_${c.team}`}
                        c={c}
                        blocs={blocs}
                        slot={chosen?.team === c.team ? chosen.type : null}
                        locked={false}
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
              </div>
            )}

            <PoolPicker
              title="Underdog"
              icon={Dog}
              color="underdog"
              options={dogs}
              chosen={underdog}
              onPick={(v) => pickExtra('underdog', v)}
            />

            <PoolPicker
              title="Survivor"
              icon={Skull}
              color="survivor"
              options={favourites.map((f) => ({ ...f, disabled: spent.has(f.team) }))}
              chosen={survivor}
              onPick={(v) => pickExtra('survivor', v)}
            />

            <div className="rounded-lg border border-border bg-card p-3">
              <h2 className="mb-2 flex items-center gap-1.5 text-sm font-bold">
                Where we lose
                <Info text="Rules fitted from our own pick record, refit on every deploy — only shown once a rule clears the field's own rate in most seasons." />
              </h2>
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

            <ActionBarSpacer />
          </TabsContent>

          <TabsContent value="grid">
            <Grid rows={rows} pickers={pickers} />
          </TabsContent>

          <TabsContent value="survivor">
            <Survivor seasonPicks={seasonPicks} week={week} weekPicks={picks} />
          </TabsContent>
        </Tabs>
        )}
      </section>
    </div>
  )
}

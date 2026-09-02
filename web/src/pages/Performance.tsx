import { useEffect, useMemo, useState } from 'react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../api'
import { useConfig, useGuardrails, useSeasonWeek } from '../hooks'
import type { LedgerResponse, PickerStanding, RecordStats, StandingsResponse } from '../types'
import { BREAK_EVEN, TEAM_2025, TEAM_PICKER } from '@/lib/consensus'
import PageHeader from '@/components/PageHeader'
import { EmptyState, ErrorNote, Loading } from '@/components/PageState'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

/**
 * How the room is doing, in the pool's own units (#132).
 *
 * Standings, Ledger and the Team page all answered the same question in three
 * different currencies, on three tabs. Units at -110 was the headline on one of
 * them, and nobody in this pool bets a unit: the pool pays 2 for a best bet, 1
 * for a regular, 1 for the Monday game, half for a push. So the headline is
 * that, and units survives as a muted column so nobody thinks a number went
 * missing.
 *
 * The rule for everything on this page: no table that cannot state, in one line
 * above it, what a reader should do differently after reading it.
 */

/** Pool points a slot is worth (notes/SCORING.md). */
const WEIGHT: Record<string, number> = { best_bet: 2, regular: 1, mnf: 1 }

type Weighted = { points: number; available: number; pct: number | null; lost: number }

/**
 * The headline. A push is half, so it lands in both halves of the fraction and
 * pulls a record toward 50% rather than out of it.
 */
function weigh(byType: Record<string, RecordStats>): Weighted {
  let points = 0
  let available = 0
  for (const [type, w] of Object.entries(WEIGHT)) {
    const r = byType[type]
    if (!r) continue
    points += w * (r.wins + r.pushes / 2)
    available += w * (r.wins + r.losses + r.pushes)
  }
  return {
    points,
    available,
    lost: available - points,
    pct: available > 0 ? points / available : null,
  }
}

const fmtPct = (p: number | null) => (p === null ? '—' : `${(p * 100).toFixed(1)}%`)
const fmtUnits = (u: number) => `${u > 0 ? '+' : ''}${u.toFixed(2)}`
const fmtRecord = (r: RecordStats | undefined) =>
  r ? `${r.wins}-${r.losses}${r.pushes ? `-${r.pushes}` : ''}` : '—'

/** Whole numbers stay whole; a half point shows its half. */
const fmtPoints = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1))

/**
 * Standings, ordered by what the pool pays.
 *
 * The weighted record reads points won against points lost, with the best bet
 * carrying two and the Monday game in it — which is the entry as the pool
 * scores it, not as a bookmaker would.
 */
function Standings({ rows }: { rows: { s: PickerStanding; w: Weighted }[] }) {
  return (
    <section>
      <h2 className="text-sm font-bold">Standings</h2>
      <p className="mb-2 text-xs text-muted-foreground">
        Weighted for the pool: best bet 2, regular 1, MNF 1, a push a half. If you are
        below {fmtPct(BREAK_EVEN / 100)} you are paying for the privilege.
      </p>
      <div className="overflow-x-auto rounded-lg border border-border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Picker</TableHead>
              <TableHead className="text-right">Points</TableHead>
              <TableHead className="text-right">Weighted</TableHead>
              <TableHead className="text-right text-muted-foreground">ATS</TableHead>
              <TableHead className="text-right text-muted-foreground">Units</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map(({ s, w }) => (
              <TableRow key={s.picker}>
                <TableCell
                  className={s.picker === TEAM_PICKER ? 'font-bold text-loss' : 'font-semibold'}
                >
                  {s.picker}
                </TableCell>
                <TableCell className="tabular text-right">
                  {fmtPoints(w.points)}-{fmtPoints(w.lost)}
                </TableCell>
                <TableCell
                  className={`tabular text-right font-medium ${
                    w.pct === null
                      ? ''
                      : w.pct * 100 >= BREAK_EVEN
                        ? 'text-win'
                        : 'text-loss'
                  }`}
                >
                  {fmtPct(w.pct)}
                </TableCell>
                <TableCell className="tabular text-right text-muted-foreground">
                  {fmtRecord(s.ats)}
                </TableCell>
                <TableCell className="tabular text-right text-muted-foreground">
                  {fmtUnits(s.units)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
  )
}

const BENCHMARKS = ['Majority', 'Best member', 'No Homers']

const colour = (entry: string) =>
  entry === TEAM_PICKER
    ? 'var(--loss)'
    : BENCHMARKS.includes(entry)
      ? 'var(--primary)'
      : 'var(--muted-foreground)'

/**
 * The one chart that answers whether the Sunday call is worth holding.
 *
 * Two independent sources say the weekly call costs about 1.5 points of hit
 * rate against the members who sit on it. Run live, a losing process shows up
 * in week 8 rather than in April.
 */
function TeamChart({ data }: { data: LedgerResponse }) {
  const series = useMemo(() => {
    const byWeek = new Map<number, Record<string, number>>()
    for (const w of data.weeks) {
      const row = byWeek.get(w.week) ?? { week: w.week }
      row[w.entry] = w.running
      byWeek.set(w.week, row)
    }
    return [...byWeek.values()].sort((a, b) => a.week - b.week)
  }, [data])

  const drawn = useMemo(() => {
    const named = data.standings.map((s) => s.entry)
    return [TEAM_PICKER, ...BENCHMARKS, ...named.filter((n) => n !== TEAM_PICKER && !BENCHMARKS.includes(n))]
      .filter((n) => named.includes(n))
  }, [data])

  if (series.length < 2) return null

  return (
    <section>
      <h2 className="text-sm font-bold">TEAM against what it could have submitted</h2>
      <p className="mb-2 text-xs text-muted-foreground">
        If TEAM keeps losing to Majority, that is the finding, and the process should
        change mid-season. <b>Best member</b> follows whoever led going into that week,
        never the one who turned out to be right.
      </p>
      <div className="h-72 w-full rounded-lg border border-border bg-card p-3">
        <ResponsiveContainer>
          <LineChart data={series} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="week"
              tickLine={false}
              axisLine={false}
              tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
            />
            <Tooltip
              contentStyle={{
                background: 'var(--card)',
                border: '1px solid var(--border)',
                borderRadius: 8,
                fontSize: 12,
              }}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            {drawn.map((entry) => (
              <Line
                key={entry}
                type="monotone"
                dataKey={entry}
                stroke={colour(entry)}
                strokeWidth={entry === TEAM_PICKER || BENCHMARKS.includes(entry) ? 2 : 1}
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}

/**
 * The two side pools, on their own scoring.
 *
 * Neither enters weighted ATS: the dog pays its spread only on an outright win
 * and survivor is a season-long allocation, so mixing either into a hit rate
 * makes both numbers mean nothing.
 */
function SidePools({ rows }: { rows: PickerStanding[] }) {
  const panel = (type: 'underdog' | 'survivor', title: string, hint: string) => {
    const entries = rows
      .map((s) => ({ picker: s.picker, rec: s.by_type[type] }))
      .filter((e) => e.rec && e.rec.wins + e.rec.losses > 0)
      .sort((a, b) => (b.rec?.wins ?? 0) - (a.rec?.wins ?? 0))
    return (
      <div className="flex-1 rounded-lg border border-border bg-card p-3">
        <h3 className="text-sm font-bold">{title}</h3>
        <p className="mb-2 text-xs text-muted-foreground">{hint}</p>
        {entries.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing graded yet.</p>
        ) : (
          <div className="flex flex-col gap-1">
            {entries.map((e) => (
              <div key={e.picker} className="flex items-center gap-2 text-sm">
                <span className="w-20 shrink-0 font-semibold">{e.picker}</span>
                <span className="tabular text-muted-foreground">{fmtRecord(e.rec)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  return (
    <section className="flex flex-col gap-3 sm:flex-row">
      {panel('underdog', 'Underdog', 'One dog a week. It pays its spread outright or nothing.')}
      {panel('survivor', 'Survivor', 'One team a week, spent for the season. Wrong once and it is over.')}
    </section>
  )
}

/**
 * What the record says, as sentences (#132).
 *
 * The Analytics cuts tables rendered a per-key breakdown of everything, and
 * notes/pick-analytics.md found almost nothing survives clustering, so they
 * were mostly noise with a table's authority. The findings that did survive
 * are four sentences, and the rates come from GET /api/guardrails so they
 * cannot go stale in the way a number typed into TypeScript does.
 */
function Findings({ season }: { season: number }) {
  const { guardrails } = useGuardrails(season, null)
  return (
    <section>
      <h2 className="text-sm font-bold">What the record says</h2>
      <p className="mb-2 text-xs text-muted-foreground">
        Refit from our own picks on every deploy. A rule appears here only once it is
        below the field&apos;s own rate, and below it in most seasons.
      </p>
      <ul className="flex list-disc flex-col gap-2 pl-5 text-sm">
        <li>
          The weekly call came <b>last</b> in {2025}. TEAM took {TEAM_2025.rate}% of
          available pool points while following the room&apos;s majority on{' '}
          {TEAM_2025.rubberStamp} games, and {TEAM_2025.best} took {TEAM_2025.bestRate}%.
          Averaging is what loses.
        </li>
        <li>
          The games worth the call&apos;s time are the ones the room has <b>not</b>{' '}
          settled. Unanimous games went 45.2% in 2025; contested ones went{' '}
          {BREAK_EVEN}%, which is break-even and no better.
        </li>
        {(guardrails?.rules ?? []).map((r) => (
          <li key={r.id}>
            {r.label} has hit <b className="text-loss">{(r.pct * 100).toFixed(1)}%</b>{' '}
            against {(r.base_pct * 100).toFixed(1)}% for everything else we pick, over{' '}
            {r.games.toFixed(0)} games
            {r.advisory ? ', though not stably enough to veto on' : ''}.
          </li>
        ))}
        {!guardrails?.rules.length && (
          <li className="text-muted-foreground">No rule currently clears the bar.</li>
        )}
      </ul>
    </section>
  )
}

export default function Performance() {
  const { config, error: configError } = useConfig()
  const { season, setSeason, seasons } = useSeasonWeek(config)
  const [standings, setStandings] = useState<StandingsResponse | null>(null)
  const [ledger, setLedger] = useState<LedgerResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (season === null) return
    let live = true
    api
      .standings(season)
      .then((d) => live && setStandings(d))
      .catch((e) => live && setError(String(e)))
    // The ledger is the second half of the same question, so a failure there
    // must not take the standings down with it.
    api
      .ledger(season)
      .then((d) => live && setLedger(d))
      .catch(() => live && setLedger(null))
    return () => {
      live = false
    }
  }, [season])

  const ranked = useMemo(() => {
    if (!standings) return []
    return standings.standings
      .map((s) => ({ s, w: weigh(s.by_type) }))
      .sort((a, b) => (b.w.pct ?? -1) - (a.w.pct ?? -1) || b.w.points - a.w.points)
  }, [standings])

  if (configError) return <ErrorNote>Failed to load config: {configError}</ErrorNote>
  if (!config || season === null) return <Loading />

  const stale = !error && standings?.season !== season
  const empty = !error && standings?.season === season && standings.standings.length === 0

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Performance" season={season} seasons={seasons} onSeason={setSeason} />

      {standings?.graded_through_week != null && (
        <p className="-mt-4 text-sm text-muted-foreground">
          Graded through week {standings.graded_through_week}.
        </p>
      )}

      {(error || empty) && (
        <EmptyState
          title="Nothing graded yet"
          detail={`Standings appear once results are loaded for ${season}.`}
          note={error}
        />
      )}
      {stale && !error && <Loading />}

      {!error && !empty && standings?.season === season && (
        <>
          <Standings rows={ranked} />
          {ledger?.season === season && <TeamChart data={ledger} />}
          <SidePools rows={standings.standings} />
          <Findings season={season} />
        </>
      )}
    </div>
  )
}

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
import { useConfig, useSeasonWeek } from '../hooks'
import type { LedgerResponse } from '../types'
import PageHeader from '@/components/PageHeader'
import { ErrorNote, Loading } from '@/components/PageState'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

/** The three entries that exist to be beaten, drawn heavier than the people. */
const BENCHMARKS = ['Majority', 'Best member', 'No Homers']
const TEAM = 'TEAM'

const colour = (entry: string) =>
  entry === TEAM
    ? 'var(--loss)'
    : BENCHMARKS.includes(entry)
      ? 'var(--primary)'
      : 'var(--muted-foreground)'

/**
 * What the weekly call is worth (#58).
 *
 * Two independent sources say it costs about 1.5 points of hit rate against the
 * members who sit on it. This is that comparison, live and in pool points, so a
 * losing process shows up in week 8 rather than in April.
 */
export default function Ledger() {
  const { config, error: configError } = useConfig()
  const { season, setSeason, seasons } = useSeasonWeek(config)
  const [data, setData] = useState<LedgerResponse | null>(null)
  const stale = data !== null && data.season !== season
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (season === null) return
    let live = true
    // The season is in the key, so a stale table is replaced when the new one
    // lands rather than blanked synchronously from inside the effect.
    api
      .ledger(season)
      .then((r) => live && setData(r))
      .catch((e) => live && setError(String(e)))
    return () => {
      live = false
    }
  }, [season])

  // One row per week, one column per entry, so the lines share an x axis.
  const series = useMemo(() => {
    if (!data) return []
    const byWeek = new Map<number, Record<string, number>>()
    for (const w of data.weeks) {
      const row = byWeek.get(w.week) ?? { week: w.week }
      row[w.entry] = w.running
      byWeek.set(w.week, row)
    }
    return [...byWeek.values()].sort((a, b) => a.week - b.week)
  }, [data])

  const drawn = useMemo(() => {
    if (!data) return []
    const named = data.standings.map((s) => s.entry)
    return [TEAM, ...BENCHMARKS, ...named.filter((n) => n !== TEAM && !BENCHMARKS.includes(n))]
      .filter((n) => named.includes(n))
  }, [data])

  if (configError) return <ErrorNote>Failed to load config: {configError}</ErrorNote>
  if (error) return <ErrorNote>{error}</ErrorNote>
  if (!config || season === null) return <Loading />

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Ledger" season={season} seasons={seasons} onSeason={setSeason} />

      <p className="text-xs text-muted-foreground">
        Pool points only: best bet 2, regular 1, MNF 1, a push a half. Underdog and survivor
        are separate pools with different objectives, so they are not in this number.{' '}
        <b>Best member</b> follows whoever led going into that week, never the one who turned
        out to be right.
      </p>

      {!data || stale ? (
        <Loading />
      ) : !data.standings.length ? (
        <p className="rounded-md border border-border bg-card px-3 py-2 text-sm text-muted-foreground">
          Nothing graded yet for {season}.
        </p>
      ) : (
        <>
          <div className="rounded-lg border border-border bg-card overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Entry</TableHead>
                  <TableHead className="text-right">Points</TableHead>
                  <TableHead className="text-right">Available</TableHead>
                  <TableHead className="text-right">Share</TableHead>
                  <TableHead className="text-right">Weeks</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.standings.map((s) => (
                  <TableRow key={s.entry}>
                    <TableCell
                      className={
                        s.entry === TEAM
                          ? 'font-bold text-loss'
                          : BENCHMARKS.includes(s.entry)
                            ? 'font-semibold text-primary'
                            : ''
                      }
                    >
                      {s.entry}
                    </TableCell>
                    <TableCell className="tabular text-right">{s.points.toFixed(1)}</TableCell>
                    <TableCell className="tabular text-right text-muted-foreground">
                      {s.available.toFixed(0)}
                    </TableCell>
                    <TableCell className="tabular text-right">
                      {s.share === null ? '—' : `${(s.share * 100).toFixed(1)}%`}
                    </TableCell>
                    <TableCell className="tabular text-right text-muted-foreground">
                      {s.weeks}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

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
                    strokeWidth={entry === TEAM || BENCHMARKS.includes(entry) ? 2 : 1}
                    dot={false}
                    isAnimationActive={false}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>

          <p className="text-xs text-muted-foreground">
            If TEAM keeps losing to Majority, that is the finding, and the process should
            change mid-season rather than at the end of it.
          </p>
        </>
      )}
    </div>
  )
}

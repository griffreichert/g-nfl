import { useEffect, useMemo, useState } from 'react'
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../api'
import { useConfig, useSeasonWeek } from '../hooks'
import type { PickerStanding, StandingsResponse } from '../types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

const CHART_COLORS = [
  'var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)',
  'var(--chart-4)', 'var(--chart-5)',
]

const fmtPct = (p: number | null) => (p === null ? '—' : `${(p * 100).toFixed(1)}%`)
const fmtUnits = (u: number) => `${u > 0 ? '+' : ''}${u.toFixed(2)}`
const fmtRecord = (r: { wins: number; losses: number; pushes: number }) =>
  `${r.wins}-${r.losses}${r.pushes ? `-${r.pushes}` : ''}`

/** Cumulative units by week, one line per picker, zero line dashed */
function TrendChart({ standings }: { standings: PickerStanding[] }) {
  const series = standings.filter((s) => s.weekly.length > 0)
  const { rows, weeks } = useMemo(() => {
    const byWeek = new Map<number, Record<string, number>>()
    for (const s of series) {
      for (const w of s.weekly) {
        const row = byWeek.get(w.week) ?? { week: w.week }
        row[s.picker] = w.cum_units
        byWeek.set(w.week, row)
      }
    }
    return {
      rows: [...byWeek.values()].sort((a, b) => a.week - b.week),
      weeks: byWeek.size,
    }
  }, [series])

  if (series.length === 0 || weeks < 2) return null

  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle className="text-sm">Cumulative units by week (1u per pick at -110)</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis
              dataKey="week"
              tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
              stroke="var(--border)"
            />
            <YAxis
              tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
              stroke="var(--border)"
              width={44}
            />
            <ReferenceLine y={0} stroke="var(--muted-foreground)" strokeDasharray="4 3" />
            <Tooltip
              contentStyle={{
                background: 'var(--popover)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius)',
                color: 'var(--popover-foreground)',
                fontSize: 12,
              }}
              formatter={(v) => fmtUnits(Number(v))}
              labelFormatter={(w) => `Week ${w}`}
            />
            {series.map((s, i) => (
              <Line
                key={s.picker}
                type="monotone"
                dataKey={s.picker}
                stroke={CHART_COLORS[i % CHART_COLORS.length]}
                // 8 pickers, 5 colours: on the second lap of the palette the
                // line goes dashed so two people are never the same blue.
                strokeDasharray={i >= CHART_COLORS.length ? '5 3' : undefined}
                strokeWidth={2}
                dot={false}
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
        <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1 text-xs">
          {series.map((s, i) => (
            <span key={s.picker} className="flex items-center gap-1">
              <span
                className="inline-block h-0.5 w-3"
                style={
                  i >= CHART_COLORS.length
                    ? {
                        backgroundImage: `repeating-linear-gradient(to right, ${CHART_COLORS[i % CHART_COLORS.length]} 0 4px, transparent 4px 7px)`,
                      }
                    : { background: CHART_COLORS[i % CHART_COLORS.length] }
                }
              />
              {s.picker}
            </span>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

const col = createColumnHelper<PickerStanding>()

function StandingsTable({ standings, breakEven }: { standings: PickerStanding[]; breakEven: number }) {
  const columns = useMemo(
    () => [
      col.accessor('picker', {
        header: 'Picker',
        cell: (c) => <span className="font-bold">{c.getValue()}</span>,
      }),
      col.accessor('ats', {
        header: 'ATS',
        cell: (c) => {
          const ats = c.getValue()
          return (
            <span className="tabular">
              {fmtRecord(ats)}
              {ats.pending > 0 && <span className="text-muted-foreground"> ({ats.pending} pend)</span>}
            </span>
          )
        },
      }),
      col.accessor((r) => r.ats.win_pct, {
        id: 'win_pct',
        header: 'Win%',
        cell: (c) => {
          const pct = c.getValue()
          return (
            <span
              className={`tabular ${pct !== null ? (pct > breakEven ? 'text-win' : 'text-loss') : ''}`}
            >
              {fmtPct(pct)}
            </span>
          )
        },
      }),
      col.accessor('units', {
        header: 'Units',
        cell: (c) => {
          const u = c.getValue()
          return (
            <span
              className={`tabular font-medium ${u > 0 ? 'text-win' : u < 0 ? 'text-loss' : ''}`}
            >
              {fmtUnits(u)}
            </span>
          )
        },
      }),
      ...(
        [
          ['best_bet', 'Best bet'],
          ['survivor', 'Survivor'],
          ['underdog', 'Dog'],
          ['mnf', 'MNF'],
        ] as const
      ).map(([type, header]) =>
        col.accessor((r) => r.by_type[type], {
          id: type,
          header,
          cell: (c) => {
            const rec = c.getValue()
            return <span className="tabular text-muted-foreground">{rec ? fmtRecord(rec) : '—'}</span>
          },
        }),
      ),
    ],
    [breakEven],
  )

  const table = useReactTable({ data: standings, columns, getCoreRowModel: getCoreRowModel() })

  return (
    <div className="bg-card rounded-lg border border-border overflow-x-auto">
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((group) => (
            <TableRow key={group.id}>
              {group.headers.map((header) => (
                <TableHead key={header.id}>
                  {flexRender(header.column.columnDef.header, header.getContext())}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows.map((row) => (
            <TableRow key={row.id}>
              {row.getVisibleCells().map((cell) => (
                <TableCell key={cell.id}>
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

export default function Standings() {
  const { config, error: configError } = useConfig()
  const { season, setSeason, seasons } = useSeasonWeek(config)
  const [data, setData] = useState<StandingsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (season === null) return
    let cancelled = false
    api
      .standings(season)
      .then((d) => {
        if (cancelled) return
        setData(d)
        setError(null)
      })
      .catch((e) => {
        if (!cancelled) setError(String(e))
      })
    return () => {
      cancelled = true
    }
  }, [season])

  if (configError) return <p className="text-destructive">Failed to load config: {configError}</p>
  if (!config || season === null) return <p>Loading…</p>

  const breakEven = data ? data.break_even_pct : 110 / 210

  const empty = !error && data?.season === season && data.standings.length === 0

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-xl font-bold sm:text-2xl">Standings</h1>
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
      </div>

      {data?.graded_through_week != null && (
        <p className="text-sm text-muted-foreground">
          Results through week {data.graded_through_week}.
        </p>
      )}

      {/* Results live in a table the backend may not have yet (#65). An empty
          board is the honest answer, not a stack trace. */}
      {(error || empty) && (
        <div className="rounded-lg border border-border bg-card p-6 text-center">
          <p className="font-medium">No graded results yet</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Standings appear once game results are loaded for {season}.
          </p>
          {error && <p className="mt-3 text-xs text-muted-foreground">{error}</p>}
        </div>
      )}
      {!error && !data && <p className="text-muted-foreground">Loading…</p>}
      {!error && data && data.season !== season && (
        <p className="text-muted-foreground">Loading…</p>
      )}

      {!error && !empty && data?.season === season && (
        <>
          <TrendChart standings={data.standings} />
          <StandingsTable standings={data.standings} breakEven={breakEven} />

          <p className="text-xs text-muted-foreground mt-2">
            ATS record covers regular + best bet picks, graded against the line at pick time.
            Break-even at -110 is {fmtPct(breakEven)}. Pushes excluded from win%.
          </p>
        </>
      )}
    </div>
  )
}

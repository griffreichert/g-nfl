import { useEffect, useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  Cell as BarCell,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from 'recharts'
import { api, teamLogo } from '../api'
import { useConfig, useSeasonRoute } from '../hooks'
import type { AnalyticsResponse, Cut, CutRow, TeamAppetite } from '../types'
import {
  cutHasSignal,
  fmtPct,
  fmtUnits,
  isFlat,
  isHabit,
  sortTeams,
  type TeamSortKey,
} from '@/lib/analytics'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import PageHeader from '@/components/PageHeader'
import { EmptyState, ErrorNote, Loading } from '@/components/PageState'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

/** Cut keys come off the backend as raw group values. Only slots need help. */
const prettyKey = (k: string) =>
  ({ best_bet: 'Best bet', regular: 'Regular', mnf: 'MNF' })[k] ?? k

const fmtZ = (z: number | null) => (z === null ? '—' : `${z > 0 ? '+' : ''}${z.toFixed(2)}`)

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="tabular text-lg font-semibold">{value}</dd>
    </div>
  )
}

/**
 * The sample, stated before anything is drawn from it. The gap between picks
 * and games is the whole reason this page exists: an earlier cut of the same
 * record counted picks, inflated every rate, and shipped into the pick board.
 */
function Sample({ d }: { d: AnalyticsResponse }) {
  const gap = (d.break_even_pct - d.base_pct) * 100
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">The sample</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <Stat label="Picks" value={String(d.picks)} />
          <Stat label="Distinct games" value={String(d.games)} />
          <Stat label="Votes / game" value={d.votes_per_game.toFixed(2)} />
          <Stat label="Field, per game" value={fmtPct(d.base_pct)} />
          <Stat label="Break-even at -110" value={fmtPct(d.break_even_pct)} />
        </dl>
        <p className="text-sm text-muted-foreground">
          {d.picks} picks land on {d.games} distinct games — {d.votes_per_game} votes each — so a
          per-pick rate counts the average game three times over. Every rate below is per game: a
          game the room split 4-2 counts once, as 0.667. On that denominator the field hits{' '}
          {fmtPct(d.base_pct)}, {gap.toFixed(1)} points under the {fmtPct(d.break_even_pct)} a -110
          bet needs. The room is under water overall, and no cut below turns that around.
        </p>
        <p className="text-sm text-muted-foreground">
          Shrunk rates pull each cell toward {fmtPct(d.base_pct)} by its own sample size. Where a
          split carries no more spread than binomial noise, every cell shrinks all the way onto the
          base rate — those rows are marked and are not findings.
        </p>
      </CardContent>
    </Card>
  )
}

/**
 * One cut as bars, with both lines that matter drawn on it: the field's own
 * rate and break-even. A bar above the field but below break-even is still a
 * losing cell, which is easy to forget when only one line is on the chart.
 */
function CutChart({
  rows,
  base,
  breakEven,
}: {
  rows: CutRow[]
  base: number
  breakEven: number
}) {
  const data = rows.map((r) => ({
    key: prettyKey(r.key),
    pct: (r.pct ?? 0) * 100,
    good: (r.pct ?? 0) >= breakEven,
  }))
  const lo = Math.min(...data.map((d) => d.pct), base * 100) - 8
  const hi = Math.max(...data.map((d) => d.pct), breakEven * 100) + 8

  return (
    <div className="h-44 w-full">
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 16, right: 8, bottom: 0, left: -24 }}>
          <XAxis
            dataKey="key"
            tickLine={false}
            axisLine={false}
            interval={0}
            tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
          />
          <YAxis
            domain={[Math.max(0, lo), Math.min(100, hi)]}
            tickLine={false}
            axisLine={false}
            tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
            tickFormatter={(v) => `${Math.round(Number(v))}%`}
          />
          {/* The two lines sit ~5 points apart, so inline labels collide.
              They are named in the legend under the chart instead. */}
          <ReferenceLine y={base * 100} stroke="var(--muted-foreground)" strokeDasharray="2 3" />
          <ReferenceLine y={breakEven * 100} stroke="var(--foreground)" strokeDasharray="5 3" />
          <Bar dataKey="pct" radius={[4, 4, 0, 0]} maxBarSize={72} isAnimationActive={false}>
            {data.map((d) => (
              <BarCell key={d.key} fill={d.good ? 'var(--win)' : 'var(--loss)'} />
            ))}
            <LabelList
              dataKey="pct"
              position="top"
              formatter={(v) => `${Number(v).toFixed(1)}%`}
              fill="var(--foreground)"
              fontSize={11}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function CutSection({
  cut,
  base,
  breakEven,
}: {
  cut: Cut
  base: number
  breakEven: number
}) {
  const signal = cutHasSignal(cut.rows, base)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
          {cut.label}
          {!signal && (
            <Badge variant="outline" className="text-muted-foreground">
              no signal
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-xs text-muted-foreground">{cut.note}</p>

        {/* A chart of cells that all shrank onto the base rate would draw six
            bars of pure noise, so cuts with nothing in them get the table only. */}
        {signal && <CutChart rows={cut.rows} base={base} breakEven={breakEven} />}

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{cut.label}</TableHead>
              <TableHead className="text-right" title="distinct games, votes collapsed">
                Games
              </TableHead>
              <TableHead className="text-right" title="wins per game, the honest rate">
                Per game
              </TableHead>
              <TableHead className="text-right" title="pulled toward the field's rate by sample size">
                Shrunk
              </TableHead>
              <TableHead className="text-right" title="per pick — counts one game as many, kept only so the inflation is visible">
                Naive
              </TableHead>
              <TableHead className="text-right">Units</TableHead>
              <TableHead className="text-right" title="standard deviations from break-even, on the clustered denominator">
                z
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {cut.rows.map((r) => {
              const flat = isFlat(r, base)
              return (
                <TableRow key={r.key} className={flat ? 'text-muted-foreground' : undefined}>
                  <TableCell className="font-medium whitespace-nowrap">{prettyKey(r.key)}</TableCell>
                  <TableCell className="tabular text-right">
                    {r.games}
                    <span className="text-muted-foreground"> / {r.picks}</span>
                  </TableCell>
                  <TableCell
                    className={`tabular text-right font-semibold ${
                      flat ? '' : (r.pct ?? 0) >= breakEven ? 'text-win' : 'text-loss'
                    }`}
                  >
                    {fmtPct(r.pct)}
                  </TableCell>
                  <TableCell className="tabular text-right whitespace-nowrap">
                    {flat ? (
                      <span title="shrank all the way onto the field's own rate — this cell says nothing">
                        {fmtPct(base)} <span className="text-xs">= base</span>
                      </span>
                    ) : (
                      fmtPct(r.shrunk_pct)
                    )}
                  </TableCell>
                  <TableCell
                    className="tabular text-right text-muted-foreground line-through decoration-1"
                    title="naive per-pick rate — not a real rate, shown for contrast"
                  >
                    {fmtPct(r.pick_pct)}
                  </TableCell>
                  <TableCell className="tabular text-right">{fmtUnits(r.units)}</TableCell>
                  <TableCell className="tabular text-right text-muted-foreground">
                    {fmtZ(r.z)}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

const TEAM_COLS: { key: TeamSortKey; label: string; title: string }[] = [
  { key: 'team', label: 'Team', title: 'team' },
  { key: 'appetite', label: 'Appetite', title: "share of a team's games in which someone took them" },
  { key: 'picked_games', label: 'Picked', title: 'games picked / games available' },
  { key: 'picks', label: 'Votes', title: 'total picks across the room' },
  { key: 'pct', label: 'Per game', title: 'hit rate per game' },
  { key: 'units', label: 'Units', title: 'profit at -110 over the actual picks' },
]

function Teams({ teams, base }: { teams: TeamAppetite[]; base: number }) {
  const [sort, setSort] = useState<{ key: TeamSortKey; desc: boolean }>({
    key: 'appetite',
    desc: true,
  })
  const rows = useMemo(() => sortTeams(teams, sort.key, sort.desc), [teams, sort])
  const habits = rows.filter((t) => isHabit(t, base))

  const toggle = (key: TeamSortKey) =>
    // First click on a new column sorts the interesting way: descending for
    // numbers, A-Z for the team code.
    setSort((s) => (s.key === key ? { key, desc: !s.desc } : { key, desc: key !== 'team' }))

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Teams: how often we buy them, and how it went</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-xs text-muted-foreground">
          Highlighted rows: taken in at least half their games and hitting under the field's own{' '}
          {fmtPct(base)}.
        </p>

        {habits.length > 0 && (
          <p className="text-sm">
            <span className="font-medium">Overbought and losing:</span>{' '}
            {habits.map((t) => `${t.team} (${fmtPct(t.pct)})`).join(', ')}
          </p>
        )}

        <Table>
          <TableHeader>
            <TableRow>
              {TEAM_COLS.map((c) => (
                <TableHead
                  key={c.key}
                  title={c.title}
                  aria-sort={sort.key === c.key ? (sort.desc ? 'descending' : 'ascending') : 'none'}
                  className={c.key === 'team' ? '' : 'text-right'}
                >
                  <button
                    type="button"
                    onClick={() => toggle(c.key)}
                    className="cursor-pointer hover:text-foreground"
                  >
                    {c.label}
                    {sort.key === c.key && <span className="ml-1">{sort.desc ? '▾' : '▴'}</span>}
                  </button>
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((t) => (
              <TableRow key={t.team} className={isHabit(t, base) ? 'bg-loss/10' : undefined}>
                <TableCell className="font-medium whitespace-nowrap">
                  <span className="flex items-center gap-1.5">
                    <img src={teamLogo(t.team)} alt="" className="size-5" />
                    {t.team}
                  </span>
                </TableCell>
                <TableCell className="tabular text-right">{fmtPct(t.appetite)}</TableCell>
                <TableCell className="tabular text-right whitespace-nowrap">
                  {t.picked_games}
                  <span className="text-muted-foreground"> / {t.available}</span>
                </TableCell>
                <TableCell className="tabular text-right text-muted-foreground">{t.picks}</TableCell>
                <TableCell className="tabular text-right">{fmtPct(t.pct)}</TableCell>
                <TableCell
                  className={`tabular text-right ${t.units > 0 ? 'text-win' : t.units < 0 ? 'text-loss' : ''}`}
                >
                  {fmtUnits(t.units)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

export default function Analytics() {
  const { config, error: configError } = useConfig()
  const { season, setSeason, seasons } = useSeasonRoute(config, (s) => `/analytics/${s}`)
  const [data, setData] = useState<AnalyticsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (season === null) return
    let cancelled = false
    api
      .analytics(season)
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

  if (configError) return <ErrorNote>Failed to load config: {configError}</ErrorNote>
  if (!config || season === null) return <Loading />

  const ready = data?.season === season

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Analytics"
        season={season}
        seasons={seasons}
        onSeason={setSeason}
      />

      {error && (
        <EmptyState
          title={`Could not load ${season}`}
          detail="Cuts appear once picks and results exist for the season."
          note={error}
        />
      )}

      {/* A season nobody has picked in comes back empty rather than as an
          error, so say so instead of drawing a page of zeroes. */}
      {!error && ready && data && data.picks === 0 && (
        <EmptyState
          title={`Nothing graded for ${season}`}
          detail="Cuts appear once picks and results exist for the season."
        />
      )}

      {!error && !ready && <Loading />}

      {!error && ready && data && data.picks > 0 && (
        <>
          <Sample d={data} />
          {data.cuts.map((c) => (
            <CutSection
              key={c.name}
              cut={c}
              base={data.base_pct}
              breakEven={data.break_even_pct}
            />
          ))}
          <Teams teams={data.teams} base={data.base_pct} />
          <p className="text-xs text-muted-foreground">
            Regular, best bet and MNF picks only, graded against the pool spread where one exists
            and the market line otherwise. TEAM and TEST are excluded: TEAM is the room's own
            average, so counting it would count everyone twice.
          </p>
        </>
      )}
    </div>
  )
}

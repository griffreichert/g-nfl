import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
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
import { api, teamLogo } from '../api'
import { fmtSpread } from '../hooks'
import type { GameDetail, InjuryReport } from '../types'
import {
  epaSeries,
  fmtKickoff,
  groupInjuries,
  hasContext,
  marginLabel,
  sideSpread,
  SLOT_LABEL,
  type EpaPoint,
} from '@/lib/game'
import { Loading } from '@/components/PageState'
import { Info } from '@/components/Info'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

const AWAY_COLOR = 'var(--chart-1)'
const HOME_COLOR = 'var(--chart-3)'

/** Green and red only ever mean graded. Everything else stays neutral. */
const OUTCOME: Record<string, { label: string; className: string }> = {
  win: { label: 'Win', className: 'text-win' },
  loss: { label: 'Loss', className: 'text-loss' },
  push: { label: 'Push', className: 'text-muted-foreground' },
  pending: { label: 'Pending', className: 'text-muted-foreground' },
  no_spread: { label: 'No line', className: 'text-muted-foreground' },
}

function Side({
  team,
  spread,
  score,
  label,
}: {
  team: string
  spread: number | null
  score: number | null
  label: string
}) {
  return (
    <div className="flex flex-1 flex-col items-center gap-1 text-center">
      <img src={teamLogo(team)} className="size-10 sm:size-14" alt="" />
      <span className="font-bold">{team}</span>
      <span className="text-xs text-muted-foreground">
        {label} · {fmtSpread(spread)}
      </span>
      {score !== null && <span className="tabular text-3xl font-bold">{score}</span>}
    </div>
  )
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm font-medium">{value}</dd>
    </div>
  )
}

function InjuryTable({ team, players }: { team: string; players: InjuryReport[] }) {
  return (
    <div>
      <h3 className="mb-1 flex items-center gap-1.5 text-sm font-semibold">
        <img src={teamLogo(team)} className="size-5" alt="" />
        {team}
      </h3>
      <div className="overflow-x-auto rounded-lg border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Player</TableHead>
              <TableHead>Pos</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Practice</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {players.map((p) => (
              <TableRow key={`${p.name}-${p.position}`}>
                <TableCell className="whitespace-nowrap">{p.name}</TableCell>
                <TableCell className="text-muted-foreground">{p.position ?? '—'}</TableCell>
                <TableCell
                  className={
                    p.status?.toLowerCase() === 'out' ? 'font-semibold' : 'text-muted-foreground'
                  }
                >
                  {p.status ?? '—'}
                </TableCell>
                <TableCell className="whitespace-nowrap text-muted-foreground">
                  {p.practice ?? '—'}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

function EpaChart({
  data,
  away,
  home,
  awayKey,
  homeKey,
  title,
  hint,
}: {
  data: EpaPoint[]
  away: string
  home: string
  awayKey: keyof EpaPoint
  homeKey: keyof EpaPoint
  title: string
  hint: string
}) {
  return (
    <div>
      <h3 className="text-sm font-semibold">{title}</h3>
      <p className="mb-1 text-xs text-muted-foreground">{hint}</p>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis
            dataKey="week"
            tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
            stroke="var(--border)"
          />
          <YAxis
            tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
            stroke="var(--border)"
            width={40}
            tickFormatter={(v) => Number(v).toFixed(2)}
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
            formatter={(v) => Number(v).toFixed(3)}
            labelFormatter={(w) => `Week ${w}`}
          />
          <Line
            type="monotone"
            dataKey={awayKey}
            name={away}
            stroke={AWAY_COLOR}
            strokeWidth={2}
            dot={false}
            connectNulls
          />
          <Line
            type="monotone"
            dataKey={homeKey}
            name={home}
            stroke={HOME_COLOR}
            strokeWidth={2}
            dot={false}
            connectNulls
          />
        </LineChart>
      </ResponsiveContainer>
      <div className="mt-1 flex flex-wrap gap-x-3 text-xs">
        {[
          { team: away, color: AWAY_COLOR },
          { team: home, color: HOME_COLOR },
        ].map((s) => (
          <span key={s.team} className="flex items-center gap-1">
            <span className="inline-block h-0.5 w-3" style={{ background: s.color }} />
            {s.team}
          </span>
        ))}
      </div>
    </div>
  )
}

export default function GameDetailPage() {
  const { gameId } = useParams<{ gameId: string }>()
  // Result carries the id it belongs to, so walking to another game shows a
  // load rather than the previous game's numbers under the new heading.
  const [res, setRes] = useState<{ id: string; game?: GameDetail; error?: string } | null>(null)

  useEffect(() => {
    if (!gameId) return
    let cancelled = false
    api
      .game(gameId)
      .then((game) => !cancelled && setRes({ id: gameId, game }))
      .catch((e) => !cancelled && setRes({ id: gameId, error: String(e) }))
    return () => {
      cancelled = true
    }
  }, [gameId])

  const current = res?.id === gameId ? res : null
  const game = current?.game
  const error = current?.error

  const back = (
    <Link
      to="/picks"
      className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="size-4" /> Back
    </Link>
  )

  if (error)
    return (
      <div className="flex flex-col gap-3">
        {back}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-destructive">Could not load {gameId}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            <p className="text-sm text-muted-foreground">
              Context and EPA come from tables pushed by{' '}
              <code>scripts/update_game_context.py</code>. If they have never been created this
              call fails outright.
            </p>
            <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">{error}</pre>
          </CardContent>
        </Card>
      </div>
    )

  if (!game)
    return (
      <div className="flex flex-col gap-3">
        {back}
        <Loading />
      </div>
    )

  const { away_team: away, home_team: home } = game
  const kickoff = fmtKickoff(game.gameday, game.gametime)
  const margin = marginLabel(game)
  const injuries = groupInjuries(game.injuries, away, home)
  const series = epaSeries(game.team_weeks, away, home)

  const facts: { label: string; value: string }[] = []
  const fact = (label: string, value: string | number | boolean | null) => {
    if (value !== null && value !== undefined) facts.push({ label, value: String(value) })
  }
  fact('Stadium', game.stadium)
  fact('Roof', game.roof)
  fact('Surface', game.surface)
  fact('Temp', game.temp === null ? null : `${game.temp}°F`)
  fact('Wind', game.wind === null ? null : `${game.wind} mph`)
  fact('Divisional', game.div_game === null ? null : game.div_game ? 'Yes' : 'No')
  fact(`${away} rest`, game.away_rest === null ? null : `${game.away_rest} days`)
  fact(`${home} rest`, game.home_rest === null ? null : `${game.home_rest} days`)
  fact(`${away} QB`, game.away_qb)
  fact(`${home} QB`, game.home_qb)
  fact(`${away} coach`, game.away_coach)
  fact(`${home} coach`, game.home_coach)
  fact('Referee', game.referee)

  return (
    <div className="flex flex-col gap-4">
      {back}

      <Card>
        <CardContent className="flex flex-col gap-3">
          <p className="text-center text-xs text-muted-foreground">
            Week {game.week} · {game.season}
            {kickoff ? ` · ${kickoff}` : ''}
          </p>
          <div className="flex items-start justify-center gap-2">
            <Side
              team={away}
              spread={sideSpread(game.pool_spread ?? game.market_spread, away, home)}
              score={game.away_score}
              label="away"
            />
            <span className="pt-10 text-sm text-muted-foreground">@</span>
            <Side
              team={home}
              spread={sideSpread(game.pool_spread ?? game.market_spread, home, home)}
              score={game.home_score}
              label="home"
            />
          </div>
          {margin && <p className="text-center text-sm font-medium">Final · {margin}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-1.5 text-sm">
            Lines
            <Info text={`Home perspective, so a positive number means ${home} is favoured.`} />
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <dl className="grid grid-cols-3 gap-3">
            <Fact label="Pool" value={fmtSpread(game.pool_spread)} />
            <Fact label="Market" value={fmtSpread(game.market_spread)} />
            <Fact label="Total" value={game.market_total === null ? '—' : String(game.market_total)} />
          </dl>
          <p className="text-xs text-muted-foreground">
            {game.graded_line === null
              ? 'No line resolved yet, so nothing here grades.'
              : `Picks grade on ${fmtSpread(game.graded_line)} (${
                  game.graded_line_source ?? 'unknown'
                }).`}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">What the room did</CardTitle>
        </CardHeader>
        <CardContent>
          {game.picks.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nobody picked this game.</p>
          ) : (
            <ul className="flex flex-col divide-y divide-border">
              {game.picks.map((p) => {
                const tone = OUTCOME[p.outcome ?? 'pending'] ?? OUTCOME.pending
                return (
                  <li
                    key={`${p.picker}-${p.pick_type}`}
                    className="flex flex-col gap-1 py-2 first:pt-0 last:pb-0 sm:flex-row sm:gap-4"
                  >
                    <div className="flex items-center gap-2 sm:w-44 sm:shrink-0">
                      <img src={teamLogo(p.team_picked)} className="size-5 shrink-0" alt="" />
                      <span className="font-semibold">{p.picker}</span>
                      <span className="text-sm text-muted-foreground">{p.team_picked}</span>
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline">{SLOT_LABEL[p.pick_type]}</Badge>
                        <span className={`text-sm font-medium ${tone.className}`}>{tone.label}</span>
                      </div>
                      {/* The note is the only record of why; it gets the room it needs. */}
                      {p.note && <p className="mt-1 text-sm whitespace-pre-wrap">{p.note}</p>}
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </CardContent>
      </Card>

      {hasContext(game) && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Conditions</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {facts.map((f) => (
                <Fact key={f.label} label={f.label} value={f.value} />
              ))}
            </dl>
          </CardContent>
        </Card>
      )}

      {injuries.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Injuries</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {injuries.map((g, i) => (
              <div key={g.team} className="flex flex-col gap-4">
                {i > 0 && <Separator />}
                <InjuryTable team={g.team} players={g.players} />
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {series.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">EPA per play, week by week</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <EpaChart
              data={series}
              away={away}
              home={home}
              awayKey="awayOff"
              homeKey="homeOff"
              title="Offense"
              hint="Higher is better."
            />
            <EpaChart
              data={series}
              away={away}
              home={home}
              awayKey="awayDef"
              homeKey="homeDef"
              title="Defense"
              hint="EPA allowed, so lower is better — a line below zero is a defence holding opponents under expectation."
            />
          </CardContent>
        </Card>
      )}
    </div>
  )
}

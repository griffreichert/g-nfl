import { Fragment, useEffect, useMemo, useState } from 'react'
import { api, teamLogo } from '../api'
import { fmtSpread, useConfig, useSeasonWeek } from '../hooks'
import type { GameLine, PickRecord } from '../types'
import { buildConsensus, spreadFor, TEAM_PICKER, type ConsensusRow, type SidePick } from '@/lib/consensus'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const pickerOrder = (a: string, b: string) =>
  a === TEAM_PICKER ? 1 : b === TEAM_PICKER ? -1 : a.localeCompare(b)

function TeamLabel({ team, spread }: { team: string; spread: number | null }) {
  return (
    <span className="flex items-center gap-1.5">
      <img src={teamLogo(team)} className="w-5 h-5" alt="" />
      <b>{team}</b>
      {spread !== null && <span className="tabular text-muted-foreground">{fmtSpread(spread)}</span>}
    </span>
  )
}

function PickerChips({ label, picks }: { label: string; picks: SidePick[] }) {
  if (picks.length === 0) return null
  return (
    <div className="flex items-baseline gap-2 flex-wrap">
      <span className="text-xs text-muted-foreground w-10 shrink-0">{label}</span>
      {picks.map((p) => (
        <span
          key={p.picker}
          className={`text-xs px-1.5 py-0.5 rounded border ${
            p.bb ? 'border-bb text-bb font-bold' : 'border-border text-muted-foreground'
          }`}
        >
          {p.picker}
          {p.bb && ' ★'}
        </span>
      ))}
    </div>
  )
}

/** PK and BB are headcounts; NET is weighted points (BB 2, regular 1), TEAM excluded. */
function ConsensusTable({ rows }: { rows: ConsensusRow[] }) {
  const [open, setOpen] = useState<string | null>(null)

  return (
    <div className="bg-card rounded-lg border border-border overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Side</TableHead>
            <TableHead className="text-right">PK</TableHead>
            <TableHead className="text-right">BB</TableHead>
            <TableHead className="text-right">NET</TableHead>
            <TableHead className="text-right">TEAM</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <Fragment key={r.game.game_id}>
              <TableRow
                onClick={() => setOpen(open === r.game.game_id ? null : r.game.game_id)}
                className="cursor-pointer"
              >
                <TableCell className={r.net === 0 ? 'text-muted-foreground' : ''}>
                  <TeamLabel team={r.side} spread={r.spread} />
                  <span className="text-xs text-muted-foreground">
                    {r.game.is_mnf && '🌙 '}vs {r.other}
                  </span>
                </TableCell>
                <TableCell className="tabular text-right">{r.pk}</TableCell>
                <TableCell className="tabular text-right text-bb font-bold">
                  {r.bb || ''}
                </TableCell>
                <TableCell className="tabular text-right font-bold">
                  {r.net === 0 ? '—' : `+${r.net}`}
                </TableCell>
                <TableCell
                  className={`text-right ${r.teamAgrees === false ? 'text-loss font-bold' : 'text-muted-foreground'}`}
                >
                  {r.teamPick ?? '—'}
                  {r.teamAgrees === false && ' ⚠'}
                </TableCell>
              </TableRow>
              {open === r.game.game_id && (
                <TableRow className="bg-muted/50 hover:bg-muted/50">
                  <TableCell colSpan={5}>
                    <div className="flex flex-col gap-1.5">
                      <PickerChips label={r.side} picks={r.sidePicks} />
                      <PickerChips label={r.other} picks={r.otherPicks} />
                    </div>
                  </TableCell>
                </TableRow>
              )}
            </Fragment>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

/** The weekly call's working view: every side someone took, picker by picker. */
function Grid({
  rows,
  pickers,
}: {
  rows: ConsensusRow[]
  pickers: string[]
}) {
  const sides = rows.flatMap((r) => [
    { team: r.side, spread: r.spread, picks: r.sidePicks, gameId: r.game.game_id },
    { team: r.other, spread: spreadFor(r.game, r.other), picks: r.otherPicks, gameId: r.game.game_id },
  ])

  return (
    <div className="bg-card rounded-lg border border-border overflow-x-auto">
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
                <TableCell className="sticky left-0 bg-card whitespace-nowrap">
                  <TeamLabel team={s.team} spread={s.spread} />
                </TableCell>
                {pickers.map((p) => {
                  const hit = s.picks.find((x) => x.picker === p)
                  return (
                    <TableCell key={p} className="text-center">
                      {hit ? (
                        <span className={hit.bb ? 'text-bb font-bold' : 'text-pick'}>
                          {hit.bb ? '★' : '✓'}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
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
  season,
  weeks,
  week,
  weekPicks,
}: {
  season: number
  weeks: number[]
  week: number
  weekPicks: PickRecord[]
}) {
  const [seasonPicks, setSeasonPicks] = useState<PickRecord[] | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all(weeks.map((w) => api.picks(season, w)))
      .then((all) => !cancelled && setSeasonPicks(all.flat()))
      .catch(() => !cancelled && setSeasonPicks([]))
    return () => {
      cancelled = true
    }
  }, [season, weeks])

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
      <div className="bg-card rounded-lg border border-border p-3">
        <h2 className="font-bold text-sm mb-2">💀 Survivor — teams spent</h2>
        {seasonPicks === null && <p className="text-sm text-muted-foreground">Loading season…</p>}
        <div className="flex flex-col gap-2">
          {byPicker.map(([picker, used]) => (
            <div key={picker} className="flex items-baseline gap-2 flex-wrap">
              <span className="text-sm font-bold w-16 shrink-0">{picker}</span>
              {used.map((u) => (
                <span
                  key={`${u.week}-${u.team}`}
                  className={`text-xs px-1.5 py-0.5 rounded border ${
                    u.week === week
                      ? 'border-pick text-pick font-bold'
                      : 'border-border text-muted-foreground line-through'
                  }`}
                  title={`week ${u.week}`}
                >
                  {u.team}
                </span>
              ))}
            </div>
          ))}
        </div>
      </div>

      <div className="bg-card rounded-lg border border-border p-3">
        <h2 className="font-bold text-sm mb-2">🐶 Underdog — week {week}</h2>
        {dogs.length === 0 && <p className="text-sm text-muted-foreground">No dog picks yet.</p>}
        <div className="flex flex-col gap-1.5">
          {dogs.map((d) => (
            <div key={`${d.picker}-${d.game_id}`} className="flex items-center gap-2 text-sm">
              <span className="w-16 shrink-0 font-bold">{d.picker}</span>
              <TeamLabel team={d.team_picked} spread={d.spread} />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function Field() {
  const { config, error: configError } = useConfig()
  const { season, setSeason, week, setWeek, weeks, seasons } = useSeasonWeek(config)
  const [picks, setPicks] = useState<PickRecord[]>([])
  const [games, setGames] = useState<GameLine[]>([])
  const [error, setError] = useState<string | null>(null)

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

  const rows = useMemo(() => buildConsensus(games, picks), [games, picks])
  const pickers = useMemo(
    () => [...new Set(picks.map((p) => p.picker))].sort(pickerOrder),
    [picks],
  )

  if (configError) return <p className="text-destructive">Failed to load config: {configError}</p>
  if (!config || season === null || week === null) return <p>Loading…</p>

  return (
    <div>
      <h1 className="text-2xl font-bold mb-3">🔍 Field</h1>

      <div className="flex gap-2 mb-4">
        <Select value={String(season)} onValueChange={(v) => setSeason(Number(v))}>
          <SelectTrigger className="w-28">
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
          <SelectTrigger className="w-32">
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
      </div>

      {error && <p className="text-destructive">{error}</p>}
      {!error && rows.length === 0 && (
        <p className="text-muted-foreground">No picks yet for week {week}.</p>
      )}

      {!error && rows.length > 0 && (
        <Tabs defaultValue="consensus">
          <TabsList className="mb-3">
            <TabsTrigger value="consensus">Consensus</TabsTrigger>
            <TabsTrigger value="grid">Grid</TabsTrigger>
            <TabsTrigger value="survivor">Survivor</TabsTrigger>
          </TabsList>

          <TabsContent value="consensus" className="flex flex-col gap-2">
            <ConsensusTable rows={rows} />
            <p className="text-xs text-muted-foreground">
              PK and BB are headcounts. NET is weighted points — best bet 2, regular and MNF 1 —
              for the leading side minus the other, with TEAM excluded. Tap a row for who's where.
              Splits sort last.
            </p>
          </TabsContent>

          <TabsContent value="grid">
            <Grid rows={rows} pickers={pickers} />
          </TabsContent>

          <TabsContent value="survivor">
            <Survivor season={season} weeks={weeks} week={week} weekPicks={picks} />
          </TabsContent>
        </Tabs>
      )}
    </div>
  )
}

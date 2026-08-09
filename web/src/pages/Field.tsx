import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Star } from 'lucide-react'
import { api, teamLogo } from '../api'
import { fmtSpread, useConfig, useSeasonWeek } from '../hooks'
import type { GameLine, PickRecord } from '../types'
import {
  BANDS,
  bestSide,
  BREAK_EVEN,
  buildAttachment,
  buildConsensus,
  byScore,
  findBlocs,
  scoreSide,
  spreadFor,
  TEAM_PICKER,
  type ConsensusRow,
  type Score,
  type SidePick,
} from '@/lib/consensus'
import SplitBar from '@/components/SplitBar'
import BandChart from '@/components/BandChart'
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

/** Expected ATS% for a side, and how far that sits from the -110 break-even. */
function ScorePill({ score }: { score: Score }) {
  const good = score.total >= BREAK_EVEN
  return (
    <span
      className={`tabular rounded px-1.5 py-0.5 text-xs font-semibold ${
        good ? 'bg-win/15 text-win' : 'bg-loss/15 text-loss'
      }`}
      title={score.parts
        .map((p) => `${p.label}: ${p.value > 0 ? '+' : ''}${p.value.toFixed(1)}${p.measured ? '' : ' (judgement)'}`)
        .join('\n')}
    >
      {score.total.toFixed(1)}%
    </span>
  )
}

function Side({
  team,
  spread,
  picks,
  isTeamPick,
  lead,
  score,
  blocs,
}: {
  team: string
  spread: number | null
  picks: SidePick[]
  isTeamPick: boolean
  lead: boolean
  score: Score
  blocs: string[][]
}) {
  return (
    <div
      className={`flex flex-wrap items-center gap-x-2 gap-y-1.5 rounded-md px-2 py-1.5 ${
        lead ? 'bg-muted/60' : ''
      }`}
    >
      <img src={teamLogo(team)} alt="" className={`size-6 ${picks.length ? '' : 'opacity-40'}`} />
      <span className="font-semibold">{team}</span>
      <span className="tabular text-sm text-muted-foreground">{fmtSpread(spread)}</span>
      <ScorePill score={score} />
      {isTeamPick && (
        <span className="rounded bg-primary px-1.5 py-0.5 text-[10px] font-bold text-primary-foreground">
          TEAM
        </span>
      )}
      <span className="ml-auto flex flex-wrap justify-end gap-1">
        {toChips(picks, blocs).map((c) => (
          <Chip key={c.picks.join('+')} picks={c.picks} bb={c.bb} />
        ))}
      </span>
    </div>
  )
}

function GameCard({
  row,
  attachment,
  blocs,
}: {
  row: ConsensusRow
  attachment: Map<string, number>
  blocs: string[][]
}) {
  const split = row.blocOther > 0 && row.blocSide > 0
  const otherSpread = spreadFor(row.game, row.other)
  // Two weak signals stacked: a best bet on a game nobody is arguing about.
  const warn = row.bb > 0 && !split

  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <div className="mb-2 flex items-center gap-2 text-xs">
        <span
          className={`rounded px-1.5 py-0.5 font-medium ${
            row.band?.tone === 'good'
              ? 'bg-win/15 text-win'
              : row.band
                ? 'bg-loss/15 text-loss'
                : 'bg-muted text-muted-foreground'
          }`}
          title={
            row.band
              ? `2025: we hit ${row.band.pct}% on spreads of ${row.band.label} (n=${row.band.n})`
              : 'No pool line yet'
          }
        >
          {row.band ? `${row.band.label} · ${row.band.pct}%` : 'no line'}
        </span>
        {row.game.is_mnf && (
          <span className="rounded bg-secondary px-1.5 py-0.5 text-secondary-foreground">MNF</span>
        )}
        <span className="ml-auto text-muted-foreground">
          {split ? (
            <span className="font-medium text-foreground">
              split {row.blocSide}–{row.blocOther}
            </span>
          ) : (
            `${row.blocSide} agree`
          )}
        </span>
        {warn && (
          <span title="Best bet on a game nobody is contesting — our two weakest historical signals stacked">
            <AlertTriangle className="size-3.5 text-loss" />
          </span>
        )}
      </div>

      <div className="mb-2 flex flex-col gap-1">
        <Side
          team={row.side}
          spread={row.spread}
          picks={row.sidePicks}
          isTeamPick={row.teamPick === row.side}
          lead
          score={scoreSide(row, row.side, attachment)}
          blocs={blocs}
        />
        <Side
          team={row.other}
          spread={otherSpread}
          picks={row.otherPicks}
          isTeamPick={row.teamPick === row.other}
          lead={false}
          score={scoreSide(row, row.other, attachment)}
          blocs={blocs}
        />
      </div>

      <SplitBar row={row} />
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
        {seasonPicks === null && <p className="text-sm text-muted-foreground">Loading season…</p>}
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

export default function Field() {
  const { config, error: configError } = useConfig()
  const { season, setSeason, week, setWeek, weeks, seasons } = useSeasonWeek(config)
  const [picks, setPicks] = useState<PickRecord[]>([])
  const [games, setGames] = useState<GameLine[]>([])
  const [seasonPicks, setSeasonPicks] = useState<PickRecord[] | null>(null)
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

  // Blocs need the whole season — one week is far too little to tell a habit
  // from a coincidence. Survivor inventory rides along on the same fetch.
  useEffect(() => {
    if (season === null || weeks.length === 0) return
    let cancelled = false
    setSeasonPicks(null)
    Promise.all(weeks.map((w) => api.picks(season, w)))
      .then((all) => !cancelled && setSeasonPicks(all.flat()))
      .catch(() => !cancelled && setSeasonPicks([]))
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
      built.map((r) => [r.game.game_id, bestSide(r, attachment).score.total]),
    )
    return built.sort(byScore(best))
  }, [games, picks, blocs, attachment])
  const pickers = useMemo(
    () => [...new Set(picks.map((p) => p.picker))].sort(pickerOrder),
    [picks],
  )

  const bandCounts = useMemo(() => {
    const c: Record<string, number> = {}
    for (const r of rows) {
      const n = r.sidePicks.length + r.otherPicks.length
      if (r.band) c[r.band.label] = (c[r.band.label] ?? 0) + n
    }
    return c
  }, [rows])

  if (configError) return <p className="text-destructive">Failed to load config: {configError}</p>
  if (!config || season === null || week === null) return <p>Loading…</p>

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-xl font-bold sm:text-2xl">Team</h1>
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
        <Select value={String(week)} onValueChange={(v) => setWeek(Number(v))}>
          <SelectTrigger size="sm" className="w-28">
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
        <Tabs defaultValue="board">
          <TabsList className="mb-3">
            <TabsTrigger value="board">Board</TabsTrigger>
            <TabsTrigger value="grid">Grid</TabsTrigger>
            <TabsTrigger value="survivor">Survivor</TabsTrigger>
          </TabsList>

          <TabsContent value="board" className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              {rows.map((r) => (
                <GameCard
                  key={r.game.game_id}
                  row={r}
                  attachment={attachment}
                  blocs={blocs}
                />
              ))}
            </div>

            <div className="rounded-lg border border-border bg-card p-3">
              <h2 className="text-sm font-bold">Our ATS hit rate by spread size</h2>
              <p className="mb-1 text-xs text-muted-foreground">
                2025, 777 graded picks. Close games 57.1%, everything else under 45% — the only
                split in our history significant at both tails.
              </p>
              <BandChart counts={bandCounts} />
              <p className="text-xs text-muted-foreground">
                This week we have{' '}
                {BANDS.map((b) => `${bandCounts[b.label] ?? 0} in ${b.label}`).join(', ')}.
              </p>
            </div>

            <p className="text-xs text-muted-foreground">
              Every side carries an expected ATS%, best first. It is built from what graded out in
              2025: spread band, contested or not, the best-bet slot, home or road. Agreement counts
              against a side — the games we all agreed on went 45.2% and the contested ones 52.4%.
              Homer and attachment terms are judgement, capped so they can only break a tie; hover a
              score to see the breakdown. Full analysis in{' '}
              <code>notes/team-page-consensus-analysis.md</code>.
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

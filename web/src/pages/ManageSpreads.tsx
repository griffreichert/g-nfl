import { useEffect, useState } from 'react'
import { api, teamLogo } from '../api'
import { fmtSpread, useConfig, useSeasonWeek } from '../hooks'
import type { GameLine } from '../types'
import { Button } from '@/components/ui/button'
import PageHeader from '@/components/PageHeader'
import { ErrorNote, Loading } from '@/components/PageState'

export default function ManageSpreads() {
  const { config, error: configError } = useConfig()
  const { season, setSeason, week, setWeek, weeks, seasons } = useSeasonWeek(config)
  const [games, setGames] = useState<GameLine[]>([])
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [status, setStatus] = useState<{ kind: 'ok' | 'err'; msg: string } | null>(null)

  const load = () => {
    if (season === null || week === null) return
    api.lines(season, week).then((g) => {
      setGames(g)
      setDrafts(Object.fromEntries(g.map((x) => [x.game_id, x.pool_spread?.toString() ?? ''])))
    })
  }
  useEffect(load, [season, week])

  const saveOne = async (g: GameLine) => {
    const raw = drafts[g.game_id]
    const spread = Number(raw)
    if (raw === '' || Number.isNaN(spread)) {
      setStatus({ kind: 'err', msg: `Invalid spread for ${g.away_team} @ ${g.home_team}` })
      return
    }
    if (season === null || week === null) return
    try {
      await api.updatePoolSpread(season, week, g.game_id, spread)
      setStatus({ kind: 'ok', msg: `Saved ${g.away_team} @ ${g.home_team}: ${fmtSpread(spread)}` })
      load()
    } catch (e) {
      setStatus({ kind: 'err', msg: String(e) })
    }
  }

  if (configError) return <ErrorNote>Failed to load config: {configError}</ErrorNote>
  if (!config || season === null || week === null) return <Loading />

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Lines"
        season={season}
        seasons={seasons}
        onSeason={setSeason}
        week={week}
        weeks={weeks}
        onWeek={setWeek}
      />

      <p className="text-sm text-muted-foreground">
        Pool spread is what picks grade against. Blank means the market line stands.
      </p>

      {status && (
        <p
          className={`rounded-md px-3 py-2 text-sm ${
            status.kind === 'ok' ? 'bg-win/15 text-win' : 'bg-loss/15 text-loss'
          }`}
        >
          {status.msg}
        </p>
      )}

      <div className="divide-y divide-border rounded-lg border border-border bg-card">
        {games.map((g) => {
          const saved = g.pool_spread?.toString() ?? ''
          const dirty = (drafts[g.game_id] ?? '') !== saved
          return (
            <div key={g.game_id} className="flex items-center gap-2 px-2 py-2 text-sm sm:px-3">
              <img src={teamLogo(g.away_team)} className="size-6 shrink-0" alt="" />
              <span className="flex-1 truncate whitespace-nowrap">
                {g.away_team} @ {g.home_team}
                <span className="tabular ml-2 hidden text-muted-foreground sm:inline">
                  market {fmtSpread(g.market_spread)}
                </span>
              </span>
              <input
                type="number"
                step="0.5"
                inputMode="decimal"
                value={drafts[g.game_id] ?? ''}
                placeholder={fmtSpread(g.market_spread)}
                onChange={(e) => setDrafts((d) => ({ ...d, [g.game_id]: e.target.value }))}
                aria-label={`Pool spread for ${g.away_team} at ${g.home_team}`}
                className="tabular h-8 w-20 rounded-md border border-input bg-transparent px-2 text-right text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 dark:bg-input/30"
              />
              {/* Only the row you actually changed offers a save — 16 live green
                  buttons is noise, and it makes an unsaved edit obvious. */}
              <Button
                size="sm"
                variant={dirty ? 'default' : 'outline'}
                disabled={!dirty}
                onClick={() => saveOne(g)}
              >
                Save
              </Button>
              <img src={teamLogo(g.home_team)} className="size-6 shrink-0" alt="" />
            </div>
          )
        })}
      </div>
    </div>
  )
}

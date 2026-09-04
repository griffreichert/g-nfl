import { useState } from 'react'
import { Minus, Plus } from 'lucide-react'
import { api } from '../api'
import { fmtSpread } from '../hooks'
import type { GameLine } from '../types'
import { Button } from '@/components/ui/button'

const STEP = 0.5

/**
 * The pool spread editor, toggled from the bottom bar's "Edit Lines" button.
 * Lives here rather than on one page because both Board and Submit My Picks
 * need it (#126 follow-up) — it used to be `Field.tsx`-local.
 *
 * `-`/`+` step the line half a point at a time — the common edit is nudging
 * a market number, not retyping it — and the field still takes a typed
 * number for a line that moved further than a step or two. One Save writes
 * every row, not just the touched ones, instead of a button per row (#126
 * follow-up: Griffin found the per-row spinner+Save fiddly on a laptop
 * trackpad) — an untouched game copies its market number in as the pool
 * spread, so a save leaves nothing still falling back to market.
 */
export function LinesEditor({
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
  const [saving, setSaving] = useState(false)

  const valueFor = (g: GameLine) => drafts[g.game_id] ?? g.pool_spread?.toString() ?? ''
  const savedFor = (g: GameLine) => g.pool_spread?.toString() ?? ''
  const isDirty = (g: GameLine) => valueFor(g) !== savedFor(g)
  const dirtyGames = games.filter(isDirty)

  const step = (g: GameLine, delta: number) => {
    const current = Number(valueFor(g) || g.market_spread || 0)
    const next = Math.round((current + delta) * 2) / 2
    setDrafts((d) => ({ ...d, [g.game_id]: next.toString() }))
  }

  // An untouched game copies its market number in rather than staying null —
  // Save writes what the pool actually grades against for every game, not
  // just the ones somebody nudged.
  const targetFor = (g: GameLine) => (isDirty(g) ? valueFor(g) : (g.market_spread?.toString() ?? ''))
  const toSave = games.filter((g) => targetFor(g) !== '')

  const saveAll = async () => {
    const invalid = dirtyGames.find((g) => Number.isNaN(Number(valueFor(g))) || valueFor(g) === '')
    if (invalid) {
      setStatus(`Invalid spread for ${invalid.away_team} @ ${invalid.home_team}`)
      return
    }
    setSaving(true)
    try {
      await Promise.all(
        toSave.map((g) => api.updatePoolSpread(season, week, g.game_id, Number(targetFor(g)))),
      )
      setStatus(`Saved ${toSave.length} line${toSave.length === 1 ? '' : 's'}`)
      setDrafts({})
      onSaved()
    } catch (e) {
      setStatus(String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-bold">Pool lines</h2>
          <p className="text-xs text-muted-foreground">
            What picks grade against. Save copies the market number in for
            anything you don't touch.
          </p>
        </div>
        <Button size="sm" disabled={toSave.length === 0 || saving} onClick={saveAll}>
          {saving ? 'Saving…' : 'Save Lines'}
        </Button>
      </div>
      {status && <p className="mt-2 text-xs text-muted-foreground">{status}</p>}
      <div className="mt-2 divide-y divide-border">
        {games.map((g) => (
          <div key={g.game_id} className="flex items-center gap-2 py-1.5 text-sm">
            <span className="min-w-0 flex-1 truncate">
              {g.away_team} @ {g.home_team}
              <span className="tabular ml-2 hidden text-muted-foreground sm:inline">
                market {fmtSpread(g.market_spread)}
              </span>
            </span>
            <div
              className={`flex items-center rounded-md border ${
                isDirty(g) ? 'border-pick' : 'border-input'
              }`}
            >
              <button
                type="button"
                onClick={() => step(g, -STEP)}
                aria-label={`Decrease pool spread for ${g.away_team} at ${g.home_team}`}
                className="flex h-8 w-7 items-center justify-center text-muted-foreground hover:text-foreground"
              >
                <Minus className="size-3.5" />
              </button>
              <input
                type="text"
                inputMode="decimal"
                value={valueFor(g)}
                placeholder={fmtSpread(g.market_spread)}
                onChange={(e) => setDrafts((d) => ({ ...d, [g.game_id]: e.target.value }))}
                aria-label={`Pool spread for ${g.away_team} at ${g.home_team}`}
                className="tabular h-8 w-14 border-x border-input bg-transparent text-center text-sm outline-none"
              />
              <button
                type="button"
                onClick={() => step(g, STEP)}
                aria-label={`Increase pool spread for ${g.away_team} at ${g.home_team}`}
                className="flex h-8 w-7 items-center justify-center text-muted-foreground hover:text-foreground"
              >
                <Plus className="size-3.5" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

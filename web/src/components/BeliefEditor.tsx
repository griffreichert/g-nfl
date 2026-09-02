import { ChevronDown, ChevronRight } from 'lucide-react'
import { teamLogo } from '../api'
import type { SurvivorBelief } from '../types'

/**
 * Where the user tells the board what the ratings cannot know (#72).
 *
 * Ratings say what a team is. They do not say how sure anyone is about
 * that, and they do not say how long it will stay true. Both are
 * judgement, they differ per person, and that difference is exactly why
 * two entries plan different seasons off identical numbers.
 *
 * Confidence is doubt about the rating today — a new coach, a new
 * quarterback, a roster that turned over. Fragility is how fast the
 * rating goes stale: injury risk, or a bad team that fires a coordinator
 * in November and stops resembling itself. Both widen the margin
 * distribution, which pulls a win probability toward 50%, so doubt costs
 * you most on the big favourite you were saving.
 */

const STEPS = [0, 1, 2, 3, 4]

const LABELS: Record<number, string> = {
  0: 'no doubt',
  1: 'slight',
  2: 'some',
  3: 'a lot',
  4: 'no idea',
}

type Props = {
  teams: string[]
  beliefs: Record<string, SurvivorBelief>
  onChange: (team: string, field: 'confidence' | 'fragility', value: number) => void
  open: boolean
  onToggle: () => void
  status: string | null
}

function Steps({
  value,
  onPick,
  title,
}: {
  value: number
  onPick: (v: number) => void
  title: string
}) {
  return (
    <span className="flex gap-0.5" title={title}>
      {STEPS.map((s) => (
        <button
          key={s}
          onClick={() => onPick(s)}
          aria-label={`${title}: ${LABELS[s]}`}
          className={`size-5 rounded-sm border text-[10px] tabular-nums transition-colors ${
            s === value
              ? 'border-primary bg-primary text-primary-foreground'
              : 'border-border text-muted-foreground hover:bg-muted'
          }`}
        >
          {s}
        </button>
      ))}
    </span>
  )
}

export default function BeliefEditor({
  teams,
  beliefs,
  onChange,
  open,
  onToggle,
  status,
}: Props) {
  const touched = teams.filter(
    (t) => beliefs[t] && (beliefs[t].confidence || beliefs[t].fragility)
  )

  return (
    <div className="rounded-lg border border-border bg-card">
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-2 px-4 py-3 text-left"
      >
        {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
        <span className="text-sm font-semibold">What the ratings can't know</span>
        <span className="text-xs text-muted-foreground">
          {touched.length ? `${touched.length} teams adjusted` : 'nothing adjusted yet'}
        </span>
        {status && <span className="ml-auto text-xs text-muted-foreground">{status}</span>}
      </button>

      {open && (
        <div className="border-t border-border px-4 py-3">
          <p className="mb-3 max-w-3xl text-xs text-muted-foreground">
            <b>Doubt</b> is how wrong the rating might be today — new coach, new
            quarterback, a roster you have not seen play. <b>Decay</b> is how fast it
            goes stale: injury risk, or a bad team that stops trying in December. Doubt
            applies evenly across the season; decay grows the further out the week is.
            Both pull a win probability toward a coin flip, so they cost you most on the
            teams you were planning to save.
          </p>

          <div className="grid gap-x-8 gap-y-1 sm:grid-cols-2 xl:grid-cols-3">
            {teams.map((team) => {
              const b = beliefs[team] ?? { team, confidence: 0, fragility: 0 }
              return (
                <div key={team} className="flex items-center gap-2 py-0.5">
                  <img src={teamLogo(team)} alt="" className="size-5" />
                  <span className="w-10 text-xs font-medium">{team}</span>
                  <Steps
                    value={b.confidence}
                    title={`${team} doubt`}
                    onPick={(v) => onChange(team, 'confidence', v)}
                  />
                  <span className="text-[10px] text-muted-foreground">doubt</span>
                  <Steps
                    value={b.fragility}
                    title={`${team} decay`}
                    onPick={(v) => onChange(team, 'fragility', v)}
                  />
                  <span className="text-[10px] text-muted-foreground">decay</span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

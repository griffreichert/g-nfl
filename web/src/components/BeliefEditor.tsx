import { ChevronDown, ChevronRight } from 'lucide-react'
import { teamLogo } from '../api'
import { NEUTRAL, STEPS, STEP_LABELS } from '../lib/survivor'
import type { SurvivorBelief } from '../types'

/**
 * Where the picker tells the board what the ratings cannot know (#72).
 *
 * Ratings say what a team is. They do not say how long that stays true,
 * and that judgement differs per person — which is exactly why two
 * entries plan different seasons off identical numbers.
 *
 * One knob, deliberately. A flat "I don't trust this rating" term moves a
 * team's probability equally in every week, so it changes whether you
 * spend them and barely changes when — and when is the only question
 * survivor asks. What earns a control is the part that grows with
 * distance: the Rams still being the Rams in December, against a team an
 * injury or a hot seat away from being someone else.
 */

type Props = {
  teams: string[]
  beliefs: Record<string, SurvivorBelief>
  onChange: (team: string, value: number) => void
  open: boolean
  onToggle: () => void
  status: string | null
}

export default function BeliefEditor({
  teams,
  beliefs,
  onChange,
  open,
  onToggle,
  status,
}: Props) {
  const touched = teams.filter((t) => beliefs[t] && beliefs[t].confidence !== NEUTRAL)

  return (
    <div className="rounded-lg border border-border bg-card">
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-2 px-4 py-3 text-left"
      >
        {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
        <span className="text-sm font-semibold">Confidence</span>
        <span className="text-xs text-muted-foreground">
          how well each rating holds up ·{' '}
          {touched.length ? `${touched.length} set` : 'all neutral'}
        </span>
        {status && <span className="ml-auto text-xs text-muted-foreground">{status}</span>}
      </button>

      {open && (
        <div className="border-t border-border px-4 py-3">
          <p className="mb-1 max-w-3xl text-xs text-muted-foreground">
            A rating says what a team is today. This says how long you think that
            lasts. <b>5</b> is a team you would still back in December — settled roster,
            settled coach. <b>1</b> is one injury, one hot seat, or one bad month from
            being somebody else. <b>3</b> is no opinion and changes nothing.
          </p>
          <p className="mb-3 max-w-3xl text-xs text-muted-foreground">
            It bites harder the further out the week is, so it moves <i>when</i> you
            spend a team rather than whether you like them. Low confidence pulls their
            late-season weeks toward a coin flip; high confidence sharpens them.
          </p>

          <div className="grid gap-x-8 gap-y-1 sm:grid-cols-2 xl:grid-cols-3">
            {teams.map((team) => {
              const value = beliefs[team]?.confidence ?? NEUTRAL
              return (
                <div key={team} className="flex items-center gap-2 py-0.5">
                  <img src={teamLogo(team)} alt="" className="size-5" />
                  <span className="w-10 text-xs font-medium">{team}</span>
                  <span className="flex gap-0.5">
                    {STEPS.map((s) => (
                      <button
                        key={s}
                        onClick={() => onChange(team, s)}
                        title={`${team}: ${STEP_LABELS[s]}`}
                        aria-label={`${team}: ${STEP_LABELS[s]}`}
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
                  <span className="text-[10px] text-muted-foreground">
                    {value === NEUTRAL ? '' : STEP_LABELS[value]}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

import { teamLogo } from '../api'
import type { ConsensusRow } from '@/lib/consensus'

/**
 * Where the room actually stands on one game: a bar split by pool-point weight,
 * a logo anchoring each end. Reads at a glance from across a kitchen table,
 * which is the room this gets used in.
 */
export default function SplitBar({ row }: { row: ConsensusRow }) {
  const sideW = row.sidePicks.reduce((s, p) => s + (p.bb ? 2 : 1), 0)
  const otherW = row.otherPicks.reduce((s, p) => s + (p.bb ? 2 : 1), 0)
  const total = sideW + otherW
  const pct = total === 0 ? 50 : (sideW / total) * 100

  return (
    <div className="flex items-center gap-2">
      <img src={teamLogo(row.side)} alt="" className="size-6 shrink-0" />
      <div className="relative h-2.5 flex-1 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-pick transition-[width]"
          style={{ width: `${pct}%` }}
        />
        {/* dead-centre tick: the eye needs a reference for "even split" */}
        <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-background/70" />
      </div>
      <img src={teamLogo(row.other)} alt="" className="size-6 shrink-0 opacity-60" />
    </div>
  )
}

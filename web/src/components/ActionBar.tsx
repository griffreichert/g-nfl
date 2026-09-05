import type { ReactNode } from 'react'

/**
 * Slot progress and the Save button, pinned under the header (#124).
 *
 * Both pick pages assemble one entry against the same slot rules, and both
 * used to put the count in a line of text that scrolled away and the primary
 * button somewhere different: bottom of the page on Picks, top on Team. The
 * count is the whole constraint of the task, so it stays on screen.
 *
 * `top-14` clears the app header, which is `h-14` and sticky.
 */
export default function ActionBar({
  slots,
  children,
}: {
  slots: ReactNode
  children: ReactNode
}) {
  return (
    <div className="sticky top-14 z-10 -mx-3 flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-border bg-card/95 px-3 py-2 backdrop-blur sm:-mx-5 sm:px-5">
      <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">{slots}</span>
      <span className="ml-auto flex items-center gap-2">{children}</span>
    </div>
  )
}

/** One slot of an entry: filled, or how many are still open. */
export function Slot({
  label,
  have,
  need,
}: {
  label: string
  have: number
  need: number
}) {
  const done = have >= need
  return (
    <span className={done ? 'text-foreground' : 'text-muted-foreground'}>
      <span className={done ? 'text-pick' : ''}>{done ? '●' : '○'}</span>{' '}
      <span className="tabular font-semibold">
        {have}/{need}
      </span>{' '}
      {label}
    </span>
  )
}

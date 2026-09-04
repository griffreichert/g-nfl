import { useState, type ReactNode } from 'react'
import { ChevronDown, ChevronUp, Clipboard, Eraser, PenLine } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { POOL_TEXT, type PoolColor } from '../hooks'

/**
 * Slot progress and the Save button, pinned to the bottom of the screen like
 * a cart bar (#124, revised after the top-pinned version scrolled the primary
 * action out of thumb reach on a long board).
 *
 * Both pick pages assemble one entry against the same slot rules, and the
 * count is the whole constraint of the task, so it and the button that acts
 * on it stay on screen together regardless of scroll position.
 *
 * `bottom-14` clears the phone tab bar, which is `h-14` and fixed; the tab
 * bar is `sm:hidden`, so `sm:bottom-0` drops straight to the viewport edge.
 * `ActionBarSpacer` reserves the matching space in normal flow so this
 * doesn't cover the page's last card.
 *
 * `detail` is the expanded view: what the dots above only count, this spells
 * out. Collapsed by default so the ribbon stays a thumb's width; the chevron
 * is the only new control, and it's a no-op with nothing to show.
 */
export default function ActionBar({
  slots,
  detail,
  status,
  children,
}: {
  slots: ReactNode
  detail?: ReactNode
  status?: { kind: 'ok' | 'err'; msg: string } | null
  children: ReactNode
}) {
  const [open, setOpen] = useState(true)
  return (
    <div className="fixed inset-x-0 bottom-14 z-20 border-t border-border bg-card/95 backdrop-blur sm:bottom-0">
      {/* Lives where the buttons that trigger it live, not at the top of the
          page — a toast that pops above the fold while your eyes are on the
          bottom bar goes unseen (#126 follow-up). */}
      {status && (
        <p
          className={`mx-auto max-w-6xl px-3 py-1.5 text-sm sm:px-5 ${
            status.kind === 'ok' ? 'bg-win/15 text-win' : 'bg-loss/15 text-loss'
          }`}
        >
          {status.msg}
        </p>
      )}
      {open && detail && (
        <div className="mx-auto max-h-[45vh] max-w-6xl overflow-y-auto border-b border-border px-3 py-2 sm:px-5">
          {detail}
        </div>
      )}
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2 sm:px-5">
        {detail && (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-label={open ? 'Collapse Picks' : 'Expand Picks'}
            aria-expanded={open}
            className="flex size-6 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            {open ? <ChevronDown className="size-4" /> : <ChevronUp className="size-4" />}
          </button>
        )}
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">{slots}</span>
        <span className="ml-auto flex items-center gap-2">{children}</span>
      </div>
    </div>
  )
}

/** The space `ActionBar` takes out of the page it floats over. Render it once, last. */
export function ActionBarSpacer() {
  return <div className="h-24 sm:h-16" />
}

/**
 * Copy the entry as chat-ready text. Same button on Board and Submit My
 * Picks (#126 follow-up) — it used to be icon-only on one page and missing
 * on the other.
 */
export function CopyButton({ onClick, disabled }: { onClick: () => void; disabled?: boolean }) {
  return (
    <Button size="sm" variant="outline" onClick={onClick} disabled={disabled}>
      <Clipboard className="size-3.5" />
      Copy
    </Button>
  )
}

/** Toggles the `LinesEditor` panel. Same button on Board and Submit My Picks. */
export function EditLinesButton({ editing, onClick }: { editing: boolean; onClick: () => void }) {
  return (
    <Button size="sm" variant="outline" onClick={onClick}>
      <PenLine className="size-3.5" />
      {editing ? 'Done With Lines' : 'Edit Lines'}
    </Button>
  )
}

/**
 * Wipe the entry back to blank (Board: back to whatever's already submitted).
 * Nothing is written until Save/Submit, so this is a local, reversible
 * reset, not a server call.
 */
export function ClearButton({ onClick, disabled }: { onClick: () => void; disabled?: boolean }) {
  return (
    <Button size="sm" variant="outline" onClick={onClick} disabled={disabled}>
      <Eraser className="size-3.5" />
      Clear Picks
    </Button>
  )
}

/** One slot of an entry: empty, filled partway, or filled. Dot colour names the pool. */
export function Slot({
  label,
  color,
  have,
  need,
}: {
  label: string
  color: PoolColor
  have: number
  need: number
}) {
  const started = have > 0
  return (
    <span className={started ? 'text-foreground' : 'text-muted-foreground'}>
      <span className={started ? POOL_TEXT[color] : ''}>{started ? '●' : '○'}</span>{' '}
      <span className="tabular font-semibold">
        {have}/{need}
      </span>{' '}
      {label}
    </span>
  )
}

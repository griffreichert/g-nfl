import type { ReactNode } from 'react'

/**
 * The three things a page shows instead of its content: waiting, nothing to
 * show, and broken. They were spelled a different way on every page — "Loading…",
 * "Loading game…", "Loading season…", some muted and some not — so a week change
 * moved the text around under the header.
 */

/** Waiting on a fetch. One wording, one colour, everywhere. */
export function Loading({ children = 'Loading…' }: { children?: ReactNode }) {
  return <p className="text-muted-foreground">{children}</p>
}

/** Nothing to show, and that is the honest answer rather than a crash. */
export function EmptyState({
  title,
  detail,
  note,
}: {
  title: string
  detail?: ReactNode
  /** Underlying error text, when there is one worth showing small. */
  note?: ReactNode
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-6 text-center">
      <p className="font-medium">{title}</p>
      {detail && <p className="mt-1 text-sm text-muted-foreground">{detail}</p>}
      {note && <p className="mt-3 text-xs text-muted-foreground">{note}</p>}
    </div>
  )
}

/** A failure the page cannot render around. */
export function ErrorNote({ children }: { children: ReactNode }) {
  return <p className="text-destructive">{children}</p>
}

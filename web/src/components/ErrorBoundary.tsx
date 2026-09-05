import { Component, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'

/**
 * Catches a render error under it and shows the message.
 *
 * Without one, React unmounts the whole tree on a throw, so the header goes
 * with the page and the viewer gets a bare dark screen carrying nothing to
 * report.
 */
export default class ErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: { componentStack?: string | null }) {
    console.error('page crashed', error, info.componentStack)
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children
    return (
      <div className="rounded-lg border border-destructive/40 bg-card p-6">
        <p className="font-medium">This page hit an error</p>
        <p className="mt-1 text-sm text-destructive">{error.message || String(error)}</p>
        <p className="mt-3 text-xs text-muted-foreground">
          The tabs above still work. The full stack is in the browser console.
        </p>
        <Button className="mt-4" onClick={() => window.location.reload()}>
          Reload
        </Button>
      </div>
    )
  }
}

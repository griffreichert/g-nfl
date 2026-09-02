import { Suspense, lazy } from 'react'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { ChartColumn, CircleQuestionMark, ClipboardCheck, LineChart, Ruler, Scale, Skull, Users } from 'lucide-react'
import ThemeToggle from './components/ThemeToggle'
import { useAuth } from './hooks'

// Split per route so a page's charts and tables are fetched when someone opens
// it, not on first paint. Recharts and TanStack Table are most of the bundle.
const MakePicks = lazy(() => import('./pages/MakePicks'))
const Field = lazy(() => import('./pages/Field'))
const GameDetail = lazy(() => import('./pages/GameDetail'))
const ManageSpreads = lazy(() => import('./pages/ManageSpreads'))
const Survivor = lazy(() => import('./pages/Survivor'))
const Standings = lazy(() => import('./pages/Standings'))
const Analytics = lazy(() => import('./pages/Analytics'))
const Ledger = lazy(() => import('./pages/Ledger'))
const Help = lazy(() => import('./pages/Help'))

const tabs = [
  { to: '/picks', label: 'Picks', icon: ClipboardCheck },
  { to: '/view', label: 'Team', icon: Users },
  { to: '/survivor', label: 'Survivor', icon: Skull },
  { to: '/standings', label: 'Standings', icon: LineChart },
  { to: '/spreads', label: 'Lines', icon: Ruler },
  { to: '/ledger', label: 'Ledger', icon: Scale },
  { to: '/analytics', label: 'Analytics', icon: ChartColumn },
]

export default function App() {
  const { picker, logout } = useAuth()

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-20 border-b border-border bg-card/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-1 px-3 sm:px-5">
          <span className="mr-3 font-bold tracking-tight">
            no<span className="text-primary">·</span>homers
          </span>

          {/* laptop: inline tabs. mobile: the bottom bar owns navigation. */}
          <nav className="hidden gap-1 sm:flex">
            {tabs.map((t) => (
              <NavLink
                key={t.to}
                to={t.to}
                className={({ isActive }) =>
                  `flex h-9 items-center rounded-md px-3 text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-secondary text-foreground'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                  }`
                }
              >
                {t.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-1">
            <NavLink
              to="/help"
              aria-label="How this works"
              title="How this works"
              className={({ isActive }) =>
                `flex size-9 items-center justify-center rounded-md transition-colors ${
                  isActive ? 'text-primary' : 'text-muted-foreground hover:text-foreground'
                }`
              }
            >
              <CircleQuestionMark className="size-5" />
            </NavLink>
            {picker && (
              <button
                onClick={logout}
                title={`Signed in as ${picker}`}
                className="flex h-9 items-center rounded-md px-2 text-xs font-medium text-muted-foreground hover:text-foreground"
              >
                {picker} · out
              </button>
            )}
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-3 pt-4 pb-24 sm:px-5 sm:pb-8">
        <Suspense fallback={<p className="text-muted-foreground">Loading…</p>}>
          <Routes>
            <Route path="/" element={<Navigate to="/view" replace />} />
            <Route path="/picks" element={<MakePicks />} />
            <Route path="/view" element={<Field />} />
            {/* detail view, reached from a game row — deliberately not a tab */}
            <Route path="/game/:gameId" element={<GameDetail />} />
            <Route path="/survivor" element={<Survivor />} />
            <Route path="/standings" element={<Standings />} />
            <Route path="/spreads" element={<ManageSpreads />} />
            <Route path="/ledger" element={<Ledger />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/help" element={<Help />} />
          </Routes>
        </Suspense>
      </main>

      {/* Thumb-reachable on a phone, gone on a laptop. */}
      <nav className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-card/95 backdrop-blur sm:hidden">
        <div className="flex pb-[env(safe-area-inset-bottom)]">
          {tabs.map((t) => (
            <NavLink
              key={t.to}
              to={t.to}
              className={({ isActive }) =>
                `flex flex-1 flex-col items-center gap-0.5 py-2.5 text-[11px] font-medium transition-colors ${
                  isActive ? 'text-primary' : 'text-muted-foreground'
                }`
              }
            >
              <t.icon className="size-5" />
              {t.label}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  )
}

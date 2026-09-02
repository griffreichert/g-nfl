import { Suspense, lazy, useEffect, useRef, useState } from 'react'
import { NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import {
  ChartColumn,
  CircleQuestionMark,
  ClipboardCheck,
  Ellipsis,
  LineChart,
  LogIn,
  LogOut,
  Ruler,
  Scale,
  Skull,
  Users,
} from 'lucide-react'
import ThemeToggle from './components/ThemeToggle'
import RequireAuth from './components/RequireAuth'
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
const SignInPage = lazy(() => import('./pages/SignInPage'))

/**
 * The week's order, and which half of it a tab belongs to (#124).
 *
 * "build" is what you do — pick, argue, enter the pool's numbers. "read" is
 * what you look at afterwards. They used to be interleaved, with Lines (a
 * Saturday chore) stranded between Standings and Ledger.
 */
const tabs = [
  { to: '/picks', label: 'Picks', icon: ClipboardCheck, group: 'build', bar: true },
  { to: '/view', label: 'Team', icon: Users, group: 'build', bar: true },
  { to: '/survivor', label: 'Survivor', icon: Skull, group: 'build', bar: true },
  { to: '/spreads', label: 'Lines', icon: Ruler, group: 'build', bar: false },
  { to: '/standings', label: 'Standings', icon: LineChart, group: 'read', bar: true },
  { to: '/ledger', label: 'Ledger', icon: Scale, group: 'read', bar: false },
  { to: '/analytics', label: 'Analytics', icon: ChartColumn, group: 'read', bar: false },
] as const

/** Bottom bar tabs, and everything else behind More. Seven 53px targets on a
 *  375px phone was under the size a thumb can hit. */
const barTabs = tabs.filter((t) => t.bar)
const overflow = tabs.filter((t) => !t.bar)

const navClass = (isActive: boolean) =>
  `flex h-9 items-center rounded-md px-3 text-sm font-medium transition-colors ${
    isActive
      ? 'bg-secondary text-foreground'
      : 'text-muted-foreground hover:bg-muted hover:text-foreground'
  }`

/** The overflow sheet on a phone. Closes on navigation and on outside taps. */
function MoreMenu() {
  const { pathname } = useLocation()
  // Stored with the route it was opened on, so navigating closes it without an
  // effect reaching in to set state after the fact.
  const [openAt, setOpenAt] = useState<string | null>(null)
  const open = openAt === pathname
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const away = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpenAt(null)
    }
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [open])

  const here = overflow.some((t) => t.to === pathname) || pathname === '/help'

  return (
    <div ref={ref} className="relative flex flex-1">
      {open && (
        <div className="absolute bottom-full right-1 mb-1 w-44 overflow-hidden rounded-lg border border-border bg-card shadow-lg">
          {[...overflow, { to: '/help', label: 'How this works', icon: CircleQuestionMark }].map(
            (t) => (
              <NavLink
                key={t.to}
                to={t.to}
                className={({ isActive }) =>
                  `flex items-center gap-2 px-3 py-2.5 text-sm font-medium ${
                    isActive ? 'text-primary' : 'text-foreground'
                  }`
                }
              >
                <t.icon className="size-4" />
                {t.label}
              </NavLink>
            )
          )}
        </div>
      )}
      <button
        onClick={() => setOpenAt(open ? null : pathname)}
        aria-expanded={open}
        aria-label="More pages"
        className={`flex flex-1 flex-col items-center gap-0.5 py-2.5 text-[11px] font-medium transition-colors ${
          here || open ? 'text-primary' : 'text-muted-foreground'
        }`}
      >
        <Ellipsis className="size-5" />
        More
      </button>
    </div>
  )
}

export default function App() {
  const { picker, logout } = useAuth()

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-20 border-b border-border bg-card/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-1 px-3 sm:px-5">
          <span className="mr-3 font-bold tracking-tight">
            no<span className="text-primary">·</span>homers
          </span>

          {/* laptop: inline tabs, build then read. mobile: the bottom bar owns
              navigation. */}
          <nav className="hidden items-center gap-1 sm:flex">
            {tabs
              .filter((t) => t.group === 'build')
              .map((t) => (
                <NavLink key={t.to} to={t.to} className={({ isActive }) => navClass(isActive)}>
                  {t.label}
                </NavLink>
              ))}
            <span className="mx-1.5 h-5 w-px bg-border" />
            {tabs
              .filter((t) => t.group === 'read')
              .map((t) => (
                <NavLink key={t.to} to={t.to} className={({ isActive }) => navClass(isActive)}>
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
                `hidden size-9 items-center justify-center rounded-md transition-colors sm:flex ${
                  isActive ? 'text-primary' : 'text-muted-foreground hover:text-foreground'
                }`
              }
            >
              <CircleQuestionMark className="size-5" />
            </NavLink>
            {/* Who the picks will be saved under. It was grey 12px next to a
                theme toggle, so the one thing on the page that decides where a
                submission lands was the easiest thing to miss. Signed out it
                was dead text, and the sign-in form could only be reached by
                walking into a gated page (#124). */}
            {picker ? (
              <span className="flex h-9 items-center gap-2 rounded-full border border-border bg-secondary py-1 pr-2 pl-1">
                <span className="flex size-7 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
                  {picker.slice(0, 1).toUpperCase()}
                </span>
                <span className="text-sm font-semibold">{picker}</span>
                <button
                  onClick={logout}
                  aria-label="Sign out"
                  title="Sign out"
                  className="text-muted-foreground hover:text-foreground"
                >
                  <LogOut className="size-4" />
                </button>
              </span>
            ) : (
              <NavLink
                to="/signin"
                className="flex h-9 items-center gap-1.5 rounded-full border border-border px-3 text-sm font-semibold hover:bg-muted"
              >
                <LogIn className="size-4" />
                Sign in
              </NavLink>
            )}
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-3 pt-4 pb-24 sm:px-5 sm:pb-8">
        <Suspense fallback={<p className="text-muted-foreground">Loading…</p>}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/signin" element={<SignInPage />} />
            <Route
              path="/picks"
              element={
                <RequireAuth>
                  <MakePicks />
                </RequireAuth>
              }
            />
            <Route
              path="/view"
              element={
                <RequireAuth>
                  <Field />
                </RequireAuth>
              }
            />
            {/* detail view, reached from a game row — deliberately not a tab */}
            <Route path="/game/:gameId" element={<GameDetail />} />
            <Route path="/survivor" element={<Survivor />} />
            <Route path="/standings" element={<Standings />} />
            <Route
              path="/spreads"
              element={
                <RequireAuth>
                  <ManageSpreads />
                </RequireAuth>
              }
            />
            <Route path="/ledger" element={<Ledger />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/help" element={<Help />} />
          </Routes>
        </Suspense>
      </main>

      {/* Thumb-reachable on a phone, gone on a laptop. */}
      <nav className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-card/95 backdrop-blur sm:hidden">
        <div className="flex pb-[env(safe-area-inset-bottom)]">
          {barTabs.map((t) => (
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
          <MoreMenu />
        </div>
      </nav>
    </div>
  )
}

/**
 * Where `/` goes. It used to redirect to the Team board, which is the Sunday
 * meeting page and gated, so a signed-out visitor's first screen was a login
 * box with nothing around it. Signed in, the weekday job is your own picks;
 * signed out, Standings explains itself and needs no session (#124).
 */
function Landing() {
  const { picker, checking } = useAuth()
  if (checking) return <p className="text-muted-foreground">Loading…</p>
  return <Navigate to={picker ? '/picks' : '/standings'} replace />
}

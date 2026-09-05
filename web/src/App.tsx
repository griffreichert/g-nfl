import { Suspense, lazy } from 'react'
import { NavLink, Route, Routes, useLocation } from 'react-router-dom'
import {
  ChartColumn,
  CircleQuestionMark,
  ClipboardCheck,
  LineChart,
  LogIn,
  LogOut,
  Skull,
} from 'lucide-react'
import ThemeToggle from './components/ThemeToggle'
import RequireAuth from './components/RequireAuth'
import { useAuth } from './hooks'

// Split per route so a page's charts and tables are fetched when someone opens
// it, not on first paint. Recharts and TanStack Table are most of the bundle.
const MakePicks = lazy(() => import('./pages/MakePicks'))
const Field = lazy(() => import('./pages/Field'))
const GameDetail = lazy(() => import('./pages/GameDetail'))
const Survivor = lazy(() => import('./pages/Survivor'))
const Performance = lazy(() => import('./pages/Performance'))
const Analytics = lazy(() => import('./pages/Analytics'))
const Help = lazy(() => import('./pages/Help'))
const SignInPage = lazy(() => import('./pages/SignInPage'))

/**
 * Four tabs, in one order, on every width (#135).
 *
 * Seven tabs needed a More menu on a phone, and the two halves of the site the
 * seven were split into — build and read — turned out to be one job each.
 * Team, Standings and Ledger all answered "how is the room doing", so they are
 * one Performance tab. Lines was a Saturday chore in the navigation all week
 * and now lives behind a toggle on the board. Picks is a button on the board,
 * because you do it once and then you are done.
 *
 * Make Picks is the home page and the only gated tab: it is where the week
 * starts, and it was sitting second behind a page you visit once.
 */
const TAB_ICONS = [
  { key: 'picks', label: 'Make Picks', icon: ClipboardCheck },
  { key: 'survivor', label: 'Survivor', icon: Skull },
  { key: 'performance', label: 'Performance', icon: LineChart },
  { key: 'analytics', label: 'Analytics', icon: ChartColumn },
] as const

/**
 * The season/week a URL names, read out of the path rather than component
 * state because the nav bar sits above every route and can't call
 * `useParams` on one. Carrying it into the next tab's link is what makes
 * "I'm looking at 2025 on Picks" survive a click to Analytics.
 */
function currentSeasonWeek(pathname: string) {
  const weekly = pathname.match(/^\/(?:picks|survivor)\/(\d+)(?:\/week\/(\d+))?/)
  if (weekly) return { season: Number(weekly[1]), week: weekly[2] ? Number(weekly[2]) : undefined }
  const seasonOnly = pathname.match(/^\/(?:performance|analytics)\/(\d+)/)
  if (seasonOnly) return { season: Number(seasonOnly[1]), week: undefined }
  return { season: undefined, week: undefined }
}

const navClass = (isActive: boolean) =>
  `flex h-9 items-center rounded-md px-3 text-sm font-medium transition-colors ${
    isActive
      ? 'bg-secondary text-foreground'
      : 'text-muted-foreground hover:bg-muted hover:text-foreground'
  }`

export default function App() {
  const { picker, logout } = useAuth()
  const { season, week } = currentSeasonWeek(useLocation().pathname)
  const tabs = [
    {
      to: season && week ? `/picks/${season}/week/${week}` : season ? `/picks/${season}` : '/picks',
      ...TAB_ICONS[0],
    },
    {
      to:
        season && week
          ? `/survivor/${season}/week/${week}`
          : season
            ? `/survivor/${season}`
            : '/survivor',
      ...TAB_ICONS[1],
    },
    { to: season ? `/performance/${season}` : '/performance', ...TAB_ICONS[2] },
    { to: season ? `/analytics/${season}` : '/analytics', ...TAB_ICONS[3] },
  ]

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-20 border-b border-border bg-card/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-1 px-3 sm:px-5">
          <span className="mr-3 font-bold tracking-tight">
            no<span className="text-primary">·</span>homers
          </span>

          {/* laptop: inline tabs. phone: the bottom bar owns navigation. */}
          <nav className="hidden items-center gap-1 sm:flex">
            {tabs.map((t) => (
              <NavLink
                key={t.to}
                to={t.to}
                end
                className={({ isActive }) => navClass(isActive)}
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
            {/* Home is the board. Bare, season-only, and full forms all
                render it: useSeasonWeekRoute resolves whichever is missing
                and settles the address bar on the explicit one (#126
                follow-up). Gated, so a signed-out visitor lands on /signin
                with where they were going kept in state. */}
            <Route
              path="/picks"
              element={
                <RequireAuth>
                  <Field />
                </RequireAuth>
              }
            />
            <Route
              path="/picks/:season"
              element={
                <RequireAuth>
                  <Field />
                </RequireAuth>
              }
            />
            <Route
              path="/picks/:season/week/:week"
              element={
                <RequireAuth>
                  <Field />
                </RequireAuth>
              }
            />
            <Route path="/signin" element={<SignInPage />} />
            {/* Off the navigation, reached from the button on the board.
                Making your own picks is a job you do once a week (#135). */}
            <Route
              path="/picks/submit"
              element={
                <RequireAuth>
                  <MakePicks />
                </RequireAuth>
              }
            />
            <Route
              path="/picks/:season/week/:week/submit"
              element={
                <RequireAuth>
                  <MakePicks />
                </RequireAuth>
              }
            />
            {/* detail view, reached from a game row — deliberately not a tab */}
            <Route path="/game/:gameId" element={<GameDetail />} />
            <Route path="/survivor" element={<Survivor />} />
            <Route path="/survivor/:season" element={<Survivor />} />
            <Route path="/survivor/:season/week/:week" element={<Survivor />} />
            <Route path="/performance" element={<Performance />} />
            <Route path="/performance/:season" element={<Performance />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/analytics/:season" element={<Analytics />} />
            <Route path="/help" element={<Help />} />
          </Routes>
        </Suspense>
      </main>

      {/* Thumb-reachable on a phone, gone on a laptop. Four 93px targets on a
          375px screen, where seven were 53px and needed a More menu. */}
      <nav className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-card/95 backdrop-blur sm:hidden">
        <div className="flex pb-[env(safe-area-inset-bottom)]">
          {tabs.map((t) => (
            <NavLink
              key={t.to}
              to={t.to}
              end
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

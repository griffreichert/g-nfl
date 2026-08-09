import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { ChartColumn, CircleQuestionMark, ClipboardCheck, LineChart, Ruler, Users } from 'lucide-react'
import ThemeToggle from './components/ThemeToggle'
import MakePicks from './pages/MakePicks'
import Field from './pages/Field'
import ManageSpreads from './pages/ManageSpreads'
import Standings from './pages/Standings'
import Analytics from './pages/Analytics'
import Help from './pages/Help'

const tabs = [
  { to: '/picks', label: 'Picks', icon: ClipboardCheck },
  { to: '/view', label: 'Team', icon: Users },
  { to: '/standings', label: 'Standings', icon: LineChart },
  { to: '/spreads', label: 'Lines', icon: Ruler },
  { to: '/analytics', label: 'Analytics', icon: ChartColumn },
]

export default function App() {
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
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-3 pt-4 pb-24 sm:px-5 sm:pb-8">
        <Routes>
          <Route path="/" element={<Navigate to="/view" replace />} />
          <Route path="/picks" element={<MakePicks />} />
          <Route path="/view" element={<Field />} />
          <Route path="/standings" element={<Standings />} />
          <Route path="/spreads" element={<ManageSpreads />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/help" element={<Help />} />
        </Routes>
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

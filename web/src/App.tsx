import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import ThemeToggle from './components/ThemeToggle'
import MakePicks from './pages/MakePicks'
import Field from './pages/Field'
import ManageSpreads from './pages/ManageSpreads'
import Standings from './pages/Standings'

const tabs = [
  { to: '/picks', label: '🎯 Make Picks' },
  { to: '/view', label: '🔍 Field' },
  { to: '/standings', label: '🏆 Standings' },
  { to: '/spreads', label: '⚙️ Spreads' },
]

export default function App() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <nav className="bg-card border-b border-border px-4 py-2 flex gap-1 sm:gap-2 items-center sticky top-0 z-10">
        <span className="font-bold mr-2 hidden sm:inline">no-homers</span>
        {tabs.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            className={({ isActive }) =>
              `px-3 py-1.5 rounded-md text-sm font-medium ${
                isActive
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-muted'
              }`
            }
          >
            {t.label}
          </NavLink>
        ))}
        <span className="ml-auto">
          <ThemeToggle />
        </span>
      </nav>
      <main className="max-w-3xl mx-auto px-2 sm:px-4 py-4">
        <Routes>
          <Route path="/" element={<Navigate to="/picks" replace />} />
          <Route path="/picks" element={<MakePicks />} />
          <Route path="/view" element={<Field />} />
          <Route path="/standings" element={<Standings />} />
          <Route path="/spreads" element={<ManageSpreads />} />
        </Routes>
      </main>
    </div>
  )
}

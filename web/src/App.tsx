import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import MakePicks from './pages/MakePicks'
import ViewPicks from './pages/ViewPicks'
import ManageSpreads from './pages/ManageSpreads'

const tabs = [
  { to: '/picks', label: '🎯 Make Picks' },
  { to: '/view', label: '🔍 View Picks' },
  { to: '/spreads', label: '⚙️ Spreads' },
]

export default function App() {
  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <nav className="bg-white border-b border-gray-200 px-4 py-2 flex gap-1 sm:gap-2 items-center sticky top-0 z-10">
        <span className="font-bold mr-2 hidden sm:inline">no-homers</span>
        {tabs.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            className={({ isActive }) =>
              `px-3 py-1.5 rounded-md text-sm font-medium ${
                isActive ? 'bg-green-600 text-white' : 'text-gray-600 hover:bg-gray-100'
              }`
            }
          >
            {t.label}
          </NavLink>
        ))}
      </nav>
      <main className="max-w-3xl mx-auto px-2 sm:px-4 py-4">
        <Routes>
          <Route path="/" element={<Navigate to="/picks" replace />} />
          <Route path="/picks" element={<MakePicks />} />
          <Route path="/view" element={<ViewPicks />} />
          <Route path="/spreads" element={<ManageSpreads />} />
        </Routes>
      </main>
    </div>
  )
}

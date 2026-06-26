import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { useConfig, useSeasonWeek } from '../hooks'
import type { PickerStanding, StandingsResponse } from '../types'

const PICKER_COLORS = [
  '#16a34a', '#2563eb', '#dc2626', '#9333ea', '#ea580c',
  '#0891b2', '#ca8a04', '#db2777',
]

const fmtPct = (p: number | null) => (p === null ? '—' : `${(p * 100).toFixed(1)}%`)
const fmtUnits = (u: number) => `${u > 0 ? '+' : ''}${u.toFixed(2)}`
const fmtRecord = (r: { wins: number; losses: number; pushes: number }) =>
  `${r.wins}-${r.losses}${r.pushes ? `-${r.pushes}` : ''}`

/** Cumulative units by week, one line per picker, zero line dashed */
function TrendChart({ standings }: { standings: PickerStanding[] }) {
  const series = standings.filter((s) => s.weekly.length > 0)
  const { weeks, lo, hi } = useMemo(() => {
    const allWeeks = series.flatMap((s) => s.weekly.map((w) => w.week))
    const allUnits = series.flatMap((s) => s.weekly.map((w) => w.cum_units))
    return {
      weeks: [...new Set(allWeeks)].sort((a, b) => a - b),
      lo: Math.min(0, ...allUnits),
      hi: Math.max(0, ...allUnits),
    }
  }, [series])

  if (series.length === 0 || weeks.length < 2) return null

  const W = 640
  const H = 220
  const PAD = { top: 10, right: 8, bottom: 22, left: 36 }
  const x = (week: number) =>
    PAD.left + ((week - weeks[0]) / (weeks[weeks.length - 1] - weeks[0])) * (W - PAD.left - PAD.right)
  const y = (units: number) =>
    hi === lo ? H / 2 : PAD.top + ((hi - units) / (hi - lo)) * (H - PAD.top - PAD.bottom)

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-3 mb-4">
      <h2 className="font-bold mb-2 text-sm">Cumulative units by week (1u per pick at -110)</h2>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        <line x1={PAD.left} x2={W - PAD.right} y1={y(0)} y2={y(0)} stroke="#9ca3af" strokeDasharray="4 3" />
        <text x={4} y={y(0) + 4} fontSize={11} fill="#6b7280">0u</text>
        {weeks.map((w) => (
          <text key={w} x={x(w)} y={H - 6} fontSize={10} fill="#6b7280" textAnchor="middle">
            {w}
          </text>
        ))}
        {series.map((s, i) => {
          const color = PICKER_COLORS[i % PICKER_COLORS.length]
          const pts = s.weekly.map((w) => `${x(w.week)},${y(w.cum_units)}`).join(' ')
          const last = s.weekly[s.weekly.length - 1]
          return (
            <g key={s.picker}>
              <polyline points={pts} fill="none" stroke={color} strokeWidth={2} />
              <circle cx={x(last.week)} cy={y(last.cum_units)} r={3} fill={color} />
            </g>
          )
        })}
      </svg>
      <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1 text-xs">
        {series.map((s, i) => (
          <span key={s.picker} className="flex items-center gap-1">
            <span className="w-3 h-0.5 inline-block" style={{ background: PICKER_COLORS[i % PICKER_COLORS.length] }} />
            {s.picker}
          </span>
        ))}
      </div>
    </div>
  )
}

export default function Standings() {
  const { config, error: configError } = useConfig()
  const { season, setSeason, seasons } = useSeasonWeek(config)
  const [data, setData] = useState<StandingsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (season === null) return
    let cancelled = false
    api
      .standings(season)
      .then((d) => {
        if (cancelled) return
        setData(d)
        setError(null)
      })
      .catch((e) => {
        if (!cancelled) setError(String(e))
      })
    return () => {
      cancelled = true
    }
  }, [season])

  if (configError) return <p className="text-red-600">Failed to load config: {configError}</p>
  if (!config || season === null) return <p>Loading…</p>

  const breakEven = data ? data.break_even_pct : 110 / 210

  return (
    <div>
      <h1 className="text-2xl font-bold mb-3">🏆 Standings</h1>

      <div className="flex gap-2 items-center mb-4">
        <select value={season} onChange={(e) => setSeason(Number(e.target.value))} className="border rounded-md px-2 py-1.5 bg-white">
          {seasons.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        {data?.graded_through_week != null && (
          <span className="text-sm text-gray-500">results through week {data.graded_through_week}</span>
        )}
      </div>

      {error && <p className="text-red-600">{error}</p>}
      {!error && data?.season !== season && <p>Loading…</p>}

      {!error && data?.season === season && (
        <>
          <TrendChart standings={data.standings} />

          <div className="bg-white rounded-lg border border-gray-200 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-200">
                  <th className="px-3 py-2">Picker</th>
                  <th className="px-3 py-2">ATS</th>
                  <th className="px-3 py-2">Win%</th>
                  <th className="px-3 py-2">Units</th>
                  <th className="px-3 py-2">⭐️ Best bet</th>
                  <th className="px-3 py-2">💀 Survivor</th>
                  <th className="px-3 py-2">🐶 Dog</th>
                  <th className="px-3 py-2">🌙 MNF</th>
                </tr>
              </thead>
              <tbody>
                {data.standings.map((s) => (
                  <tr key={s.picker} className="border-b border-gray-100 last:border-0">
                    <td className="px-3 py-2 font-bold">{s.picker}</td>
                    <td className="px-3 py-2">{fmtRecord(s.ats)}{s.ats.pending > 0 && <span className="text-gray-400"> ({s.ats.pending} pend)</span>}</td>
                    <td className={`px-3 py-2 ${s.ats.win_pct !== null ? (s.ats.win_pct > breakEven ? 'text-green-600' : 'text-red-600') : ''}`}>
                      {fmtPct(s.ats.win_pct)}
                    </td>
                    <td className={`px-3 py-2 font-medium ${s.units > 0 ? 'text-green-600' : s.units < 0 ? 'text-red-600' : ''}`}>
                      {fmtUnits(s.units)}
                    </td>
                    {(['best_bet', 'survivor', 'underdog', 'mnf'] as const).map((t) => (
                      <td key={t} className="px-3 py-2 text-gray-600">
                        {s.by_type[t] ? fmtRecord(s.by_type[t]) : '—'}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="text-xs text-gray-500 mt-2">
            ATS record covers regular + best bet picks, graded against the line at pick time.
            Break-even at -110 is {fmtPct(breakEven)}. Pushes excluded from win%.
          </p>
        </>
      )}
    </div>
  )
}

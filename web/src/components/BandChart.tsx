import { Bar, BarChart, Cell, LabelList, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from 'recharts'
import { BANDS } from '@/lib/consensus'

/**
 * Our 2025 ATS hit rate by spread size. The one cut in the data that was
 * significant at both tails, so it is the one chart on the page.
 */
export default function BandChart({ counts }: { counts: Record<string, number> }) {
  const data = BANDS.map((b) => ({
    label: b.label,
    pct: b.pct,
    n: b.n,
    tone: b.tone,
    picked: counts[b.label] ?? 0,
  }))

  return (
    <div className="h-40 w-full">
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 16, right: 8, bottom: 0, left: -22 }}>
          <XAxis
            dataKey="label"
            tickLine={false}
            axisLine={false}
            tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }}
          />
          <YAxis
            domain={[30, 62]}
            ticks={[40, 50, 60]}
            tickLine={false}
            axisLine={false}
            tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
            tickFormatter={(v) => `${v}%`}
          />
          <ReferenceLine y={50} stroke="var(--border)" strokeDasharray="3 3" />
          <Bar dataKey="pct" radius={[4, 4, 0, 0]} isAnimationActive={false}>
            {data.map((d) => (
              <Cell key={d.label} fill={d.tone === 'good' ? 'var(--win)' : 'var(--loss)'} />
            ))}
            <LabelList
              dataKey="pct"
              position="top"
              formatter={(v) => `${Number(v).toFixed(1)}%`}
              fill="var(--foreground)"
              fontSize={11}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

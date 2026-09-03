import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './ui/select'

type Props = {
  title: string
  season: number | null
  seasons: number[]
  onSeason: (season: number) => void
  /** Omit the week trio on pages that read a whole season (Standings, Analytics). */
  week?: number | null
  weeks?: number[]
  onWeek?: (week: number) => void
}

/**
 * Title plus the season/week selectors every page carries.
 *
 * The five pages had this markup copied verbatim, so the widths and gaps only
 * matched by luck. Keeping it in one place is what stops them drifting.
 */
export default function PageHeader({
  title,
  season,
  seasons,
  onSeason,
  week,
  weeks,
  onWeek,
}: Props) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <h1 className="mr-auto text-xl font-bold sm:text-2xl">{title}</h1>

      <Select value={String(season)} onValueChange={(v) => onSeason(Number(v))}>
        <SelectTrigger size="sm" className="w-24">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {seasons.map((s) => (
            <SelectItem key={s} value={String(s)}>
              {s}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {onWeek && weeks && (
        <Select value={String(week)} onValueChange={(v) => onWeek(Number(v))}>
          <SelectTrigger size="sm" className="w-28">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {weeks.map((w) => (
              <SelectItem key={w} value={String(w)}>
                Week {w}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
    </div>
  )
}

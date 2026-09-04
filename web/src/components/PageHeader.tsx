import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from './ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './ui/select'

type Props = {
  title: string
  /** Omit the season selector on a page whose week is fixed by how it was reached (Picks). */
  season?: number | null
  seasons?: number[]
  onSeason?: (season: number) => void
  /** Omit the week trio on pages that read a whole season (Standings, Analytics). */
  week?: number | null
  weeks?: number[]
  onWeek?: (week: number) => void
}

/**
 * Title plus the season/week selectors most pages carry.
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

      {onSeason && seasons && (
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
      )}

      {onWeek && weeks && (
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="icon-sm"
            aria-label="Previous week"
            disabled={week == null || weeks.indexOf(week) <= 0}
            onClick={() => week != null && onWeek(weeks[weeks.indexOf(week) - 1])}
          >
            <ChevronLeft className="size-4" />
          </Button>
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
          <Button
            variant="outline"
            size="icon-sm"
            aria-label="Next week"
            disabled={week == null || weeks.indexOf(week) >= weeks.length - 1}
            onClick={() => week != null && onWeek(weeks[weeks.indexOf(week) + 1])}
          >
            <ChevronRight className="size-4" />
          </Button>
        </div>
      )}
    </div>
  )
}

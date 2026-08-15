import type {
  AnalyticsResponse,
  AppConfig,
  GameDetail,
  GameLine,
  Pick,
  PickRecord,
  StandingsResponse,
  WeeksResponse,
} from './types'

// In production VITE_API_URL points at the Render backend; in dev the Vite
// proxy forwards /api to localhost:8000.
const BASE = import.meta.env.VITE_API_URL ?? ''

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

async function send<T>(method: string, path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

export const api = {
  config: () => get<AppConfig>('/api/config'),
  weeks: (season: number) => get<WeeksResponse>(`/api/weeks?season=${season}`),
  lines: (season: number, week: number) =>
    get<GameLine[]>(`/api/lines?season=${season}&week=${week}`),
  picks: (season: number, week: number, picker?: string) =>
    get<PickRecord[]>(
      `/api/picks?season=${season}&week=${week}${picker ? `&picker=${encodeURIComponent(picker)}` : ''}`
    ),
  game: (gameId: string) => get<GameDetail>(`/api/games/${encodeURIComponent(gameId)}`),
  standings: (season: number) => get<StandingsResponse>(`/api/standings?season=${season}`),
  analytics: (season: number) => get<AnalyticsResponse>(`/api/analytics?season=${season}`),
  savePicks: (season: number, week: number, picker: string, picks: Pick[]) =>
    send<{ saved: number }>('POST', '/api/picks', { season, week, picker, picks }),
  updatePoolSpread: (season: number, week: number, game_id: string, spread: number) =>
    send<{ success: boolean }>('PUT', '/api/pool-spreads', { season, week, game_id, spread }),
}

export const teamLogo = (team: string) =>
  `https://a.espncdn.com/i/teamlogos/nfl/500/${team.toLowerCase()}.png`

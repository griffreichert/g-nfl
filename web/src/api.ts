import type {
  AnalyticsResponse,
  AppConfig,
  GameDetail,
  GameLine,
  GuardrailsResponse,
  LedgerResponse,
  LoginResponse,
  Pick,
  PickRecord,
  StandingsResponse,
  WeeksResponse,
} from './types'

// In production VITE_API_URL points at the Render backend; in dev the Vite
// proxy forwards /api to localhost:8000.
const BASE = import.meta.env.VITE_API_URL ?? ''

const TOKEN_KEY = 'nohomers.token'

export const token = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

/** Bearer header when we hold a token, nothing when we do not. */
const authHeaders = (): Record<string, string> => {
  const t = token.get()
  return t ? { Authorization: `Bearer ${t}` } : {}
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { headers: authHeaders() })
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

async function send<T>(method: string, path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

export const api = {
  login: (picker: string, passphrase: string) =>
    send<LoginResponse>('POST', '/api/auth/login', { picker, passphrase }),
  me: () => get<LoginResponse>('/api/auth/me'),
  config: (picker?: string) =>
    get<AppConfig>(
      `/api/config${picker ? `?picker=${encodeURIComponent(picker)}` : ''}`
    ),
  weeks: (season: number) => get<WeeksResponse>(`/api/weeks?season=${season}`),
  lines: (season: number, week: number) =>
    get<GameLine[]>(`/api/lines?season=${season}&week=${week}`),
  guardrails: (season: number, week?: number) =>
    get<GuardrailsResponse>(
      `/api/guardrails?season=${season}${week !== undefined ? `&week=${week}` : ''}`
    ),
  picks: (season: number, week: number, picker?: string) =>
    get<PickRecord[]>(
      `/api/picks?season=${season}&week=${week}${picker ? `&picker=${encodeURIComponent(picker)}` : ''}`
    ),
  game: (gameId: string) => get<GameDetail>(`/api/games/${encodeURIComponent(gameId)}`),
  ledger: (season: number) => get<LedgerResponse>(`/api/ledger?season=${season}`),
  standings: (season: number) => get<StandingsResponse>(`/api/standings?season=${season}`),
  analytics: (season: number) => get<AnalyticsResponse>(`/api/analytics?season=${season}`),
  // `picker` is read from the token server-side. The body's copy is ignored
  // except for TEAM, the entry the room submits together off the board.
  savePicks: (season: number, week: number, picks: Pick[], picker?: string) =>
    send<{ saved: number }>('POST', '/api/picks', { season, week, picker, picks }),
  updatePoolSpread: (season: number, week: number, game_id: string, spread: number) =>
    send<{ success: boolean }>('PUT', '/api/pool-spreads', { season, week, game_id, spread }),
}

export const teamLogo = (team: string) =>
  `https://a.espncdn.com/i/teamlogos/nfl/500/${team.toLowerCase()}.png`

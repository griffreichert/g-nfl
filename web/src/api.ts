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
  SurvivorBelief,
  SurvivorResponse,
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

/**
 * The answers that do not change while you use the site (#124).
 *
 * Every fetch lived in a `useEffect`, and a route change unmounts the page
 * holding the result, so config, the week list and the guardrail fit were
 * re-fetched on every navigation and nothing painted until they landed. The
 * promise is cached rather than the value, so two pages mounting at once share
 * one request. A failed request is dropped so the next mount retries it.
 */
const cache = new Map<string, Promise<unknown>>()

function stable<T>(path: string): Promise<T> {
  const hit = cache.get(path)
  if (hit) return hit as Promise<T>
  const p = get<T>(path).catch((e) => {
    cache.delete(path)
    throw e
  })
  cache.set(path, p)
  return p
}

/**
 * Drop the cache after a write. Saving a survivor pick changes the used-teams
 * list inside /api/config, so a stale copy would offer a team back that was
 * spent a second ago.
 */
export const invalidate = () => cache.clear()

export const api = {
  login: (picker: string, passphrase: string) =>
    send<LoginResponse>('POST', '/api/auth/login', { picker, passphrase }),
  me: () => stable<LoginResponse>('/api/auth/me'),
  config: (picker?: string) =>
    stable<AppConfig>(
      `/api/config${picker ? `?picker=${encodeURIComponent(picker)}` : ''}`
    ),
  weeks: (season: number) => stable<WeeksResponse>(`/api/weeks?season=${season}`),
  lines: (season: number, week: number) =>
    get<GameLine[]>(`/api/lines?season=${season}&week=${week}`),
  guardrails: (season: number, week?: number) =>
    stable<GuardrailsResponse>(
      `/api/guardrails?season=${season}${week !== undefined ? `&week=${week}` : ''}`
    ),
  // Leave `week` off for the whole season, which is what the board wants: it
  // used to ask for eighteen weeks in eighteen requests to find voting blocs.
  picks: (season: number, week?: number, picker?: string) =>
    get<PickRecord[]>(
      `/api/picks?season=${season}${week !== undefined ? `&week=${week}` : ''}${picker ? `&picker=${encodeURIComponent(picker)}` : ''}`
    ),
  game: (gameId: string) => get<GameDetail>(`/api/games/${encodeURIComponent(gameId)}`),
  ledger: (season: number) => get<LedgerResponse>(`/api/ledger?season=${season}`),
  standings: (season: number) => get<StandingsResponse>(`/api/standings?season=${season}`),
  analytics: (season: number) => get<AnalyticsResponse>(`/api/analytics?season=${season}`),
  // Pins ride the query string because a plan is a sketch: only a submitted
  // pick spends a team, so nothing about a plan is worth a table (#72).
  survivor: (
    season: number,
    week: number,
    picker?: string,
    pins?: Record<number, string>,
    rank?: number,
    doubts?: SurvivorBelief[]
  ) => {
    const q = new URLSearchParams({ season: String(season), week: String(week) })
    if (picker) q.set('picker', picker)
    const pairs = Object.entries(pins ?? {}).map(([w, t]) => `${w}:${t}`)
    if (pairs.length) q.set('pins', pairs.join(','))
    if (rank !== undefined) q.set('rank', String(rank))
    // Sent only while an edit is unsaved, or for a viewer with no entry to
    // save against — a signed-in picker's beliefs are read from the table.
    if (doubts?.length)
      q.set('doubts', doubts.map((b) => `${b.team}:${b.confidence}`).join(','))
    return get<SurvivorResponse>(`/api/survivor?${q}`)
  },
  beliefs: (season: number, picker?: string) => {
    const q = new URLSearchParams({ season: String(season) })
    if (picker) q.set('picker', picker)
    return get<SurvivorBelief[]>(`/api/survivor/beliefs?${q}`)
  },
  // Written under the token's picker: beliefs are what makes two entries
  // diverge on the same board, so they have to belong to somebody.
  saveBeliefs: (season: number, beliefs: SurvivorBelief[]) =>
    send<{ saved: number }>('PUT', '/api/survivor/beliefs', { season, beliefs }),
  // `picker` is read from the token server-side. The body's copy is ignored
  // except for TEAM, the entry the room submits together off the board.
  savePicks: async (season: number, week: number, picks: Pick[], picker?: string) => {
    const r = await send<{ saved: number }>('POST', '/api/picks', {
      season,
      week,
      picker,
      picks,
    })
    invalidate()
    return r
  },
  updatePoolSpread: (season: number, week: number, game_id: string, spread: number) =>
    send<{ success: boolean }>('PUT', '/api/pool-spreads', { season, week, game_id, spread }),
}

export const teamLogo = (team: string) =>
  `https://a.espncdn.com/i/teamlogos/nfl/500/${team.toLowerCase()}.png`

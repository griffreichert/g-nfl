import { createContext, useContext } from 'react'

export type Auth = {
  /** Who the session belongs to, null when signed out. */
  picker: string | null
  /** True while an existing token is being verified. */
  checking: boolean
  login: (who: string, passphrase: string) => Promise<void>
  logout: () => void
}

export const AuthContext = createContext<Auth | null>(null)

/** The one session, from anywhere under `AuthProvider`. */
export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth outside AuthProvider')
  return ctx
}

import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { api, token } from './api'
import { AuthContext, type Auth } from './auth-context'

/**
 * One session for the whole app (#124).
 *
 * This used to be a plain hook, so the header and every gated page each held
 * their own copy of "who is signed in". Signing in on Picks left the header
 * saying signed out until a reload, signing out from the header left the page
 * underneath still rendering, and every navigation re-verified the same token
 * against /api/auth/me before it would paint.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [picker, setPicker] = useState<string | null>(null)
  // No token means nothing to check, so the gate opens on the first render
  // rather than after an effect has run and set state again.
  const [checking, setChecking] = useState(() => token.get() !== null)

  useEffect(() => {
    if (!token.get()) return
    let live = true
    api
      .me()
      .then((r) => live && setPicker(r.picker))
      // an expired or tampered token is the same as no token
      .catch(() => {
        token.clear()
        if (live) setPicker(null)
      })
      .finally(() => live && setChecking(false))
    return () => {
      live = false
    }
  }, [])

  const value = useMemo<Auth>(
    () => ({
      picker,
      checking,
      login: async (who, passphrase) => {
        const r = await api.login(who, passphrase)
        token.set(r.token)
        setPicker(r.picker)
      },
      logout: () => {
        token.clear()
        setPicker(null)
      },
    }),
    [picker, checking]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

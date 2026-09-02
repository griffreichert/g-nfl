import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../hooks'
import { Loading } from './PageState'

/**
 * One place that decides a page needs a session (#124).
 *
 * Picks, Team and Lines each carried their own copy of this: a `checking`
 * branch, a config fetch for the name list, and a bare `<SignIn />` return. The
 * form appeared as a wall you walked into, with no way back to where you were
 * going. Now the route sends you to /signin and /signin sends you back.
 */
export default function RequireAuth({ children }: { children: ReactNode }) {
  const { picker, checking } = useAuth()
  const location = useLocation()

  if (checking) return <Loading />
  if (!picker) return <Navigate to="/signin" state={{ from: location.pathname }} replace />
  return <>{children}</>
}

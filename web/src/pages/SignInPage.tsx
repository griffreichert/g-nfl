import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import SignIn from '@/components/SignIn'
import { Loading } from '@/components/PageState'
import { useAuth, useConfig } from '../hooks'

/**
 * Sign-in as a place you can go, rather than a wall you hit (#124).
 *
 * Returns you to the page that sent you here, so following a link into Picks
 * and signing in lands on Picks.
 */
export default function SignInPage() {
  const { picker, checking, login } = useAuth()
  const { config, error } = useConfig()
  const navigate = useNavigate()
  const from = (useLocation().state as { from?: string } | null)?.from ?? '/picks'

  if (checking || (!config && !error)) return <Loading />
  if (picker) return <Navigate to={from} replace />

  return (
    <div className="flex flex-col items-center gap-3">
      <SignIn
        pickers={config?.pickers ?? []}
        onSignIn={async (who, passphrase) => {
          await login(who, passphrase)
          navigate(from, { replace: true })
        }}
      />
      <p className="text-xs text-muted-foreground">
        Not sure what any of this is?{' '}
        <Link to="/help" className="text-primary underline-offset-4 hover:underline">
          How this works
        </Link>
      </p>
    </div>
  )
}

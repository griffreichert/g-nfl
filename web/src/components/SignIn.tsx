import { useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

/**
 * Name plus a four-digit PIN (#60).
 *
 * The name used to be enough, and the API believed it, so anyone could submit
 * as anyone. A ledger of who picked what is only worth keeping if the entries
 * are attributable.
 */
export default function SignIn({
  pickers,
  onSignIn,
}: {
  pickers: string[]
  onSignIn: (picker: string, pin: string) => Promise<void>
}) {
  const [picker, setPicker] = useState('')
  const [pin, setPin] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!picker || !pin) return
    setBusy(true)
    setError(null)
    try {
      await onSignIn(picker, pin)
    } catch {
      // the API gives the same answer for a wrong name and a wrong PIN
      setError('Wrong name or PIN.')
      setPin('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto mt-12 w-full max-w-xs rounded-lg border border-border bg-card p-4">
      <h1 className="mb-1 text-sm font-bold">Sign in</h1>
      <p className="mb-3 text-xs text-muted-foreground">
        Your picks are saved against whoever is signed in.
      </p>

      <div className="flex flex-col gap-2">
        <Select value={picker || undefined} onValueChange={setPicker}>
          <SelectTrigger size="sm" className="w-full">
            <SelectValue placeholder="Your name" />
          </SelectTrigger>
          <SelectContent>
            {pickers.map((p) => (
              <SelectItem key={p} value={p}>
                {p}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <input
          type="password"
          inputMode="numeric"
          autoComplete="current-password"
          placeholder="PIN"
          value={pin}
          onChange={(e) => setPin(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
          className="h-9 rounded-md border border-border bg-background px-3 text-sm"
        />

        {error && <p className="text-xs text-loss">{error}</p>}

        <Button size="sm" onClick={submit} disabled={busy || !picker || !pin}>
          {busy ? 'Checking…' : 'Sign in'}
        </Button>
      </div>
    </div>
  )
}

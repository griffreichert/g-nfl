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
 * One passphrase for the room, then say who you are (#60).
 *
 * Everyone in the pool is trusted, so the passphrase keeps the internet out and
 * the name is taken on trust. The session stays pinned to the name it signed in
 * with, which is what stops a stale tab saving one person's week under another.
 */
export default function SignIn({
  pickers,
  onSignIn,
}: {
  pickers: string[]
  onSignIn: (picker: string, passphrase: string) => Promise<void>
}) {
  const [picker, setPicker] = useState('')
  const [passphrase, setPassphrase] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!picker || !passphrase) return
    setBusy(true)
    setError(null)
    try {
      await onSignIn(picker, passphrase)
    } catch {
      setError('Wrong passphrase.')
      setPassphrase('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto mt-12 w-full max-w-xs rounded-lg border border-border bg-card p-4">
      <h1 className="mb-1 text-sm font-bold">Sign in</h1>
      <p className="mb-3 text-xs text-muted-foreground">
        Your picks are saved against whoever is signed in. Sessions last 30 days.
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
          autoComplete="current-password"
          placeholder="Passphrase"
          value={passphrase}
          onChange={(e) => setPassphrase(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
          className="h-9 rounded-md border border-border bg-background px-3 text-sm"
        />

        {error && <p className="text-xs text-loss">{error}</p>}

        <Button size="sm" onClick={submit} disabled={busy || !picker || !passphrase}>
          {busy ? 'Checking…' : 'Sign in'}
        </Button>
      </div>
    </div>
  )
}

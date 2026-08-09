import { useCallback, useEffect, useState } from 'react'

export type Theme = 'light' | 'dark' | 'system'

const KEY = 'theme'
const prefersDark = () => window.matchMedia('(prefers-color-scheme: dark)')

/** Stamp the resolved theme on <html>. Mirrors the boot script in index.html. */
function apply(theme: Theme) {
  const dark = theme === 'system' ? prefersDark().matches : theme === 'dark'
  document.documentElement.classList.toggle('dark', dark)
  document.documentElement.classList.toggle('light', !dark)
}

export function useTheme() {
  const [theme, set] = useState<Theme>(() => (localStorage.getItem(KEY) as Theme | null) ?? 'dark')

  useEffect(() => {
    apply(theme)
    if (theme !== 'system') return
    const mq = prefersDark()
    const onChange = () => apply('system')
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [theme])

  const setTheme = useCallback((next: Theme) => {
    localStorage.setItem(KEY, next)
    set(next)
  }, [])

  return { theme, setTheme }
}

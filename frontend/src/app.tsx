import { useEffect } from 'preact/hooks'
import { useSignal } from '@preact/signals'
import { AppShell } from './shell/AppShell'
import { BootSplash } from './shell/BootSplash'
import { ToastViewport } from './components/Toast'
import { initTheme } from './theme/manager'
import { initI18n } from './i18n'
import { initRouter } from './core/router'
import { health, startShellPolling } from './core/store'

export function App() {
  const booted = useSignal(false)

  useEffect(() => {
    initTheme()
    initI18n()
    initRouter()
    startShellPolling()
  }, [])

  // Enter the shell once the server is truly reachable (honest boot —
  // splash stays through offline with retry). Brief linger for brand beat.
  useEffect(
    () =>
      health.subscribe((h) => {
        if (h === 'online' && !booted.value) {
          window.setTimeout(() => {
            booted.value = true
          }, 500)
        }
      }),
    [],
  )

  return booted.value ? <AppShell /> : (
    <>
      <BootSplash />
      <ToastViewport />
    </>
  )
}

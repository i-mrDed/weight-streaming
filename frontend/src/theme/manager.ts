/* Theme manager (spec §4.2–4.3)
   - concrete theme id persisted in ws-theme (default classic-dark)
   - ws-theme-auto=1 → follow OS prefers-color-scheme across the aurora pair
   - particle kill-switch ws-particles (spec §5.2 Settings toggle)
   Applies via <html data-theme data-mode>; CSS tokens do the rest. */
import { signal, computed } from '@preact/signals'
import { DEFAULT_THEME, getTheme, isThemeId, THEMES } from './registry'

const LS_THEME = 'ws-theme'
const LS_AUTO = 'ws-theme-auto'
const LS_PARTICLES = 'ws-particles'
const LS_DENSITY = 'ws-density'

export type Density = 'comfortable' | 'compact'

function readInitialTheme(): string {
  try {
    const stored = localStorage.getItem(LS_THEME)
    if (stored && isThemeId(stored)) return stored
  } catch {
    /* private mode */
  }
  return DEFAULT_THEME
}

function readInitialAuto(): boolean {
  try {
    return localStorage.getItem(LS_AUTO) === '1'
  } catch {
    return false
  }
}

export const themeId = signal<string>(readInitialTheme())
export const autoMode = signal<boolean>(readInitialAuto())
export const particlesEnabled = signal<boolean>((() => {
  try {
    return localStorage.getItem(LS_PARTICLES) !== '0'
  } catch {
    return true
  }
})())

export const density = signal<Density>((() => {
  try {
    return localStorage.getItem(LS_DENSITY) === 'compact' ? 'compact' : 'comfortable'
  } catch {
    return 'comfortable'
  }
})())

const osLight = typeof window !== 'undefined' && window.matchMedia
  ? window.matchMedia('(prefers-color-scheme: light)')
  : null

export const systemMode = signal<'dark' | 'light'>(osLight?.matches ? 'light' : 'dark')
if (osLight) {
  const onChange = (e: MediaQueryListEvent) => {
    systemMode.value = e.matches ? 'light' : 'dark'
  }
  osLight.addEventListener?.('change', onChange)
}

/** The theme actually rendered (auto resolves across the aurora pair) */
export const resolvedThemeId = computed(() => {
  if (autoMode.value) {
    return systemMode.value === 'light' ? 'aurora-light' : 'aurora-dark'
  }
  return themeId.value
})

export const resolvedTheme = computed(() => getTheme(resolvedThemeId.value) ?? THEMES[0])

/** Particles live only when: theme has them, user hasn't killed them, and
    the browser doesn't request reduced motion (canvas also self-gates on
    visibility + battery — spec §5.2). */
export const particlesActive = computed(() => {
  if (!particlesEnabled.value) return false
  if (resolvedTheme.value.particles !== 'constellation') return false
  if (typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
    return false
  }
  return true
})

function persist(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch {
    /* non-fatal */
  }
}

export function applyTheme() {
  const theme = resolvedTheme.value
  const el = document.documentElement
  el.setAttribute('data-theme', theme.id)
  el.setAttribute('data-mode', theme.mode)
  el.setAttribute('data-density', density.value)
  el.style.backgroundColor = '' // hand back to CSS tokens
}

export function setTheme(id: string) {
  if (!isThemeId(id)) return
  autoMode.value = false
  persist(LS_AUTO, null)
  themeId.value = id
  persist(LS_THEME, id)
  applyTheme()
}

export function setAutoMode(on: boolean) {
  autoMode.value = on
  persist(LS_AUTO, on ? '1' : null)
  if (on) persist(LS_THEME, null) // auto owns the choice now
  applyTheme()
}

export function toggleParticles() {
  particlesEnabled.value = !particlesEnabled.value
  persist(LS_PARTICLES, particlesEnabled.value ? null : '0')
}

export function setDensity(d: Density) {
  density.value = d
  persist(LS_DENSITY, d === 'comfortable' ? null : d)
  applyTheme()
}

/** Boot: reconcile DOM with signals (index.html bootstrap already painted) */
export function initTheme() {
  if (autoMode.value) persist(LS_THEME, null)
  applyTheme()
}

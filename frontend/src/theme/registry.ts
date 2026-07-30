/* Theme registry (spec §4.2) — manifest + one token CSS per theme.
   Adding a future theme = add one CSS file + one entry here. Core untouched. */
import './tokens/base.css'
import './tokens/classic-dark.css'
import './tokens/aurora-dark.css'
import './tokens/aurora-light.css'

export type ThemeMode = 'dark' | 'light'

export interface ThemeDefinition {
  id: string
  /** i18n key in the `theme` namespace (display name is translated) */
  nameKey: string
  mode: ThemeMode
  /** particles field of spec §4.2 — classic keeps the legacy flat look */
  particles: 'constellation' | 'none'
  builtin: boolean
  /** swatches for the theme-picker cards */
  preview: { canvas: string; accent: string; text: string }
  descriptionKey: string
}

export const THEMES: ThemeDefinition[] = [
  {
    id: 'classic-dark',
    nameKey: 'settings.theme.classicDark',
    descriptionKey: 'settings.theme.classicDarkDesc',
    mode: 'dark',
    particles: 'none',
    builtin: true,
    preview: { canvas: '#0b0f19', accent: '#6366f1', text: '#f3f4f6' },
  },
  {
    id: 'aurora-dark',
    nameKey: 'settings.theme.auroraDark',
    descriptionKey: 'settings.theme.auroraDarkDesc',
    mode: 'dark',
    particles: 'constellation',
    builtin: true,
    preview: { canvas: '#06090f', accent: '#7c7ff2', text: '#edf0f7' },
  },
  {
    id: 'aurora-light',
    nameKey: 'settings.theme.auroraLight',
    descriptionKey: 'settings.theme.auroraLightDesc',
    mode: 'light',
    particles: 'constellation',
    builtin: true,
    preview: { canvas: '#f6f7fb', accent: '#6366f1', text: '#101828' },
  },
]

export const DEFAULT_THEME = 'classic-dark' // spec §4.2 — preserve first-run experience

export function getTheme(id: string): ThemeDefinition | undefined {
  return THEMES.find((t) => t.id === id)
}

export function isThemeId(id: string): boolean {
  return THEMES.some((t) => t.id === id)
}

/** Themes that ship a constellation particle field */
export function themeHasParticles(id: string): boolean {
  return getTheme(id)?.particles === 'constellation'
}

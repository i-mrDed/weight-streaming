/* i18n core (spec §6)
   - locale JSONs at frontend/locales/<lang>/<namespace>.json, glob-loaded —
     adding a language = adding a folder (no core edits).
   - fallback chain: active → en → raw key
   - ?locale= override + ws-locale persistence + navigator detection (th first)
   - Intl plural + relative-time helpers (Today/Yesterday/older grouping)
*/
import { signal, computed } from '@preact/signals'

type Dict = Record<string, unknown>

// Eager glob: keys look like '../../locales/en/common.json'
const modules = import.meta.glob<Dict>('../../locales/*/*.json', { eager: true })

const tables: Record<string, Record<string, Dict>> = {}
for (const path of Object.keys(modules)) {
  const m = path.match(/locales\/([a-zA-Z-]+)\/([a-zA-Z-]+)\.json$/)
  if (!m) continue
  const [, lang, ns] = m
  tables[lang] ??= {}
  tables[lang][ns] = (modules[path].default ?? modules[path]) as Dict
}

export const availableLocales = Object.keys(tables).sort()
export const FALLBACK = 'en'

export interface LocaleMeta {
  code: string
  nativeName: string
}
// Display names live WITH their language (never translated) — extend per locale.
export const LOCALE_META: Record<string, LocaleMeta> = {
  en: { code: 'en', nativeName: 'English' },
  th: { code: 'th', nativeName: 'ไทย' },
}

const LS_LOCALE = 'ws-locale'

function detectInitial(): string {
  try {
    const url = new URL(window.location.href)
    const override = url.searchParams.get('locale')
    if (override && tables[override]) {
      localStorage.setItem(LS_LOCALE, override)
      return override
    }
    const stored = localStorage.getItem(LS_LOCALE)
    if (stored && tables[stored]) return stored
  } catch {
    /* fall through to detection */
  }
  const nav = (navigator.language || '').toLowerCase()
  if (nav.startsWith('th') && tables['th']) return 'th'
  return FALLBACK
}

export const locale = signal<string>(detectInitial())

export const localeMeta = computed<LocaleMeta>(
  () => LOCALE_META[locale.value] ?? { code: locale.value, nativeName: locale.value },
)

export function setLocale(code: string) {
  if (!tables[code]) return
  locale.value = code
  try {
    localStorage.setItem(LS_LOCALE, code)
  } catch { /* non-fatal */ }
  document.documentElement.setAttribute('lang', code)
}

function lookup(lang: string, ns: string, path: string[]): unknown {
  let node: unknown = tables[lang]?.[ns]
  for (const seg of path) {
    if (node && typeof node === 'object' && seg in (node as Dict)) {
      node = (node as Dict)[seg]
    } else {
      return undefined
    }
  }
  return node
}

function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template
  return template.replace(/\{\{(\w+)\}\}/g, (_, name: string) =>
    name in vars ? String(vars[name]) : `{{${name}}}`,
  )
}

/** Translate `ns.key[.sub…]` with {{var}} interpolation; falls back to en. */
export function t(key: string, vars?: Record<string, string | number>): string {
  const lang = locale.value // signal read → components re-render on change
  const dot = key.indexOf('.')
  const ns = dot === -1 ? 'common' : key.slice(0, dot)
  const path = (dot === -1 ? key : key.slice(dot + 1)).split('.')
  let val = lookup(lang, ns, path)
  if (typeof val !== 'string') val = lookup(FALLBACK, ns, path)
  if (typeof val !== 'string') {
    // Key not found in any locale — almost always a call-site bug (e.g. a
    // missing namespace prefix like 'server.field.host' instead of
    // 'settings.server.field.host'). The translation verifier only checks
    // locale-file parity and cannot see wrong prefixes, so surface it here
    // instead of silently rendering the raw key. (2026-08-05)
    if (import.meta.env?.DEV) console.warn(`[i18n] missing key: ${key}`)
    return key
  }
  return interpolate(val, vars)
}

/** Pluralize via Intl.PluralRules — keys `<key>_one|_other` (add per-language
    categories as needed; th/en only use one/other). */
export function tPlural(key: string, count: number, vars?: Record<string, string | number>): string {
  const lang = locale.value
  const category = new Intl.PluralRules(lang).select(count)
  const specific = t(`${key}_${category}`, { ...vars, count })
  if (specific !== `${key}_${category}`) return specific
  return t(`${key}_other`, { ...vars, count })
}

const DAY = 86_400_000

/** "Today" / "Yesterday" / "N days ago" — for history grouping (spec §9.2) */
export function relativeDay(ts: number, now: number = Date.now()): string {
  const diffDays = Math.round((startOfDay(now) - startOfDay(ts)) / DAY)
  const rtf = new Intl.RelativeTimeFormat(locale.value, { numeric: 'auto' })
  return rtf.format(-diffDays, 'day')
}

/** Fine-grained relative time ("2 min ago" / "in 3 h") — picks the natural
    unit for the distance; localized via Intl (no UI strings involved). */
export function fmtRelative(ts: number, now: number = Date.now()): string {
  const diff = ts - now
  const abs = Math.abs(diff)
  const rtf = new Intl.RelativeTimeFormat(locale.value, { numeric: 'auto' })
  if (abs < 60_000) return rtf.format(Math.round(diff / 1000), 'second')
  if (abs < 3_600_000) return rtf.format(Math.round(diff / 60_000), 'minute')
  if (abs < DAY) return rtf.format(Math.round(diff / 3_600_000), 'hour')
  return rtf.format(Math.round(diff / DAY), 'day')
}

function startOfDay(ts: number): number {
  const d = new Date(ts)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

export function fmtNumber(n: number, opts?: Intl.NumberFormatOptions): string {
  return new Intl.NumberFormat(locale.value, opts).format(n)
}

export function fmtTime(ts: number): string {
  return new Intl.DateTimeFormat(locale.value, { hour: '2-digit', minute: '2-digit' }).format(ts)
}

export function fmtDateTime(ts: number): string {
  return new Intl.DateTimeFormat(locale.value, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(ts)
}

export function initI18n() {
  document.documentElement.setAttribute('lang', locale.value)
}

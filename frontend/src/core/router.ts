/* Hash router (spec §8.1) — #/chat, deep links like #/issues/Report-ISSUE-002,
   last-page persistence. */
import { signal } from '@preact/signals'

export interface Route {
  path: string
  /** route pattern segment count must match; ':param' captures */
  params: Record<string, string>
}

export const VALID_PAGES = [
  'overview',
  'chat',
  'stats',
  'models',
  'issues',
  'hub',
  'docs',
  'settings',
  'assistants',
] as const

export type PageId = (typeof VALID_PAGES)[number]

const LS_LAST_PAGE = 'ws-last-page'

export const route = signal<Route>(parse(window.location.hash))

function parse(hash: string): Route {
  const raw = hash.replace(/^#\/?/, '')
  const [seg, ...rest] = raw.split('/')
  if (seg && (VALID_PAGES as readonly string[]).includes(seg)) {
    const params: Record<string, string> = {}
    if (seg === 'issues' && rest[0]) params.id = decodeURIComponent(rest[0])
    return { path: seg, params }
  }
  // Unknown / empty → last page or overview
  try {
    const last = localStorage.getItem(LS_LAST_PAGE)
    if (last && (VALID_PAGES as readonly string[]).includes(last)) return { path: last, params: {} }
  } catch { /* fresh */ }
  return { path: 'overview', params: {} }
}

export function navigate(to: string) {
  window.location.hash = `/${to}`
}

export function initRouter() {
  window.addEventListener('hashchange', () => {
    const next = parse(window.location.hash)
    route.value = next
    try {
      localStorage.setItem(LS_LAST_PAGE, next.path)
    } catch { /* non-fatal */ }
  })
  // Normalize the URL on first paint (e.g. bare /console/)
  const initial = parse(window.location.hash)
  if (window.location.hash !== `#/${initial.path}`) {
    window.history.replaceState(null, '', `#/` + initial.path)
  }
  try {
    localStorage.setItem(LS_LAST_PAGE, initial.path)
  } catch { /* non-fatal */ }
}

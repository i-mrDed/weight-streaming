/* Shell state (signals) — health, loaded models, open-issue count,
   display name. Polled visibility-aware; honest states only. */
import { signal, computed } from '@preact/signals'
import { apiJSON, type HealthStatus, type ModelStatus } from './api'
import { refreshAssistants } from './assistants'
import { refreshIssues } from './issues'
import { refreshDownloads, startDownloadsSync } from './downloads'
import { createPoller, refreshOnFocus, type Poller } from './poll'

export type HealthState = 'checking' | 'online' | 'offline'

export const health = signal<HealthState>('checking')
export const serverVersion = signal<string>('')
export const serverHostPort = signal<string>('')

export const models = signal<ModelStatus[]>([])
export const modelsLoadedAt = signal<number>(0)
// Open-issue badge lives in core/issues (shared signal + computed) so the
// Sidebar/Overview update instantly when the Issues page changes a status.

const LS_DISPLAY_NAME = 'ws-display-name'

export const displayName = signal<string>((() => {
  try {
    return localStorage.getItem(LS_DISPLAY_NAME) || ''
  } catch {
    return ''
  }
})())

export function setDisplayName(name: string) {
  displayName.value = name.trim()
  try {
    if (displayName.value) localStorage.setItem(LS_DISPLAY_NAME, displayName.value)
    else localStorage.removeItem(LS_DISPLAY_NAME)
  } catch { /* non-fatal */ }
}

export const primaryModel = computed<ModelStatus | null>(() => models.value[0] ?? null)
export const extraModelCount = computed(() => Math.max(0, models.value.length - 1))

async function fetchHealth() {
  try {
    const h = await apiJSON<HealthStatus>('/health', undefined, { timeoutMs: 5000 })
    health.value = h.status === 'ok' ? 'online' : 'offline'
    serverVersion.value = h.version ?? ''
    serverHostPort.value = window.location.host
  } catch {
    health.value = 'offline'
  }
}

async function fetchModels() {
  try {
    models.value = await apiJSON<ModelStatus[]>('/v1/models', undefined, { timeoutMs: 5000 })
    modelsLoadedAt.value = Date.now()
  } catch {
    /* keep last known — health dot tells the real story */
  }
}

let healthPoller: Poller | null = null
let modelPoller: Poller | null = null
let issuePoller: Poller | null = null
let downloadPoller: Poller | null = null

export function startShellPolling() {
  if (!healthPoller) {
    healthPoller = createPoller(fetchHealth, 10_000) // spec §8.1: /health 10s
    modelPoller = createPoller(fetchModels, 15_000)
    // Full list into the shared issues store — the open count is derived, so
    // a status change on the Issues page is reflected in the badge at once.
    // Heavier than the old `?status=open` count, but the local store is tiny
    // and single-source-of-truth beats a second count source. The .catch
    // preserves the old no-backoff behavior (internal swallow); don't drop it.
    issuePoller = createPoller(() => refreshIssues().catch(() => { /* keep last known */ }), 30_000)
    // Downloads: the module-level SSE watchers carry LIVE tasks, but tasks
    // created outside this tab (or finished while unwatched) only appear via
    // a refresh — poll 30s so the panel/badge always settle on the server
    // list. refreshDownloads swallows errors internally (keep last known).
    downloadPoller = createPoller(() => refreshDownloads(), 30_000)
    healthPoller.start()
    modelPoller.start()
    issuePoller.start()
    downloadPoller.start()
    // Assistants has no poller — refresh once when the tab regains focus so
    // changes made in another tab/device appear (models/issues are already
    // covered by their pollers' own visibility catch-up in poll.ts).
    refreshOnFocus(refreshAssistants)
    // Hub downloads: module-level SSE watchers + fallback poll live for the
    // app's lifetime, so progress continues across page navigation. The
    // focus refresh is belt-and-suspenders on top of the SSE's own
    // visibility catch-up (subscribeHubProgress reconnects on show).
    startDownloadsSync()
  }
}

/** One-shot used by the boot splash — resolves to true when reachable. */
export async function probeHealth(): Promise<boolean> {
  await fetchHealth()
  return health.value === 'online'
}

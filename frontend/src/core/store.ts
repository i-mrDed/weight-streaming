/* Shell state (signals) — health, loaded models, open-issue count,
   display name. Polled visibility-aware; honest states only. */
import { signal, computed } from '@preact/signals'
import { apiJSON, type HealthStatus, type IssueSummary, type ModelStatus } from './api'
import { createPoller, type Poller } from './poll'

export type HealthState = 'checking' | 'online' | 'offline'

export const health = signal<HealthState>('checking')
export const serverVersion = signal<string>('')
export const serverHostPort = signal<string>('')

export const models = signal<ModelStatus[]>([])
export const modelsLoadedAt = signal<number>(0)

export const openIssueCount = signal<number>(0)

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

async function fetchIssueCount() {
  try {
    const list = await apiJSON<IssueSummary[]>('/v1/issues?status=open', undefined, { timeoutMs: 5000 })
    openIssueCount.value = Array.isArray(list) ? list.length : 0
  } catch {
    /* non-fatal for the badge */
  }
}

let healthPoller: Poller | null = null
let modelPoller: Poller | null = null
let issuePoller: Poller | null = null

export function startShellPolling() {
  if (!healthPoller) {
    healthPoller = createPoller(fetchHealth, 10_000) // spec §8.1: /health 10s
    modelPoller = createPoller(fetchModels, 15_000)
    issuePoller = createPoller(fetchIssueCount, 30_000)
    healthPoller.start()
    modelPoller.start()
    issuePoller.start()
  }
}

/** One-shot used by the boot splash — resolves to true when reachable. */
export async function probeHealth(): Promise<boolean> {
  await fetchHealth()
  return health.value === 'online'
}

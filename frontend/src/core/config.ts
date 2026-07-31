/* ⚙️ Server config / usage history / log tail clients (spec §9.8 / §9.1) —
   exact shapes from weight_stream/server/config.py (describe_config),
   api_server.py (PATCH /v1/config policy, /v1/usage/history, /v1/logs/tail)
   and usage.py (record fields). PATCH is done with a raw fetch (not apiJSON)
   so the HONEST 409 answer — rejected reasons + an env snippet — can be
   rendered for copy instead of being flattened into an error toast. */
import { apiJSON } from './api'

export type ConfigSource = 'env' | 'default' | 'runtime'

export interface ConfigEntry {
  value: unknown
  source: ConfigSource
}

export interface ServerConfigResponse {
  config: Record<string, ConfigEntry>
  models_dirs: string[]
  issues_dir: string
  version: string
}

export function fetchConfig(): Promise<ServerConfigResponse> {
  return apiJSON<ServerConfigResponse>('/v1/config', undefined, { timeoutMs: 10_000 })
}

/* Keys the server mutates live (api_server._CONFIG_SAFE_KEYS) vs keys it
   accepts but only applies to models loaded afterwards (_CONFIG_GATED_KEYS).
   Everything else is answered 409 + snippet (_CONFIG_REJECT_REASONS). Kept
   here ONLY to structure the form — the server remains the authority: an
   unknown key is a 400, and the reject set is read from the 409 body. */
export const SAFE_KEYS = ['idle_unload_timeout', 'max_loaded_models'] as const
export const GATED_KEYS = ['default_buffer_mb', 'default_n_ctx', 'default_n_threads'] as const

export interface PatchApplied {
  status: 'applied'
  applied: Record<string, ConfigEntry>
  notes: Record<string, string>
  config: Record<string, ConfigEntry>
}

export interface PatchRejected {
  status: 'rejected'
  httpStatus: number
  detail: string
  rejected: Record<string, string>
  snippet: string
  restart_required?: boolean
}

export type PatchResult = PatchApplied | PatchRejected

/** PATCH /v1/config — resolves to the honest outcome (never throws for a
    well-formed 4xx answer; network failures still reject). */
export async function patchConfig(body: Record<string, unknown>): Promise<PatchResult> {
  const res = await fetch(`${window.location.origin}/v1/config`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>
  if (res.ok) {
    return {
      status: 'applied',
      applied: (data.applied as PatchApplied['applied']) ?? {},
      notes: (data.notes as PatchApplied['notes']) ?? {},
      config: (data.config as PatchApplied['config']) ?? {},
    }
  }
  const rejected = (data.rejected as Record<string, string>) ?? {}
  return {
    status: 'rejected',
    httpStatus: res.status,
    detail: typeof data.detail === 'string' ? data.detail : `HTTP ${res.status}`,
    rejected,
    snippet: typeof data.snippet === 'string' ? data.snippet : '',
    restart_required: data.restart_required === true,
  }
}

/* ── Usage history (§9.1) ── */

export interface UsageRecord {
  ts: number // epoch ms
  model: string
  tokens: number | null
  /** null when a streaming path had no real measurement — render "–" */
  tok_s: number | null
  elapsed_s: number | null
  paging?: Record<string, number>
}

export interface UsageHistoryResponse {
  history: UsageRecord[]
  count: number
  capacity: number
}

export function fetchUsageHistory(limit = 5): Promise<UsageHistoryResponse> {
  return apiJSON<UsageHistoryResponse>(`/v1/usage/history?limit=${limit}`, undefined, { timeoutMs: 10_000 })
}

/* ── Log tail (§9.8 diagnostics) ── */

export interface LogsTailResponse {
  lines: string[]
  count: number
}

export function fetchLogsTail(lines = 100): Promise<LogsTailResponse> {
  return apiJSON<LogsTailResponse>(`/v1/logs/tail?lines=${lines}`, undefined, { timeoutMs: 10_000 })
}

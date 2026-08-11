/* Auto-tiering API client — exact shapes from server/tiering.py +
   api_server.py (/v1/tiering/config GET/PUT, /v1/tiering/route). */
import { apiJSON } from './api'

export interface TierEntry {
  model_id: string
  model_path: string
  extra_args: string
  n_threads?: number | null
  /** Server-attached: whether the configured file resolves on disk. */
  file_resolved?: boolean
}

export interface TieringConfig {
  enabled: boolean
  max_prompt_chars: number
  reasoning_quality: string
  fast: TierEntry
  quality: TierEntry
}

export interface TieringConfigResponse {
  config: TieringConfig
  problems: string[]
}

export interface TieringRouteRequest {
  messages: { role: string; content: string }[]
  options?: { reasoning_mode?: string; reasoning_effort?: string }
}

export interface TieringRouteResponse {
  tier: 'fast' | 'quality'
  model_id: string
  model_path: string
  reason: string
}

export function fetchTieringConfig(): Promise<TieringConfigResponse> {
  return apiJSON<TieringConfigResponse>('/v1/tiering/config')
}

export function saveTieringConfig(cfg: TieringConfig): Promise<{ status: string; config: TieringConfig }> {
  return apiJSON<{ status: string; config: TieringConfig }>('/v1/tiering/config', {
    method: 'PUT',
    body: JSON.stringify(cfg),
  }, { timeoutMs: 30_000 })
}

export function routeTiering(req: TieringRouteRequest): Promise<TieringRouteResponse> {
  return apiJSON<TieringRouteResponse>('/v1/tiering/route', {
    method: 'POST',
    body: JSON.stringify(req),
  }, { timeoutMs: 5 * 60_000 })
}

/** Swap one tier of the config (fetch current → merge → save). Used by the
    Models page to pin a scanned model as fast/quality without touching the
    other tier. Returns the saved config. */
export async function setTier(
  tier: 'fast' | 'quality',
  entry: { model_id: string; model_path: string; extra_args?: string },
): Promise<TieringConfig> {
  const cur = await fetchTieringConfig()
  const sameModel =
    cur.config[tier].model_path.replace(/\\/g, '/') ===
    entry.model_path.replace(/\\/g, '/')
  // Only a SAME-model re-pin keeps the extra args (e.g. MTP draft flags).
  // Pinning a DIFFERENT model must clear them — a stale draft path from
  // the previous model would be appended to the new one's llama-server
  // cmdline (Gemma's MTP draft applied to Qwen would crash the spawn).
  const extra_args = sameModel
    ? (entry.extra_args ?? cur.config[tier].extra_args ?? '')
    : (entry.extra_args ?? '')
  const next: TieringConfig = {
    ...cur.config,
    [tier]: {
      model_id: entry.model_id,
      model_path: entry.model_path,
      extra_args,
    },
  }
  const saved = await saveTieringConfig(next)
  return saved.config
}

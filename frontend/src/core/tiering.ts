/* Auto-tiering API client — exact shapes from server/tiering.py +
   api_server.py (/v1/tiering/config GET/PUT, /v1/tiering/route). */
import { apiJSON } from './api'

export interface TierEntry {
  model_id: string
  model_path: string
  extra_args: string
  n_threads?: number | null
  n_ctx?: number | null
  /** Per-tier output budget (EXP-023) — callers clamp max_tokens to this. */
  max_tokens?: number | null
  /** Server-attached: whether the configured file resolves on disk. */
  file_resolved?: boolean
  /** Server-attached: basename of the configured model file (Hub badge match). */
  model_basename?: string
  /** Server-attached: whether this tier still points at the shipped default. */
  is_default?: boolean
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
  /** True when the tier's file was already loaded (reused, not reloaded). */
  reused?: boolean
  /** Per-tier output budget (EXP-023) — clamp your request's max_tokens. */
  max_tokens?: number | null
}

export interface TieringPreviewResponse {
  tier: 'fast' | 'quality'
  reason: string
  model_id: string
  model_path: string
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

/** Decide the tier for a prompt WITHOUT loading any model — uses the LIVE
    config server-side, so the answer is always real. Used by the Settings
    "test the router" box. */
export function previewTiering(req: TieringRouteRequest): Promise<TieringPreviewResponse> {
  return apiJSON<TieringPreviewResponse>('/v1/tiering/preview', {
    method: 'POST',
    body: JSON.stringify(req),
  }, { timeoutMs: 10_000 })
}

/** Pin a tier from exact file names (Hub recommended list → disk). The
    server resolves the files under the model search dirs (no full scan)
    and wires MTP draft flags when a sibling draft is present. */
export function pinTier(
  tier: 'fast' | 'quality',
  files: string[],
): Promise<{ status: string; config: TieringConfig }> {
  return apiJSON<{ status: string; config: TieringConfig }>('/v1/tiering/pin', {
    method: 'POST',
    body: JSON.stringify({ tier, files }),
  }, { timeoutMs: 60_000 })
}

/** Undo a user pin — restore ONE tier to the shipped default (Hub/Settings
    reset button). The other tier and thresholds are untouched. */
export function unpinTier(
  tier: 'fast' | 'quality',
): Promise<{ status: string; config: TieringConfig }> {
  return apiJSON<{ status: string; config: TieringConfig }>('/v1/tiering/unpin', {
    method: 'POST',
    body: JSON.stringify({ tier }),
  }, { timeoutMs: 30_000 })
}

/* ── Routing stats (Overview dashboard) ── */

export interface TierRouteEvent {
  ts: number // epoch ms
  tier: 'fast' | 'quality'
  reason: string
  model_id: string
  model_path?: string
  prompt_chars?: number
  reused?: boolean
}

export interface TieringStats {
  enabled: boolean
  total_routes: number
  by_tier: Record<string, number>
  by_reason: Record<string, number>
  by_model: Record<string, number>
  recent: TierRouteEvent[]
  count: number
}

export function fetchTieringStats(limit?: number): Promise<TieringStats> {
  const q = limit != null && limit > 0 ? `?limit=${limit}` : ''
  return apiJSON<TieringStats>(`/v1/tiering/stats${q}`, undefined, { timeoutMs: 10_000 })
}

/** Swap one tier of the config (fetch current → merge → save). Used by the
    Models page to pin a scanned model as fast/quality without touching the
    other tier. Returns the saved config. */
export async function setTier(
  tier: 'fast' | 'quality',
  entry: {
    model_id: string
    model_path: string
    extra_args?: string
    n_ctx?: number | null
    max_tokens?: number | null
  },
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
  // Per-tier n_ctx/max_tokens (EXP-023) survive a re-pin unless the caller
  // explicitly overrides them — the tier's context window and output
  // budget are model-pin-independent (the Models page pin has no fields
  // for them, so dropping them on every pin would silently reset the
  // tier's load profile).
  const n_ctx = entry.n_ctx !== undefined
    ? entry.n_ctx
    : (cur.config[tier].n_ctx ?? null)
  const max_tokens = entry.max_tokens !== undefined
    ? entry.max_tokens
    : (cur.config[tier].max_tokens ?? null)
  const next: TieringConfig = {
    ...cur.config,
    [tier]: {
      model_id: entry.model_id,
      model_path: entry.model_path,
      extra_args,
      n_ctx,
      max_tokens,
    },
  }
  const saved = await saveTieringConfig(next)
  return saved.config
}

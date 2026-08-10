/* `/v1/stats` client — exact shapes from weight_stream/server/model_manager.py
   (get_stats / get_server_status) and backends/llama_cpp.py (get_stats).
   Optional fields are optional because the server omits them when the
   platform cannot measure them (honest telemetry — ADR-003). */
import { apiJSON } from './api'

export interface BufferStats {
  capacity_shards: number
  hot_shards: number
  hits: number
  misses: number
  /** 0..1 — always 0 in real runs (llama.cpp reads its own mmap; ADR-003) */
  hit_rate: number
  prefetches: number
  evictions: number
  total_accesses: number
  capacity_mb: number
}

export interface PrefetcherStats {
  prefetched: number
  useful: number
  queued: number
}

export interface PagingDemand {
  faults: number
  faults_per_token: number
  fault_mb_per_token: number
  note: string
  /** POSIX only (major-fault deltas) */
  hard_faults?: number
  disk_demand_mb?: number
  disk_demand_source?: 'major_faults' | 'residency_growth_estimate'
  disk_mb_per_token?: number
}

export interface GenerationStats {
  token_count: number
  elapsed: number
  tokens_per_sec: number
  prompt: string
  paging?: PagingDemand
}

export interface PageCacheStats {
  resident_ratio: number
  resident_gb: number
  total_gb: number
}

/** Real GPU telemetry from llama-server's GET /props (LlamaServerBackend). */
export interface GpuStats {
  n_gpu_layers: number | null
  total_vram_mb: number | null
  used_vram_mb: number | null
}

export interface ModelStats {
  /** CPU binding always sends a BufferStats object; LlamaServerBackend (GPU)
      explicitly sends null — weights live inside llama-server, so there is no
      shard-level streaming buffer to measure. Never assume an object. */
  buffer?: BufferStats | null
  predictor?: Record<string, unknown>
  /** Same contract as buffer: present for the CPU binding, explicit null (or
      absent on older servers) for the GPU backend. */
  prefetcher?: PrefetcherStats | null
  /** empty object until the first generation on this model */
  generation: Partial<GenerationStats>
  /** null when the platform/backend has no residency tracker (non-Windows
      or LlamaServerBackend) — never assume an object */
  page_cache: Partial<PageCacheStats> | null
  model: { path: string; arch: string; n_experts: number; backend?: string }
  /** LlamaServerBackend only — real VRAM/offload telemetry, or null when the
      running llama-server does not expose it (older/CPU-only builds) */
  gpu?: GpuStats | null
}

/** True for LlamaServerBackend (GPU): no shard buffer / prefetcher / page
    cache residency — those gauges must render honest n/a, not zeros. */
export function isGpuBackend(ms: ModelStats | null | undefined): boolean {
  return !!ms && ms.model?.backend === 'llama-server'
}

/** from io/process_priority.py describe() — a dict, not a string */
export interface PriorityInfo {
  platform: string
  backend: string
  lowered: boolean
  mechanism?: string
  priority_class?: string
  nice_added?: number
}

export interface ServerStats {
  models_loaded: number
  max_models: number
  queue_depth: number
  host: string
  port: number
  priority: PriorityInfo
}

export interface StatsPayload {
  models: Record<string, ModelStats>
  server: ServerStats
}

export function fetchStats(model?: string, timeoutMs = 10_000): Promise<StatsPayload> {
  const path = model ? `/v1/stats?model=${encodeURIComponent(model)}` : '/v1/stats'
  return apiJSON<StatsPayload>(path, undefined, { timeoutMs })
}

/** True once the model has recorded at least one generation. */
export function hasGeneration(ms: ModelStats | undefined): boolean {
  return !!ms && typeof ms.generation?.token_count === 'number'
}

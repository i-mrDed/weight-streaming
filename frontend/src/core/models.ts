/* Models API client — exact shapes from api_server.py
   (/v1/models/scan, /v1/models/load, /v1/models/unload, /v1/browse,
   /v1/browse-dir) and schemas.py (ModelLoadRequest). */
import { apiJSON } from './api'

export interface ScanModel {
  path: string
  name: string
  size_bytes: number
  size_gb: number
  directory: string
  architecture: string
  quant: string | null
  may_need_upgrade: boolean
}

export interface ScanResult {
  models: ScanModel[]
  total: number
}

export interface BrowseResult {
  path: string | null
  name?: string
  size_gb?: number
  cancelled?: boolean
  error?: string
}

export interface LoadModelParams {
  model_id: string
  model_path: string
  buffer_mb: number
  n_ctx: number
  n_threads?: number | null
  /** GPU layers to offload: -1 = auto, 0 = CPU only, N = first N layers.
      GPU backend only; null = server default. */
  gpu_layers?: number | null
  /** KV cache data type (f16, q8_0, …). GPU backend only; null = server default. */
  kv_cache_type?: string | null
  force?: boolean
}

export interface ModelActionResponse {
  status: string
  model_id: string
  message?: string
}

/** Recursive GGUF scan — can take minutes on large stores, long timeout. */
export function scanModels(dir?: string): Promise<ScanResult> {
  const qs = dir ? `?dir=${encodeURIComponent(dir)}` : ''
  return apiJSON<ScanResult>(`/v1/models/scan${qs}`, undefined, { timeoutMs: 10 * 60_000 })
}

export function loadModel(params: LoadModelParams): Promise<ModelActionResponse> {
  return apiJSON<ModelActionResponse>('/v1/models/load', {
    method: 'POST',
    body: JSON.stringify(params),
  }, { timeoutMs: 5 * 60_000 })
}

export function unloadModel(model_id: string): Promise<ModelActionResponse> {
  return apiJSON<ModelActionResponse>('/v1/models/unload', {
    method: 'POST',
    body: JSON.stringify({ model_id }),
  }, { timeoutMs: 60_000 })
}

/** Native file picker on the server box (dialog timeout is 120s there). */
export function browseFile(): Promise<BrowseResult> {
  return apiJSON<BrowseResult>('/v1/browse', undefined, { timeoutMs: 130_000 })
}

export function browseDir(): Promise<BrowseResult> {
  return apiJSON<BrowseResult>('/v1/browse-dir', undefined, { timeoutMs: 130_000 })
}

const QUANT_RE = /\b(F16|F32|BF16|IQ\d+_[A-Z0-9]+|Q\d+(?:_[A-Z0-9]+)?)\b/i

/** Parse a quant label out of a GGUF filename / model id. Pure name parsing —
    not telemetry; returns null when the name carries no recognizable tag. */
export function guessQuant(nameOrPath: string | null | undefined): string | null {
  if (!nameOrPath) return null
  const m = nameOrPath.match(QUANT_RE)
  return m ? m[1].toUpperCase() : null
}

/** Quant advisory level for the load form (from MODEL_GUIDE / ISSUE-011/018). */
export function quantAdvisory(quant: string | null): 'full' | 'low' | null {
  if (!quant) return null
  if (quant === 'F16' || quant === 'F32' || quant === 'BF16') return 'full'
  if (quant.startsWith('Q2_') || quant === 'Q2') return 'low'
  return null
}

/** Suggested model_id from a file path: basename without .gguf. */
export function suggestModelId(path: string): string {
  const base = path.split(/[\\/]/).pop() ?? path
  return base.replace(/\.gguf$/i, '') || 'model'
}

export interface HardwareInfo {
  gpu: { name: string; total_vram_mb: number } | null
  source: string
}

/** GPU info from nvidia-smi (total VRAM — for quant-fit advice before any
    model is loaded). gpu: null when the server cannot see a GPU. */
export function fetchHardware(): Promise<HardwareInfo> {
  return apiJSON<HardwareInfo>('/v1/hardware', undefined, { timeoutMs: 15_000 })
}

/** Strip a quant tag from a GGUF basename to get the "same model" key.
    Mirrors the server's quant regex: IQ1_M / IQ2_M / Q4_K_M / F16 / … */
export function modelBaseKey(nameOrPath: string): string {
  const base = nameOrPath.split(/[\\/]/).pop() ?? nameOrPath
  return base.replace(/\.gguf$/i, '').replace(QUANT_RE, '').replace(/[-_.]+$/i, '')
}

/** Sibling quants of the SAME model from scan results (same base key,
    different file). Sorted by size ascending — the smallest first. */
export function quantSiblings(
  path: string,
  scanResults: ScanModel[] | null,
): ScanModel[] {
  if (!scanResults?.length) return []
  const base = modelBaseKey(path)
  if (!base) return []
  const norm = path.replace(/\\/g, '/')
  return scanResults
    .filter((m) => m.path.replace(/\\/g, '/') !== norm && modelBaseKey(m.path) === base)
    .sort((a, b) => a.size_bytes - b.size_bytes)
}

/** Measured tok/s on THIS machine (EXP-011, Qwen3.6-35B-A3B, n-cpu-moe 0,
    temp 0, same question set). Honest reference for the quant advisor —
    only listed for quants we actually measured, never extrapolated. */
export const MEASURED_TOK_S: Record<string, number> = {
  IQ1_M: 79.1,
  IQ2_M: 56.4,
}

/** Rough VRAM needed for a model file, MiB: weights ≈ file size + KV cache
    + compute buffers. Calibrated from EXP-011 on this machine (IQ1_M 10.05
    GB file → 10,803 MiB; IQ2_M 11.5 GB → ~12,067 MiB). */
export function estimateVramMiB(sizeBytes: number, ctx = 2048): number {
  const fileMiB = sizeBytes / (1024 * 1024)
  // KV + compute overhead ≈ 0.9 GiB at 2048 ctx (measured delta between
  // file size and VRAM usage on this box).
  return Math.round(fileMiB + (0.9 + ctx / 2048 * 0.25) * 1024)
}

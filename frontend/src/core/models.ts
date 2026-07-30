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

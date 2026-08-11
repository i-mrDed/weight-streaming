/* 🌐 Hub client (spec §9.6) — exact shapes from weight_stream/server/hub.py
   (DownloadTask.to_dict / DownloadManager._parse_search) and the /v1/hub/*
   routes in api_server.py. Progress telemetry is ALWAYS server-computed
   (ADR-003): bytes/percent/speed_bps/eta_s are displayed as delivered —
   never smoothed, estimated client-side, or fabricated here. */
import { apiJSON } from './api'

export interface HubFile {
  filename: string
  /** quant parsed server-side from the filename; null when unparseable */
  quant: string | null
  /** parameter-size label (7B, 8X7B) parsed from repo+file name; null = unknown */
  size_label: string | null
}

export interface HubSearchResult {
  repo_id: string
  /** author (namespace) the server derived from repo_id; null for bare names */
  author: string | null
  downloads: number | null
  likes: number | null
  last_modified: string | null
  /** passed through from the (expanded) HF search response; null when absent */
  pipeline_tag: string | null
  /** passed through from the HF search response; [] when absent */
  tags: string[]
  gguf: true
  files: HubFile[]
}

/* ── On-demand model detail (GET /v1/hub/model/{repo}) ──────────────
   Every field mirrors weight_stream/server/hub.py::_build_detail. Fields HF
   does not provide are null — this client NEVER fills them in (ADR-003). */

export interface HubShard {
  /** 1-based position within the quant's shard set */
  index: number
  total: number
}

export interface HubDetailFile {
  filename: string
  /** real byte size from HF tree/main; null if HF omitted it */
  bytes: number | null
  quant: string | null
  size_label: string | null
  shard: HubShard | null
}

export interface HubNonGguf {
  filename: string
  bytes: number | null
  type: string
}

export interface HubQuantGroup {
  quant: string | null
  files: HubDetailFile[]
  /** sum of the shard bytes; null if any part's size is unknown */
  total_bytes: number | null
  sharded: boolean
  /** ordered per-shard byte sizes; null when not sharded / incomplete */
  per_shard_bytes: number[] | null
}

export interface HubModelDetail {
  repo_id: string
  author: string | null
  published_at: string | null
  updated_at: string | null
  downloads: number | null
  likes: number | null
  pipeline_tag: string | null
  tags: string[]
  library: string | null
  description: string | null
  base_model: string | string[] | null
  /** only ever a real value from cardData/tags; otherwise null */
  context_length: number | null
  files: HubDetailFile[]
  non_gguf: HubNonGguf[]
  quants: HubQuantGroup[]
}

/* ── Curated "proven on this rig" recommendations ───────────────────
   Served from weight_stream/server/recommended.py — every entry is backed
   by a measured experiment (research/experiments/) incl. the Thai quality
   gate, and carries the EXACT files that were measured (byte sizes verified
   against HF at curation time). Numbers are from THIS machine — honest
   caveat rendered alongside (ADR-003). */

export interface HubRecommendedFile {
  filename: string
  /** real byte size of this file (verified against HF at curation time) */
  bytes: number
}

/** Human-readable text that ships in both project languages; the UI picks
    the active one, the measured numbers stay a single source of truth. */
export interface HubLocaleText {
  en: string
  th: string
}

export interface HubRecommendedQuant {
  quant: string
  /** the exact download set — the Hub downloads precisely these */
  files: HubRecommendedFile[]
  total_bytes: number
  /** measured tok/s range on the reference rig; null = not measured */
  tok_s_min: number | null
  tok_s_max: number | null
  /** Thai quality gate: correct/total (9 fixed questions, EXP-009 set) */
  thai_correct: number | null
  thai_total: number | null
  /** Thai tonal discriminator: correct/total (the project's quality floor) */
  thai_tonal_correct: number | null
  thai_tonal_total: number | null
  /** repo-relative path to the evidence (research/experiments/EXP-*) */
  experiment: string
  /** free-form measurement/usage note, localised */
  notes: HubLocaleText | null
  /** llama-server flags the measurement used (e.g. MTP); null = none */
  flags: string | null
}

export type HubRecommendedRole = 'thai' | 'speed' | 'balanced'

export interface HubRecommendedEntry {
  repo_id: string
  name: string
  arch: string
  /** drives the badge colour/icon in the UI */
  role: HubRecommendedRole
  tagline: HubLocaleText
  quants: HubRecommendedQuant[]
}

export interface HubRecommendedResponse {
  recommended: HubRecommendedEntry[]
  count: number
}

/** Pick the active language from a locale dict; falls back to English, then
    to whatever exists (a missing locale never blanks a label). */
export function pickLocaleText(txt: HubLocaleText, lang: string): string {
  return txt[lang as keyof HubLocaleText] ?? txt.en ?? txt.th
}

export function hubRecommended(): Promise<HubRecommendedResponse> {
  return apiJSON<HubRecommendedResponse>('/v1/hub/recommended', undefined, { timeoutMs: 10_000 })
}

/* ── In-app experiment evidence (GET /v1/research/experiment/{path}) ──
   The Evidence button opens the experiment record INSIDE the app (the repo
   is private — no GitHub link needed). The server validates the path stays
   under research/experiments/ and returns the folder's markdown files. */

export interface ResearchExperimentFile {
  /** e.g. setup.md / results.md / analysis.md */
  name: string
  markdown: string
}

export interface ResearchExperiment {
  /** the validated experiment dir (research/experiments/EXP-XXX-…/) */
  path: string
  /** real byte sizes per file; 0/null only when the read failed */
  files: ResearchExperimentFile[]
}

export function researchExperiment(expPath: string): Promise<ResearchExperiment> {
  const enc = expPath.split('/').map(encodeURIComponent).join('/')
  return apiJSON<ResearchExperiment>(`/v1/research/experiment/${enc}`, undefined, { timeoutMs: 10_000 })
}

export function hubModel(repoId: string): Promise<HubModelDetail> {
  // repo_id is server-sourced → encode each path segment, never interpolate raw
  const enc = repoId.split('/').map(encodeURIComponent).join('/')
  return apiJSON<HubModelDetail>(`/v1/hub/model/${enc}`, undefined, { timeoutMs: 20_000 })
}

export interface HubSearchResponse {
  results: HubSearchResult[]
  count: number
  /** HF cursor for the next page; null when unavailable / last page. */
  next_cursor: string | null
}

export type HubTaskStatus = 'queued' | 'downloading' | 'done' | 'failed' | 'cancelled'

export interface HubTask {
  id: string
  repo_id: string
  filename: string
  target_dir: string
  target_path: string
  status: HubTaskStatus
  bytes_downloaded: number
  total_bytes: number | null
  /** REAL byte size of the file on disk for a completed download; null
      otherwise (stat'ed server-side at serialization time — honest). */
  file_size: number | null
  /** null until total_bytes is known — render "–", never guess */
  percent: number | null
  speed_bps: number | null
  eta_s: number | null
  error: string | null
  created_at: number
  updated_at: number
}

export const HUB_TERMINAL: readonly HubTaskStatus[] = ['done', 'failed', 'cancelled']

export type HubSort = 'downloads' | 'likes' | 'recent'

export function hubSearch(q: string, sort: HubSort, limit = 20): Promise<HubSearchResponse> {
  const qs = new URLSearchParams({ q, sort, limit: String(limit) })
  // HF can be slow; the server itself times out at 10s.
  return apiJSON<HubSearchResponse>(`/v1/hub/search?${qs}`, undefined, { timeoutMs: 20_000 })
}

/** Paged search used by the Hub "Latest" feed: asks the server for real HF
    cursor pagination (paginate=1) and returns the ``next_cursor`` too. */
export function hubSearchPage(
  sort: HubSort,
  cursor: string | null,
  limit = 20,
): Promise<HubSearchResponse> {
  const qs = new URLSearchParams({
    sort,
    limit: String(limit),
    paginate: '1',
  })
  if (cursor) qs.set('cursor', cursor)
  return apiJSON<HubSearchResponse>(`/v1/hub/search?${qs}`, undefined, { timeoutMs: 20_000 })
}

export function hubDownload(repoId: string, filename: string, targetDir?: string): Promise<HubTask> {
  return apiJSON<HubTask>(
    '/v1/hub/download',
    { method: 'POST', body: JSON.stringify({ repo_id: repoId, filename, target_dir: targetDir ?? null }) },
    { timeoutMs: 30_000 },
  )
}

export function hubDownloads(): Promise<{ downloads: HubTask[]; count: number }> {
  return apiJSON('/v1/hub/downloads', undefined, { timeoutMs: 10_000 })
}

export function hubCancel(taskId: string): Promise<HubTask> {
  return apiJSON<HubTask>(`/v1/hub/download/${encodeURIComponent(taskId)}/cancel`, { method: 'POST' }, { timeoutMs: 10_000 })
}

/** v1.1 resume: re-queues a cancelled/failed task; the server appends the
    remaining bytes to the kept ``.part`` via HTTP Range (never byte 0). */
export function hubResume(taskId: string): Promise<HubTask> {
  return apiJSON<HubTask>(`/v1/hub/download/${encodeURIComponent(taskId)}/resume`, { method: 'POST' }, { timeoutMs: 10_000 })
}

/** v1.1 delete: removes a task (stops a running worker, drops its .part).
    With `deleteFile` the server ALSO removes the completed .gguf from disk
    (only for done tasks whose model is not loaded); `file_deleted` in the
    response says honestly whether the file was removed. */

/** Cross-feature model references (the server scans what it owns —
    assistants; conversations live client-side so the UI counts those
    itself). Used to warn before a model file is deleted. */
export interface HubReferencedBy {
  /** assistant NAMES pinned to this download's suggested model id */
  assistants: string[]
}

export interface HubDeleteResult {
  status: string
  id: string
  file_deleted: boolean
  /** scanned live at delete time (catches cross-tab assistant edits) */
  referenced_by: HubReferencedBy
}

export function hubDelete(taskId: string, deleteFile = false): Promise<HubDeleteResult> {
  return apiJSON(
    `/v1/hub/download/${encodeURIComponent(taskId)}/delete`,
    deleteFile ? { method: 'POST', body: JSON.stringify({ delete_file: true }) } : { method: 'POST' },
    { timeoutMs: 10_000 },
  )
}

/** v1.1 clear-finished: remove every terminal task (done/failed/cancelled)
    in one call; active downloads are kept. With `deleteFile` the server ALSO
    deletes the model files of completed downloads, except those of currently
    loaded models (reported in `files_skipped`). */
export interface HubClearResult {
  status: string
  removed: string[]
  files_deleted: string[]
  files_skipped: string[]
  /** task id → references; present only when deleteFile was requested
      (only then are model files at risk). */
  referenced_by?: Record<string, HubReferencedBy>
}

export function hubClear(deleteFile = false): Promise<HubClearResult> {
  return apiJSON(
    '/v1/hub/downloads/clear',
    deleteFile ? { method: 'POST', body: JSON.stringify({ delete_file: true }) } : { method: 'POST' },
    { timeoutMs: 10_000 },
  )
}

/** v1.1 reveal: ask the server (same machine as the browser) to open the OS
    file manager showing a completed download's file. 404 unknown / 409 not
    finished / 403 outside the allowed model dirs / 500 launcher failed. */
export function hubReveal(taskId: string): Promise<{ status: string; path: string }> {
  return apiJSON(
    `/v1/hub/download/${encodeURIComponent(taskId)}/reveal`,
    { method: 'POST' },
    { timeoutMs: 10_000 },
  )
}

/** Visibility-aware SSE subscription to a download's REAL progress.

    Uses the native EventSource (no library — bundle budget). The server
    yields the current task state immediately on connect, then every 0.5s
    until a terminal status, so a (re)connect after the tab was hidden
    catches up at once. Returns `stop()` — call it on unmount AND whenever
    the tab becomes hidden (the brief requires pause-when-hidden). */
export function subscribeHubProgress(
  taskId: string,
  onFrame: (task: HubTask) => void,
  onError?: () => void,
): () => void {
  let es: EventSource | null = null
  let closed = false

  const open = () => {
    if (closed || document.hidden) return
    es = new EventSource(`/v1/hub/progress/${encodeURIComponent(taskId)}`)
    es.onmessage = (ev) => {
      try {
        onFrame(JSON.parse(ev.data) as HubTask)
      } catch {
        /* a malformed frame is not fatal — the next tick carries full state */
      }
    }
    es.onerror = () => {
      // The server CLOSES the stream after the terminal frame, which also
      // fires onerror (readyState CLOSED) — that is the happy path. Only
      // surface errors while the stream should still be live.
      es?.close()
      es = null
      if (!closed && !document.hidden) onError?.()
    }
  }

  const onVisibility = () => {
    if (document.hidden) {
      es?.close()
      es = null
    } else if (!closed) {
      open() // resume: server replays the current state immediately
    }
  }
  document.addEventListener('visibilitychange', onVisibility)

  open()
  return () => {
    closed = true
    es?.close()
    es = null
    document.removeEventListener('visibilitychange', onVisibility)
  }
}

/* ── display helpers (pure formatting, no fabricated data) ── */

export function fmtBytes(n: number | null | undefined): string {
  if (n == null) return '–'
  if (n < 1024) return `${n} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let v = n / 1024
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v >= 100 ? Math.round(v) : v.toFixed(1)} ${units[i]}`
}

export function fmtSpeed(bps: number | null | undefined): string | null {
  if (bps == null || !Number.isFinite(bps) || bps < 0) return null // honest: unknown
  return `${fmtBytes(bps)}/s`
}

export function fmtEta(seconds: number | null | undefined): string | null {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return null // honest: unknown
  const s = Math.round(seconds)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ${s % 60}s`
  return `${Math.floor(m / 60)}h ${m % 60}m`
}

/** repo "author/name" → author; repos without a slash have no separate author. */
export function repoAuthor(repoId: string): string | null {
  const i = repoId.indexOf('/')
  return i > 0 ? repoId.slice(0, i) : null
}

export function repoName(repoId: string): string {
  const i = repoId.indexOf('/')
  return i >= 0 ? repoId.slice(i + 1) : repoId
}

/** Safe external link to a repo on huggingface.co (server-sourced id →
    each path segment is URI-encoded; never interpolated raw). */
export function hfRepoUrl(repoId: string): string {
  return `https://huggingface.co/${repoId.split('/').map(encodeURIComponent).join('/')}`
}

/* ── Category + feature derivation (pure; from REAL HF pipeline_tag/tags) ──
   Honest: when HF gives no usable signal we return the neutral "other"
   category and zero feature badges — we never invent a category. */

export type HubCategoryId =
  | 'embedding'
  | 'vision'
  | 'audio'
  | 'code'
  | 'moe'
  | 'chat'
  | 'other'

export interface HubCategory {
  id: HubCategoryId
  emoji: string
  labelKey: string
}

/** Unquantized weight families — real, but usually far too large to want. */
const UNQUANTIZED = new Set(['F16', 'BF16', 'F32'])
export function isUnquantized(quant: string | null): boolean {
  return quant != null && UNQUANTIZED.has(quant.toUpperCase())
}

export function modelCategory(
  pipelineTag: string | null | undefined,
  tags: string[] | null | undefined,
): HubCategory {
  const pt = (pipelineTag || '').toLowerCase()
  const t = (tags || []).map((x) => String(x).toLowerCase())
  const has = (...needles: string[]) => t.some((tag) => needles.some((n) => tag.includes(n)))
  if (pt.includes('embedding') || pt.includes('feature-extraction') || pt.includes('sentence-similarity') || has('embedding', 'embeddings')) {
    return { id: 'embedding', emoji: '🔢', labelKey: 'hub.catEmbedding' }
  }
  if (pt.includes('image') || pt.includes('vision') || has('vision', 'image-to-text', 'multimodal')) {
    return { id: 'vision', emoji: '👁️', labelKey: 'hub.catVision' }
  }
  if (pt.includes('audio') || pt.includes('speech') || has('audio', 'tts', 'asr', 'speech')) {
    return { id: 'audio', emoji: '🎧', labelKey: 'hub.catAudio' }
  }
  if (pt.includes('code') || has('code')) {
    return { id: 'code', emoji: '💻', labelKey: 'hub.catCode' }
  }
  if (has('moe', 'mixture-of-experts')) {
    return { id: 'moe', emoji: '🧩', labelKey: 'hub.catMoe' }
  }
  if (pt.includes('text-generation') || pt.includes('conversational') || has('chat', 'conversational')) {
    return { id: 'chat', emoji: '💬', labelKey: 'hub.catChat' }
  }
  return { id: 'other', emoji: '🤖', labelKey: 'hub.catOther' }
}

/** Relevant, decision-useful feature hints derived from tags (max 4). */
export function modelFeatures(tags: string[] | null | undefined): string[] {
  const t = (tags || []).map((x) => String(x).toLowerCase())
  const out: string[] = []
  if (t.some((x) => x.includes('function-calling') || x.includes('function_calling') || x.includes('tool'))) {
    out.push('hub.featTools')
  }
  if (t.some((x) => x.includes('vision') || x.includes('image'))) out.push('hub.featVision')
  if (t.some((x) => x === 'th' || x.includes('thai'))) out.push('hub.featThai')
  if (t.some((x) => x.includes('moe') || x.includes('mixture-of-experts'))) out.push('hub.featMoe')
  return out.slice(0, 4)
}

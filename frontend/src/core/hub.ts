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
  downloads: number | null
  likes: number | null
  last_modified: string | null
  gguf: true
  files: HubFile[]
}

export interface HubSearchResponse {
  results: HubSearchResult[]
  count: number
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

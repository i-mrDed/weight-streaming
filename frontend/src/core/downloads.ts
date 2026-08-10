/* 📥 Hub downloads shared store — the live download state for the whole app.

   Problem this solves: the old HubPage owned the SSE subscriptions inside the
   component, so navigating away unmounted the watcher and download progress
   froze until you returned (and only then caught up). Downloads outlive the
   page (tasks live on the server) — so the watch/fallback/toast machinery
   belongs at module level, for the app's lifetime.

   Structure (same pattern as core/assistants.ts + core/issues.ts):
   - signals: downloads (task map), downloadOrder, loadTarget, loadingNow
   - computed: downloadsLiveCount, activeDownloads
   - actions: startDownload / cancelDownload / refreshDownloads /
     loadFromDownload / openLoadNow
   - events: subscribeDownloadEvents() — pages/subscriptions can react
     (the load-now dialog on HubPage subscribes for the terminal "done" state)
   - one sticky progress toast per download, created at start, updated with
     REAL numbers from every SSE frame, resolved at the end (spec §8.4).

   Honest telemetry (ADR-003): every byte/percent/speed/ETA comes straight
   from the server's SSE frames — nothing is estimated, smoothed, or
   fabricated here. `progressLine` renders exactly what the server delivered. */
import { computed, signal } from '@preact/signals'
import {
  HUB_TERMINAL,
  fmtBytes,
  fmtEta,
  fmtSpeed,
  hubCancel,
  hubClear,
  hubDelete,
  hubDownload,
  hubDownloads,
  hubResume,
  hubReveal,
  subscribeHubProgress,
  type HubTask,
} from './hub'
import { ApiError, apiJSON, type ModelStatus } from './api'
import { loadModel, suggestModelId } from './models'
import { fetchConfig } from './config'
import { fmtNumber, t } from '@/i18n'
import { armDismiss, dismissToast, toast, updateToast } from '@/components/Toast'
import { refreshOnFocus } from './poll'
// NB: intentional store.ts <-> downloads.ts cycle — `models` is only read at
// call time inside loadFromDownload (never at module-eval), and store.ts only
// invokes startDownloadsSync/refreshDownloads at runtime, so ESM resolves
// both bindings fine. Kept here (rather than a callback seam) for simplicity.
import { models } from './store'

/* ── state ──────────────────────────────────────────────────────── */

export const downloads = signal<Record<string, HubTask>>({})
/** newest-first order (server returns oldest-first; we reverse on apply) */
export const downloadOrder = signal<string[]>([])
/** "load now?" dialog state — lives here so the toast action can open it
    from any page (the dialog itself renders on HubPage) */
export const loadTarget = signal<HubTask | null>(null)
export const loadingNow = signal(false)

/** count of non-terminal tasks — drives the Hub header badge everywhere */
export const downloadsLiveCount = computed(
  () => downloadOrder.value.filter((id) => !HUB_TERMINAL.includes(downloads.value[id]?.status ?? 'done')).length,
)

export const activeDownloads = computed<HubTask[]>(() =>
  downloadOrder.value.map((id) => downloads.value[id]).filter((tk): tk is HubTask => !!tk),
)

/* ── SSE watchers + fallback poll (module-level, app-lifetime) ──── */

const subs = new Map<string, () => void>()
const fallbackTimers = new Map<string, number>()

/** task ids deleted this session — a late in-flight SSE frame must never
    resurrect a row the user removed (ids are unique per server run, so a
    deleted id can never legitimately come back) */
const deletedIds = new Set<string>()

function watch(taskId: string) {
  if (subs.has(taskId)) return
  const stop = subscribeHubProgress(
    taskId,
    (frame) => setTask(frame),
    () => startFallbackPoll(taskId), // SSE dropped mid-flight → poll until terminal
  )
  subs.set(taskId, stop)
}

function stopWatching(taskId: string) {
  subs.get(taskId)?.()
  subs.delete(taskId)
  const timer = fallbackTimers.get(taskId)
  if (timer) window.clearInterval(timer)
  fallbackTimers.delete(taskId)
}

function startFallbackPoll(taskId: string) {
  if (fallbackTimers.has(taskId)) return
  const timer = window.setInterval(async () => {
    if (document.hidden) return // visibility-aware like the SSE path
    try {
      const res = await hubDownloads()
      const task = res.downloads.find((tk) => tk.id === taskId)
      if (task) setTask(task)
      if (!task || HUB_TERMINAL.includes(task.status)) {
        const t0 = fallbackTimers.get(taskId)
        if (t0) window.clearInterval(t0)
        fallbackTimers.delete(taskId)
      }
    } catch {
      /* keep polling — the health dot shows the outage */
    }
  }, 2000)
  fallbackTimers.set(taskId, timer)
}

/* ── actions ───────────────────────────────────────────────────── */

function applyTasks(list: HubTask[]) {
  const next: Record<string, HubTask> = {}
  for (const task of list) next[task.id] = task
  downloads.value = next
  downloadOrder.value = list.map((tk) => tk.id).reverse() // newest first
}

/** Fetch the full list from the server (source of truth) and re-attach the
    live feed to anything still running. Safe to call repeatedly — watch()
    dedupes, and terminal tasks are skipped. */
export async function refreshDownloads() {
  try {
    const res = await hubDownloads()
    applyTasks(res.downloads)
    for (const task of res.downloads) {
      if (!HUB_TERMINAL.includes(task.status)) watch(task.id)
    }
  } catch {
    /* keep last known — the health dot tells the story */
  }
}

function setTask(task: HubTask) {
  if (deletedIds.has(task.id)) return // deleted this session — ignore stale frames
  const prev = downloads.value[task.id]
  downloads.value = { ...downloads.value, [task.id]: task }
  if (!downloadOrder.value.includes(task.id)) {
    downloadOrder.value = [task.id, ...downloadOrder.value]
  }
  renderTaskToast(task, prev)
  if (HUB_TERMINAL.includes(task.status)) {
    stopWatching(task.id)
    void refreshDownloads() // settle the panel list (server is source of truth)
  }
}

export async function startDownload(repoId: string, filename: string, targetDir?: string) {
  try {
    const task = await hubDownload(repoId, filename, targetDir)
    setTask(task)
    watch(task.id)
  } catch (e) {
    toast('error', t('hub.dlFailed'), {
      body: e instanceof ApiError && e.detail ? e.detail : String(e),
    })
  }
}

export async function cancelDownload(taskId: string) {
  try {
    const task = await hubCancel(taskId)
    setTask(task)
  } catch (e) {
    toast('error', t('common.notAvailable'), {
      body: e instanceof ApiError && e.detail ? e.detail : String(e),
    })
  }
}

/** v1.1: re-queue a cancelled/failed download — the server appends the
    remaining bytes to the kept .part (Range), so this is cheap vs a retry. */
export async function resumeDownload(taskId: string) {
  try {
    const task = await hubResume(taskId)
    setTask(task)
    watch(task.id)
  } catch (e) {
    toast('error', t('hub.dlResumeFailed'), {
      body: e instanceof ApiError && e.detail ? e.detail : String(e),
    })
  }
}

/** v1.1: remove a task from the panel (stops the worker, drops its .part).
    With `deleteFile` the completed model file is ALSO removed from disk
    (only offered for done tasks — the HubPage confirm dialog decides). */
export async function deleteDownload(taskId: string, deleteFile = false) {
  try {
    const res = await hubDelete(taskId, deleteFile)
    deletedIds.add(taskId)
    stopWatching(taskId)
    const id = toastIds.get(taskId)
    if (id != null) {
      dismissToast(id)
      toastIds.delete(taskId)
    }
    const next = { ...downloads.value }
    delete next[taskId]
    downloads.value = next
    downloadOrder.value = downloadOrder.value.filter((id) => id !== taskId)
    if (res.file_deleted) {
      // the delete dialog already warned, but the server re-scans at delete
      // time — an assistant created/edited in another tab is reported here
      const refs = res.referenced_by?.assistants ?? []
      toast(
        'success',
        t('hub.dlFileDeleted'),
        refs.length ? { body: t('hub.dlFileDeletedRefs', { names: refs.join(', ') }) } : undefined,
      )
    } else if (deleteFile) {
      // user explicitly asked to reclaim disk space — never be silent when
      // the file is still there (missing / locked / outside allowed dirs)
      toast('warning', t('hub.dlFileNotDeleted'), { body: t('hub.dlFileNotDeletedBody') })
    }
  } catch (e) {
    toast('error', t('hub.dlDeleteFailed'), {
      body: e instanceof ApiError && e.detail ? e.detail : String(e),
    })
  }
}

/** v1.1 clear-finished: remove every finished download (done/failed/
    cancelled) at once — active ones stay. With `deleteFile` the completed
    model files are ALSO deleted from disk, except files of currently loaded
    models (the server reports those in files_skipped). One summary toast;
    never silent when files were requested but not all were deleted. */
export async function clearFinished(deleteFile = false) {
  try {
    const res = await hubClear(deleteFile)
    const removedSet = new Set(res.removed)
    for (const id of res.removed) {
      deletedIds.add(id) // a late in-flight SSE frame must not resurrect a cleared row
      stopWatching(id)
      const toastId = toastIds.get(id)
      if (toastId != null) {
        dismissToast(toastId)
        toastIds.delete(id)
      }
    }
    const next = { ...downloads.value }
    for (const id of res.removed) delete next[id]
    downloads.value = next
    downloadOrder.value = downloadOrder.value.filter((id) => !removedSet.has(id))
    if (res.removed.length > 0) {
      const n = res.removed.length
      // Honest summary — never silent about a file that was requested but kept:
      // deleted count always shown; skipped (loaded / locked / missing / outside
      // allowed dirs) appended as a warning line whenever delete was requested.
      const skipped = deleteFile ? res.files_skipped.length : 0
      // files ACTUALLY deleted whose model is referenced by an assistant
      // (server-scanned at clear time). Counted only among files_deleted —
      // a skipped (kept) file's reference is intact, so it must never appear
      // in a "N referenced" note.
      const refd = deleteFile
        ? res.files_deleted.filter((id) => (res.referenced_by?.[id]?.assistants.length ?? 0) > 0).length
        : 0
      const refNote = refd > 0 ? ` · ${t('hub.dlClearedRefs', { count: refd })}` : ''
      if (res.files_deleted.length > 0) {
        toast('success', t('hub.dlCleared', { count: n }), {
          body:
            skipped > 0
              ? `${t('hub.dlClearedFiles', { count: res.files_deleted.length })} · ${t('hub.dlClearSkipped', { count: skipped })}${refNote}`
              : `${t('hub.dlClearedFiles', { count: res.files_deleted.length })}${refNote}`,
        })
      } else if (skipped > 0) {
        // asked to reclaim space but nothing was deleted → warn, never
        // silent; NO ref note here — no file was deleted, so no reference
        // was broken
        toast('warning', t('hub.dlCleared', { count: n }), {
          body: t('hub.dlClearSkipped', { count: skipped }),
        })
      } else {
        toast('success', t('hub.dlCleared', { count: n }))
      }
    }
  } catch (e) {
    toast('error', t('hub.dlClearFailed'), {
      body: e instanceof ApiError && e.detail ? e.detail : String(e),
    })
  }
}

/** Ask the server (same machine as the browser) to reveal a completed
    download's file in the OS file manager. Errors surface honestly. */
export async function revealDownload(taskId: string) {
  try {
    await hubReveal(taskId)
  } catch (e) {
    toast('error', t('hub.dlOpenFolderFailed'), {
      body: e instanceof ApiError && e.detail ? e.detail : String(e),
    })
  }
}

/** Open the "load now?" dialog for a completed download (any page). */
export function openLoadNow(task: HubTask) {
  loadTarget.value = task
}

/** Load the downloaded file into the backend — used by the HubPage dialog
    AND the terminal-toast action, so it must live in the store. */
export async function loadFromDownload() {
  const task = loadTarget.value
  if (!task) return
  loadingNow.value = true
  try {
    const c = await fetchConfig().catch(() => null)
    const buf = numVal(c?.config.default_buffer_mb?.value, 64)
    const ctx = numVal(c?.config.default_n_ctx?.value, 2048)
    await loadModel({
      model_id: suggestModelId(task.filename),
      model_path: task.target_path,
      buffer_mb: buf,
      n_ctx: ctx,
    })
    // refresh the shell's model chip honestly
    models.value = await apiJSON<ModelStatus[]>('/v1/models', undefined, { timeoutMs: 5000 })
    toast('success', t('hub.loadStarted', { id: suggestModelId(task.filename) }))
    loadTarget.value = null
  } catch (e) {
    toast('error', t('hub.loadFailed'), {
      body: e instanceof ApiError && e.detail ? e.detail : String(e),
    })
  } finally {
    loadingNow.value = false
  }
}

/* ── one live toast per download (spec §8.4 progress variant) ──── */

const toastIds = new Map<string, number>()

function renderTaskToast(task: HubTask, prev?: HubTask) {
  let id = toastIds.get(task.id)
  // unchanged frame (SSE repeats full state every 0.5s) → nothing to do
  if (prev && prev.status === task.status && prev.bytes_downloaded === task.bytes_downloaded) return
  if (task.status === 'downloading' || task.status === 'queued') {
    if (id == null) {
      id = toast('info', t('hub.dlStarted'), {
        body: t('hub.dlStartedBody', { filename: task.filename, dir: task.target_dir }),
        sticky: true,
      })
      toastIds.set(task.id, id)
    } else {
      updateToast(id, { body: progressLine(task) })
    }
    return
  }
  if (id == null) return // terminal event for a task we did not start here
  if (task.status === 'done') {
    updateToast(id, {
      kind: 'success',
      title: t('hub.dlDone'),
      body: t('hub.dlDoneBody', { filename: task.filename }),
      actionLabel: t('hub.loadNow'),
      onAction: () => openLoadNow(task),
    })
    armDismiss(id, 8000)
  } else if (task.status === 'failed') {
    updateToast(id, {
      kind: 'error',
      title: t('hub.dlFailed'),
      body: task.error ?? undefined, // real server error, no dressing up
    })
  } else if (task.status === 'cancelled') {
    updateToast(id, { kind: 'info', title: t('hub.dlCancelledToast'), body: task.filename })
    armDismiss(id)
  }
  toastIds.delete(task.id)
}

/** Compact progress line used by the toast AND the downloads panel. */
export function progressLine(task: HubTask): string {
  const parts: string[] = []
  parts.push(
    task.percent != null ? `${fmtNumber(task.percent, { maximumFractionDigits: 1 })}%` : '–%',
  )
  parts.push(
    task.total_bytes != null
      ? t('hub.dlBytes', { done: fmtBytes(task.bytes_downloaded), total: fmtBytes(task.total_bytes) })
      : t('hub.dlUnknownTotal', { done: fmtBytes(task.bytes_downloaded) }),
  )
  const speed = fmtSpeed(task.speed_bps)
  if (speed) parts.push(t('hub.dlSpeed', { speed }))
  const eta = fmtEta(task.eta_s)
  if (eta) parts.push(t('hub.dlEta', { eta }))
  return parts.join(' · ')
}

/* ── boot ──────────────────────────────────────────────────────── */

let syncStarted = false

/** Wire the module-level watcher once at app boot. Downloads continue
    progressing across page navigation; focus return catches up quickly. */
export function startDownloadsSync() {
  if (syncStarted) return
  syncStarted = true
  void refreshDownloads()
  refreshOnFocus(refreshDownloads)
}

function numVal(v: unknown, fallback: number): number {
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) && n > 0 ? n : fallback
}

/* 🌐 Hub (spec §9.6) — search-first GGUF discovery on Hugging Face,
   one-click download with REAL progress (SSE), downloads panel, curated
   client-side shelves, target-dir selector and an honest offline banner.

   P5.1 (user-feedback round): roomier result cards with a colour+emoji
   category chip and tag badges; an on-demand Model detail drawer (quick
   guide + full details, RAM-per-quant computed from REAL bytes); and a
   shard-aware, quant-grouped file picker that shows real MB/GB per file.

   Honest telemetry (ADR-003): every byte/percent/speed/ETA shown here comes
   straight from the server's SSE frames — this page never estimates,
   smooths, or fabricates. HF unreachable → a truthful banner, never a fake
   list. Fields HF does not provide render as n/a, never invented.

   Drawer direction (cross-phase rule 6 + Drawer.tsx CONVENTION): the detail
   and file triggers sit in the RIGHT-hand area of their cards, so both
   drawers slide in from the RIGHT (explicit `side`, not by accident of the
   default). */
import { useEffect, useRef } from 'preact/hooks'
import { useSignal } from '@preact/signals'
import {
  Download,
  DownloadCloud,
  ExternalLink,
  FileBox,
  FolderOpen,
  Globe,
  HardDriveDownload,
  Heart,
  Inbox,
  Info,
  RefreshCw,
  Search,
  WifiOff,
  XCircle,
} from 'lucide-preact'
import { ApiError, apiJSON, type ModelStatus } from '@/core/api'
import { models } from '@/core/store'
import {
  HUB_TERMINAL,
  fmtBytes,
  fmtEta,
  fmtSpeed,
  hfRepoUrl,
  hubCancel,
  hubDownload,
  hubDownloads,
  hubModel,
  hubSearch,
  modelCategory,
  modelFeatures,
  repoAuthor,
  repoName,
  subscribeHubProgress,
  type HubDetailFile,
  type HubModelDetail,
  type HubSearchResult,
  type HubSort,
  type HubTask,
} from '@/core/hub'
import { browseDir, loadModel, suggestModelId } from '@/core/models'
import { fetchConfig, type ServerConfigResponse } from '@/core/config'
import { hubFocusQuery } from '@/core/nav-hints'
import { Badge } from '@/components/Badge'
import { Button } from '@/components/Button'
import { Card } from '@/components/Card'
import { Dialog } from '@/components/Dialog'
import { Drawer } from '@/components/Drawer'
import { EmptyState } from '@/components/EmptyState'
import { Tip } from '@/components/Tip'
import { Segmented } from '@/components/Segmented'
import { armDismiss, toast, updateToast } from '@/components/Toast'
import { fmtNumber, fmtRelative, locale, t } from '@/i18n'
import { ModelDetailDrawer, detailErrorMessage } from './ModelDetailDrawer'
import { FilesDrawer } from './FilesDrawer'

/* ── Curated shelves: a small hand-maintained list of SEARCH TERMS.
      Nothing here is fetched, ranked, or endorsed — clicking an item just
      runs the same honest search (the label says exactly that). ── */
interface Shelf {
  titleKey: string
  terms: string[]
}
const SHELVES: Shelf[] = [
  { titleKey: 'hub.shelf16gb', terms: ['qwen2.5 7b', 'llama 3.1 8b', 'mistral 7b', 'phi 3.5'] },
  { titleKey: 'hub.shelfMoe', terms: ['mixtral 8x7b', 'qwen2 57b a14b', 'deepseek v2 lite'] },
  { titleKey: 'hub.shelfThai', terms: ['typhoon', 'sea-lion', 'thai llama'] },
]

const SORTS: HubSort[] = ['downloads', 'likes', 'recent']

interface SearchError {
  status?: number
  detail: string
}

interface DetailError {
  repo: string
  status?: number
  detail: string
}

export function HubPage() {
  locale.value // subscribe: relative times re-render on language switch

  const query = useSignal('')
  const sort = useSignal<HubSort>('downloads')
  const searching = useSignal(false)
  const searched = useSignal(false) // false → show shelves (nothing fetched yet)
  const results = useSignal<HubSearchResult[]>([])
  const searchError = useSignal<SearchError | null>(null)

  const cfg = useSignal<ServerConfigResponse | null>(null)
  const targetDir = useSignal('') // '' = server default (first allowed dir)

  const detailRepo = useSignal<string | null>(null) // model-detail drawer
  const filesRepo = useSignal<string | null>(null) // file-picker drawer
  // on-demand detail cache (server also caches ~15 min — repeat opens are instant)
  const detailCache = useSignal<Record<string, HubModelDetail>>({})
  const detailLoading = useSignal<string | null>(null)
  const detailError = useSignal<DetailError | null>(null)

  const downloadsOpen = useSignal(false) // downloads-panel drawer

  const tasks = useSignal<Record<string, HubTask>>({})
  const taskOrder = useSignal<string[]>([])
  const loadTarget = useSignal<HubTask | null>(null) // "load now?" dialog
  const loadingNow = useSignal(false)

  const seqRef = useRef(0) // debounce race guard: latest search wins
  const subsRef = useRef<Map<string, () => void>>(new Map())
  const toastIds = useRef<Map<string, number>>(new Map())
  const fallbackTimers = useRef<Map<string, number>>(new Map())

  const runSearch = async (q: string, s: HubSort) => {
    const seq = ++seqRef.current
    searching.value = true
    searchError.value = null
    try {
      const res = await hubSearch(q, s)
      if (seq !== seqRef.current) return // stale
      results.value = res.results
      searched.value = true
    } catch (e) {
      if (seq !== seqRef.current) return
      searched.value = true
      searchError.value = {
        status: e instanceof ApiError ? e.status : undefined,
        detail: e instanceof ApiError && e.detail ? e.detail : String(e),
      }
      results.value = []
    } finally {
      if (seq === seqRef.current) searching.value = false
    }
  }

  // Debounced search (spec: 400ms) — fires for query AND sort changes.
  // An empty query returns to the curated shelves (nothing is fetched —
  // honest: no implicit network call on first paint).
  useEffect(() => {
    const q = query.value
    const s = sort.value
    if (q.trim() === '') {
      seqRef.current++ // cancel any in-flight search
      searching.value = false
      searched.value = false
      searchError.value = null
      return
    }
    const timer = window.setTimeout(() => void runSearch(q, s), 400)
    return () => window.clearTimeout(timer)
  }, [query.value, sort.value])

  useEffect(() => {
    // models dirs + load defaults for the "load now?" follow-up
    void fetchConfig()
      .then((c) => (cfg.value = c))
      .catch(() => undefined)
    // existing downloads survive page navigation (tasks live on the server)
    void refreshTasks()
    // a Models-page "find in Hub" shortcut may carry a search term (once)
    const focus = hubFocusQuery.value
    if (focus) {
      hubFocusQuery.value = ''
      query.value = focus // the debounce effect above will fire the search
    }
    return () => {
      subsRef.current.forEach((stop) => stop())
      subsRef.current.clear()
      fallbackTimers.current.forEach((id) => window.clearInterval(id))
      fallbackTimers.current.clear()
    }
  }, [])

  const refreshTasks = async () => {
    try {
      const res = await hubDownloads()
      applyTasks(res.downloads)
      // re-attach the live feed to anything still running (e.g. a download
      // started before a page navigation — tasks outlive the page component)
      for (const task of res.downloads) {
        if (!HUB_TERMINAL.includes(task.status)) watch(task.id)
      }
    } catch {
      /* the panel shows the last known state; the health dot tells the story */
    }
  }

  const applyTasks = (list: HubTask[]) => {
    const next: Record<string, HubTask> = {}
    for (const task of list) next[task.id] = task
    tasks.value = next
    taskOrder.value = list.map((tk) => tk.id).reverse() // newest first
  }

  const setTask = (task: HubTask) => {
    const prev = tasks.value[task.id]
    tasks.value = { ...tasks.value, [task.id]: task }
    if (!taskOrder.value.includes(task.id)) taskOrder.value = [task.id, ...taskOrder.value]
    renderTaskToast(task, prev)
    if (HUB_TERMINAL.includes(task.status)) {
      stopWatching(task.id)
      void refreshTasks() // settle the panel list (server is source of truth)
    }
  }

  /* One live toast per download: created sticky at start, updated with REAL
     numbers from each SSE frame, resolved to success/error at the end. */
  const renderTaskToast = (task: HubTask, prev?: HubTask) => {
    let id = toastIds.current.get(task.id)
    if (prev && prev.status === task.status && prev.bytes_downloaded === task.bytes_downloaded) return
    if (task.status === 'downloading' || task.status === 'queued') {
      if (id == null) {
        id = toast('info', t('hub.dlStarted'), {
          body: t('hub.dlStartedBody', { filename: task.filename, dir: task.target_dir }),
          sticky: true,
        })
        toastIds.current.set(task.id, id)
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
        onAction: () => (loadTarget.value = task),
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
    toastIds.current.delete(task.id)
  }

  const progressLine = (task: HubTask): string => {
    const parts: string[] = []
    parts.push(
      task.percent != null
        ? `${fmtNumber(task.percent, { maximumFractionDigits: 1 })}%`
        : '–%',
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

  const watch = (taskId: string) => {
    if (subsRef.current.has(taskId)) return
    const stop = subscribeHubProgress(
      taskId,
      (frame) => setTask(frame),
      () => startFallbackPoll(taskId), // SSE dropped mid-flight → poll until terminal
    )
    subsRef.current.set(taskId, stop)
  }

  const startFallbackPoll = (taskId: string) => {
    if (fallbackTimers.current.has(taskId)) return
    const timer = window.setInterval(async () => {
      if (document.hidden) return // visibility-aware like the SSE path
      try {
        const res = await hubDownloads()
        const task = res.downloads.find((tk) => tk.id === taskId)
        if (task) setTask(task)
        if (!task || HUB_TERMINAL.includes(task.status)) {
          const t0 = fallbackTimers.current.get(taskId)
          if (t0) window.clearInterval(t0)
          fallbackTimers.current.delete(taskId)
        }
      } catch {
        /* keep polling — the health dot shows the outage */
      }
    }, 2000)
    fallbackTimers.current.set(taskId, timer)
  }

  const stopWatching = (taskId: string) => {
    subsRef.current.get(taskId)?.()
    subsRef.current.delete(taskId)
    const timer = fallbackTimers.current.get(taskId)
    if (timer) window.clearInterval(timer)
    fallbackTimers.current.delete(taskId)
  }

  const startDownload = async (repoId: string, filename: string) => {
    try {
      const task = await hubDownload(repoId, filename, targetDir.value || undefined)
      setTask(task)
      watch(task.id)
    } catch (e) {
      toast('error', t('hub.dlFailed'), {
        body: e instanceof ApiError && e.detail ? e.detail : String(e),
      })
    }
  }

  // Queue every shard of a quant one after another through the same
  // download+SSE flow (the server has no batch endpoint — honest and simple).
  const downloadGroup = async (repoId: string, files: HubDetailFile[]) => {
    for (const f of files) {
      // eslint-disable-next-line no-await-in-loop
      await startDownload(repoId, f.filename)
    }
  }

  /* ── On-demand model detail (lazy, cached) ─────────────────────── */

  const ensureDetail = async (repoId: string) => {
    if (detailCache.value[repoId]) return
    if (detailLoading.value === repoId) return
    detailLoading.value = repoId
    detailError.value = null
    try {
      const d = await hubModel(repoId)
      detailCache.value = { ...detailCache.value, [repoId]: d }
    } catch (e) {
      detailError.value = { repo: repoId, ...detailErrorMessage(e) }
    } finally {
      if (detailLoading.value === repoId) detailLoading.value = null
    }
  }

  const openDetail = (repoId: string) => {
    detailRepo.value = repoId
    void ensureDetail(repoId)
  }

  const openFiles = (repoId: string) => {
    filesRepo.value = repoId
    void ensureDetail(repoId)
  }

  const doCancel = async (taskId: string) => {
    try {
      const task = await hubCancel(taskId)
      setTask(task)
    } catch (e) {
      toast('error', t('common.notAvailable'), {
        body: e instanceof ApiError && e.detail ? e.detail : String(e),
      })
    }
  }

  const doLoad = async () => {
    const task = loadTarget.value
    if (!task) return
    loadingNow.value = true
    const c = cfg.value
    const buf = numVal(c?.config.default_buffer_mb?.value, 64)
    const ctx = numVal(c?.config.default_n_ctx?.value, 2048)
    try {
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

  const onBrowseTarget = async () => {
    try {
      const res = await browseDir()
      if (res.path) targetDir.value = res.path
      else if (res.error) toast('error', t('models.scan.browseFailed'), { body: res.error })
    } catch (e) {
      toast('error', t('models.scan.browseFailed'), {
        body: e instanceof ApiError && e.detail ? e.detail : undefined,
      })
    }
  }

  const offline = searchError.value?.status === 502 || searchError.value?.status === 503
  const activeTasks = taskOrder.value
    .map((id) => tasks.value[id])
    .filter((tk): tk is HubTask => !!tk)
  const liveCount = activeTasks.filter((tk) => !HUB_TERMINAL.includes(tk.status)).length

  // detail-drawer view state
  const dRepo = detailRepo.value
  const fRepo = filesRepo.value
  const detailErrFor = (repo: string | null): { status?: number; detail: string } | null =>
    detailError.value && detailError.value.repo === repo ? detailError.value : null

  return (
    <div class="page">
      <header class="page__header">
        <h1 class="page__title">
          <span aria-hidden="true">🌐</span> {t('nav.hub')}
        </h1>
        <Button variant="ghost" onClick={() => { downloadsOpen.value = true; void refreshTasks() }}>
          <Inbox size={15} aria-hidden="true" /> {t('hub.dlTitle')}
          {liveCount > 0 ? <span class="nav-badge">{liveCount}</span> : null}
        </Button>
      </header>
      <p class="hub-tagline dialog-text--dim">{t('hub.tagline')}</p>

      {/* ── Search bar ─────────────────────────────────────────── */}
      <Card tier="raised" class="hub-search">
        <div class="hub-search__box">
          <Search size={15} aria-hidden="true" />
          <input
            class="md-input hub-search__input"
            type="search"
            placeholder={t('hub.searchPlaceholder')}
            value={query.value}
            aria-label={t('hub.searchPlaceholder')}
            onInput={(e) => (query.value = (e.target as HTMLInputElement).value)}
          />
          {searching.value ? <span class="btn__spinner" aria-hidden="true" /> : null}
        </div>
        <Segmented
          ariaLabel={t('hub.sort')}
          size="sm"
          value={sort.value}
          onChange={(v) => (sort.value = v as HubSort)}
          options={[
            { value: 'downloads', label: t('hub.sortDownloads') },
            { value: 'likes', label: t('hub.sortLikes') },
            { value: 'recent', label: t('hub.sortRecent') },
          ]}
        />
      </Card>

      {/* ── Offline / error banner (honest — never a fake list) ── */}
      {searchError.value ? (
        offline ? (
          <Card class="hub-banner hub-banner--offline">
            <WifiOff size={18} aria-hidden="true" />
            <div class="hub-banner__text">
              <strong>{t('hub.offlineTitle')}</strong>
              <p>{t('hub.offlineBody')}</p>
              <p class="dialog-text--dim">{t('hub.offlineManual')}</p>
            </div>
            <a
              class="btn btn--soft btn--sm"
              href="https://huggingface.co/"
              target="_blank"
              rel="noopener noreferrer"
            >
              <ExternalLink size={13} aria-hidden="true" /> {t('hub.offlineOpen')}
            </a>
          </Card>
        ) : (
          <Card class="hub-banner">
            <XCircle size={18} aria-hidden="true" />
            <div class="hub-banner__text">
              <strong>{t('hub.errorTitle')}</strong>
              <p>{searchError.value.detail}</p>
            </div>
            <Button variant="soft" size="sm" onClick={() => void runSearch(query.value, sort.value)}>
              <RefreshCw size={13} aria-hidden="true" /> {t('common.retry')}
            </Button>
          </Card>
        )
      ) : null}

      {/* ── Curated shelves (only before the first search) ─────── */}
      {!searched.value && !searchError.value ? (
        <div class="hub-shelves">
          <p class="hub-shelves__label">
            {t('hub.shelvesLabel')}
            <Tip label={t('hub.shelvesHint')} />
          </p>
          {SHELVES.map((shelf) => (
            <section key={shelf.titleKey} class="hub-shelf">
              <h2 class="hub-shelf__title">{t(shelf.titleKey)}</h2>
              <div class="hub-shelf__chips">
                {shelf.terms.map((term) => (
                  <button key={term} class="hub-chip" onClick={() => (query.value = term)}>
                    <Globe size={12} aria-hidden="true" /> {term}
                  </button>
                ))}
              </div>
            </section>
          ))}
        </div>
      ) : null}

      {/* ── Results ────────────────────────────────────────────── */}
      {searched.value && !searchError.value ? (
        results.value.length === 0 ? (
          <Card>
            <EmptyState emoji="🔍" title={t('hub.emptyTitle')} body={t('hub.emptyBody')} />
          </Card>
        ) : (
          <>
            <p class="hub-count tnum">{t('hub.resultsCount', { count: results.value.length })}</p>
            <div class="hub-grid">
              {results.value.map((r) => (
                <HubCard
                  key={r.repo_id}
                  r={r}
                  onViewDetail={() => openDetail(r.repo_id)}
                  onViewFiles={() => openFiles(r.repo_id)}
                />
              ))}
            </div>
          </>
        )
      ) : null}

      <p class="set-note hub-authnote">
        <Tip label={t('hub.authNote')} /> {t('hub.authNote')}
      </p>

      {/* ── Model detail drawer (trigger = card right → right sheet) ── */}
      <ModelDetailDrawer
        open={dRepo !== null}
        onClose={() => (detailRepo.value = null)}
        detail={dRepo ? detailCache.value[dRepo] ?? null : null}
        loading={detailLoading.value === dRepo && dRepo !== null}
        error={detailErrFor(dRepo)}
        onRetry={() => {
          if (dRepo) void ensureDetail(dRepo)
        }}
      />

      {/* ── File picker drawer (trigger = card right → right sheet) ── */}
      <FilesDrawer
        open={fRepo !== null}
        onClose={() => (filesRepo.value = null)}
        detail={fRepo ? detailCache.value[fRepo] ?? null : null}
        loading={detailLoading.value === fRepo && fRepo !== null}
        error={detailErrFor(fRepo)}
        onRetry={() => {
          if (fRepo) void ensureDetail(fRepo)
        }}
        modelsDirs={cfg.value?.models_dirs ?? []}
        targetDir={targetDir.value}
        onTargetDir={(v) => (targetDir.value = v)}
        onBrowse={() => void onBrowseTarget()}
        onDownloadFile={(repo, file) => void startDownload(repo, file)}
        onDownloadGroup={(repo, files) => void downloadGroup(repo, files)}
      />

      {/* ── Downloads panel drawer (trigger = page header RIGHT → right sheet) ── */}
      <Drawer open={downloadsOpen.value} onClose={() => (downloadsOpen.value = false)} title={t('hub.dlTitle')} side="right">
        {activeTasks.length === 0 ? (
          <EmptyState emoji="📥" title={t('hub.dlEmpty')} />
        ) : (
          <ul class="hub-dllist">
            {activeTasks.map((task) => (
              <li key={task.id} class="hub-dl">
                <div class="hub-dl__head">
                  <span class="hub-dl__name" title={`${task.repo_id}/${task.filename}`}>
                    {task.filename}
                  </span>
                  <Badge tone={statusTone(task.status)}>{t(`hub.dlStatus_${task.status}`)}</Badge>
                </div>
                <div class="hub-dl__path dialog-text--dim" title={task.target_path}>
                  → {task.target_dir}
                </div>
                {task.status === 'downloading' || task.status === 'queued' ? (
                  <>
                    <div
                      class="hub-dl__bar"
                      role="progressbar"
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={task.percent != null ? Math.round(task.percent) : undefined}
                      aria-label={task.filename}
                    >
                      <span style={{ width: `${task.percent != null ? Math.min(100, task.percent) : 100}%` }} class={task.percent == null ? 'is-indeterminate' : ''} />
                    </div>
                    <div class="hub-dl__nums tnum">{progressLine(task)}</div>
                  </>
                ) : null}
                {task.status === 'failed' && task.error ? <p class="hub-dl__error">{task.error}</p> : null}
                <div class="hub-dl__actions">
                  {task.status === 'downloading' || task.status === 'queued' ? (
                    <Button variant="danger" size="sm" onClick={() => void doCancel(task.id)}>
                      <XCircle size={13} aria-hidden="true" /> {t('hub.dlCancel')}
                    </Button>
                  ) : null}
                  {task.status === 'done' ? (
                    <Button variant="primary" size="sm" onClick={() => (loadTarget.value = task)}>
                      <HardDriveDownload size={13} aria-hidden="true" /> {t('hub.loadNow')}
                    </Button>
                  ) : null}
                  {task.status === 'failed' || task.status === 'cancelled' ? (
                    <>
                      <Button variant="soft" size="sm" onClick={() => void startDownload(task.repo_id, task.filename)}>
                        <RefreshCw size={13} aria-hidden="true" /> {t('hub.dlRetry')}
                      </Button>
                      <span class="hub-dl__retrynote">
                        <Tip label={t('hub.dlRetryNote')} />
                      </span>
                    </>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
        <p class="set-note">
          <Tip label={t('hub.resumeNa')} /> {t('hub.resumeNa')} · {t('hub.deleteNa')}
        </p>
      </Drawer>

      {/* ── "Load now?" confirm (spec §9.6: เสร็จ → ชวนโหลด) ────── */}
      <Dialog
        open={loadTarget.value !== null}
        onClose={() => (loadingNow.value ? undefined : (loadTarget.value = null))}
        title={t('hub.loadNow')}
        size="sm"
        footer={
          <>
            <Button variant="ghost" disabled={loadingNow.value} onClick={() => (loadTarget.value = null)}>
              {t('common.cancel')}
            </Button>
            <Button variant="primary" loading={loadingNow.value} onClick={() => void doLoad()}>
              <HardDriveDownload size={14} aria-hidden="true" /> {t('hub.loadNowGo')}
            </Button>
          </>
        }
      >
        <p class="dialog-text">
          <FileBox size={15} aria-hidden="true" /> {t('hub.loadNowBody', { filename: loadTarget.value?.filename ?? '' })}
        </p>
        <p class="dialog-text dialog-text--dim">{t('hub.loadNowNote')}</p>
      </Dialog>

    </div>
  )
}

function HubCard({
  r,
  onViewDetail,
  onViewFiles,
}: {
  r: HubSearchResult
  onViewDetail: () => void
  onViewFiles: () => void
}) {
  const quants = Array.from(new Set(r.files.map((f) => f.quant).filter((q): q is string => !!q)))
  const shown = quants.slice(0, 4)
  const author = r.author ?? repoAuthor(r.repo_id)
  const updated = r.last_modified ? new Date(r.last_modified).getTime() : null
  const cat = modelCategory(r.pipeline_tag, r.tags)
  const features = modelFeatures(r.tags)
  return (
    <Card hoverable class="hub-card">
      <div class="hub-card__head">
        <button class="hub-card__name" onClick={onViewDetail} title={t('hub.detailTitle')}>
          {repoName(r.repo_id)}
        </button>
        <a
          class="hub-card__ext"
          href={hfRepoUrl(r.repo_id)}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`${r.repo_id} — huggingface.co`}
        >
          <ExternalLink size={13} aria-hidden="true" />
        </a>
      </div>
      <div class="hub-card__sub">
        <span class={`hub-cat hub-cat--${cat.id}`} title={t(cat.labelKey)}>
          <span aria-hidden="true">{cat.emoji}</span> {t(cat.labelKey)}
        </span>
        {author ? <span class="hub-card__author dialog-text--dim">{author}</span> : null}
      </div>
      <div class="hub-card__badges">
        {shown.map((q) => (
          <Badge key={q} tone="brand">
            {q}
          </Badge>
        ))}
        {quants.length > shown.length ? <Badge tone="neutral">+{quants.length - shown.length}</Badge> : null}
        {r.files[0]?.size_label ? <Badge tone="neutral">{r.files[0].size_label}</Badge> : null}
      </div>
      {features.length > 0 ? (
        <div class="hub-card__feats">
          {features.map((key) => (
            <span key={key} class="hub-card__feat">
              {t(key)}
            </span>
          ))}
        </div>
      ) : null}
      <div class="hub-card__stats tnum">
        {/* honest telemetry (ADR-003): a search payload may omit likes — and
            rarely downloads — so hide each stat on null instead of rendering a
            fabricated 0. The detail drawer shows n/a for the same fields. This
            matches the card's established pattern (likes already hid on null). */}
        {r.downloads != null ? (
          <span title={t('hub.downloads')}>
            <Download size={12} aria-hidden="true" /> {fmtNumber(r.downloads)}
          </span>
        ) : null}
        {r.likes != null ? (
          <span title={t('hub.likes')}>
            <Heart size={12} aria-hidden="true" /> {fmtNumber(r.likes)}
          </span>
        ) : null}
        <span title={t('hub.filesCount', { count: r.files.length })}>
          <FileBox size={12} aria-hidden="true" /> {r.files.length}
        </span>
        {updated && Number.isFinite(updated) ? (
          <span class="hub-card__updated">{t('hub.updated', { when: fmtRelative(updated) })}</span>
        ) : null}
      </div>
      {/* triggers live on the RIGHT edge of the card → the drawers slide
          in from the right (Drawer CONVENTION, cross-phase rule 6) */}
      <div class="hub-card__actions">
        <Button variant="ghost" size="sm" onClick={onViewDetail}>
          <Info size={13} aria-hidden="true" /> {t('hub.details')}
        </Button>
        <Button variant="soft" size="sm" onClick={onViewFiles}>
          <DownloadCloud size={13} aria-hidden="true" /> {t('hub.viewFiles')}
        </Button>
      </div>
    </Card>
  )
}

function statusTone(status: HubTask['status']): 'neutral' | 'info' | 'ok' | 'error' {
  if (status === 'done') return 'ok'
  if (status === 'failed') return 'error'
  if (status === 'downloading' || status === 'queued') return 'info'
  return 'neutral'
}

function numVal(v: unknown, fallback: number): number {
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) && n > 0 ? n : fallback
}

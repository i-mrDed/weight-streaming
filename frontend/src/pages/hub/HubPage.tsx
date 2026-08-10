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
  Play,
  RefreshCw,
  Search,
  Trash2,
  WifiOff,
  XCircle,
} from 'lucide-preact'
import { ApiError } from '@/core/api'
import {
  activeDownloads,
  cancelDownload,
  clearFinished,
  deleteDownload,
  downloads,
  downloadOrder,
  downloadsLiveCount,
  loadFromDownload,
  loadingNow,
  loadTarget,
  openLoadNow,
  progressLine,
  refreshDownloads,
  resumeDownload,
  revealDownload,
  startDownload,
} from '@/core/downloads'
import {
  fmtBytes,
  hfRepoUrl,
  HUB_TERMINAL,
  hubModel,
  hubSearch,
  hubSearchPage,
  modelCategory,
  modelFeatures,
  repoAuthor,
  repoName,
  type HubDetailFile,
  type HubModelDetail,
  type HubSearchResult,
  type HubSort,
  type HubTask,
} from '@/core/hub'
import { browseDir, suggestModelId } from '@/core/models'
import { assistants, refreshAssistants } from '@/core/assistants'
// conversations are client-side (localStorage ws-chat-index-v1) — the delete
// dialogs count their references to a model file straight from the signal
import { convIndex } from '@/pages/chat/store'
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
import { toast } from '@/components/Toast'
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
  // confirm dialog for deleting a COMPLETED download (keep file vs delete too)
  const deleteTarget = useSignal<HubTask | null>(null)
  const deletingNow = useSignal(false)
  // confirm dialog for clearing ALL finished downloads (keep files vs delete too)
  const clearOpen = useSignal(false)
  const clearingNow = useSignal(false)
  const clearDeleteFiles = useSignal(false)

  // Latest GGUF feed (P5.2): a cursor-paginated "recent" browse shown on the
  // idle Hub (before any search) so users discover new models directly.
  // Real HF pagination — pages are cached so going back needs no refetch.
  const latestPage = useSignal(0) // 0-based
  const latestPages = useSignal<HubSearchResult[][]>([])
  const latestNext = useSignal<(string | null)[]>([]) // next_cursor after each page
  const latestLoading = useSignal(false)
  const latestError = useSignal<SearchError | null>(null)

  const seqRef = useRef(0) // debounce race guard: latest search wins

  const loadLatest = async (page: number): Promise<void> => {
    if (latestPages.value[page]) {
      latestPage.value = page
      return
    }
    latestLoading.value = true
    latestError.value = null
    try {
      const cursor = page === 0 ? null : latestNext.value[page - 1]
      const res = await hubSearchPage('recent', cursor)
      const pages = [...latestPages.value]
      pages[page] = res.results
      latestPages.value = pages
      const nxt = [...latestNext.value]
      nxt[page] = res.next_cursor ?? null
      latestNext.value = nxt
      latestPage.value = page
    } catch (e) {
      latestError.value = {
        status: e instanceof ApiError ? e.status : undefined,
        detail: e instanceof ApiError && e.detail ? e.detail : String(e),
      }
    } finally {
      latestLoading.value = false
    }
  }

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
    // existing downloads survive page navigation (tasks live on the server;
    // the shared store keeps their SSE/progress alive across pages)
    void refreshDownloads()
    // a Models-page "find in Hub" shortcut may carry a search term (once)
    const focus = hubFocusQuery.value
    if (focus) {
      hubFocusQuery.value = ''
      query.value = focus // the debounce effect above will fire the search
    } else {
      void loadLatest(0) // idle browse: surface the newest GGUF models
    }
  }, [])

  const activeTasks = activeDownloads.value
  const liveCount = downloadsLiveCount.value
  // finished rows (done/failed/cancelled) — candidates for "clear finished"
  const finishedTasks = activeTasks.filter((t) => HUB_TERMINAL.includes(t.status))
  // only DONE tasks own a model file — the checkbox is meaningful for those
  const doneCount = activeTasks.filter((t) => t.status === 'done').length

  // Cross-feature model references for the delete/clear confirm dialogs.
  // Conversations live client-side (convIndex signal) and assistants in the
  // shared store — both matched by suggestModelId(filename), the same id the
  // app uses when loading a downloaded model and creating conversations
  // against it. WARN, never block: deleting the file just means those
  // references cannot load the model until it is downloaded again.
  const delModelId = deleteTarget.value ? suggestModelId(deleteTarget.value.filename) : null
  const delConvRefs = delModelId ? convIndex.value.filter((c) => c.model === delModelId).length : 0
  const delAssistantCount = delModelId
    ? assistants.value.filter((a) => a.model_id === delModelId).length
    : 0
  const delRefsTotal = delConvRefs + delAssistantCount
  // done tasks whose suggested model id appears in a conversation or assistant
  const clearRefCount = clearDeleteFiles.value
    ? finishedTasks.filter((tk) => tk.status === 'done').filter((tk) => {
        const mid = suggestModelId(tk.filename)
        return (
          convIndex.value.some((c) => c.model === mid) ||
          assistants.value.some((a) => a.model_id === mid)
        )
      }).length
    : 0

  // Queue every shard of a quant one after another through the same
  // download+SSE flow (the server has no batch endpoint — honest and simple).
  const downloadGroup = async (repoId: string, files: HubDetailFile[]) => {
    for (const f of files) {
      // eslint-disable-next-line no-await-in-loop
      await startDownload(repoId, f.filename, targetDir.value || undefined)
    }
  }

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

  const confirmDelete = async (task: HubTask, deleteFile: boolean) => {
    deletingNow.value = true
    try {
      await deleteDownload(task.id, deleteFile)
      if (deleteTarget.value?.id === task.id) deleteTarget.value = null
    } finally {
      deletingNow.value = false
    }
  }

  const confirmClear = async () => {
    clearingNow.value = true
    try {
      await clearFinished(clearDeleteFiles.value)
      clearOpen.value = false
      clearDeleteFiles.value = false // reset for the next time
    } finally {
      clearingNow.value = false
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
        <Button variant="ghost" onClick={() => { downloadsOpen.value = true; void refreshDownloads() }}>
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

      {/* ── Latest GGUF feed (idle browse: newest models first) ── */}
      {!searched.value && !searchError.value ? (
        <section class="hub-latest">
          <h2 class="hub-latest__title">
            {t('hub.latestTitle')}
            <Tip label={t('hub.latestHint')} />
          </h2>
          {latestError.value ? (
            <Card class="hub-banner">
              <XCircle size={18} aria-hidden="true" />
              <div class="hub-banner__text">
                <strong>{t('hub.errorTitle')}</strong>
                <p>{latestError.value.detail}</p>
              </div>
              <Button variant="soft" size="sm" onClick={() => void loadLatest(latestPage.value)}>
                <RefreshCw size={13} aria-hidden="true" /> {t('common.retry')}
              </Button>
            </Card>
          ) : null}
          {latestLoading.value && !latestPages.value[latestPage.value] ? (
            <div class="hub-latest__loading">
              <span class="btn__spinner" aria-hidden="true" />
              <span class="dialog-text--dim">{t('hub.latestLoading')}</span>
            </div>
          ) : null}
          {latestPages.value[latestPage.value]?.length ? (
            <>
              <div class="hub-grid">
                {latestPages.value[latestPage.value].map((r) => (
                  <HubCard
                    key={r.repo_id}
                    r={r}
                    onViewDetail={() => openDetail(r.repo_id)}
                    onViewFiles={() => openFiles(r.repo_id)}
                  />
                ))}
              </div>
              <div class="hub-latest__pager">
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={latestPage.value === 0 || latestLoading.value}
                  onClick={() => void loadLatest(latestPage.value - 1)}
                >
                  {t('hub.pagePrev')}
                </Button>
                <span class="hub-latest__page tnum">
                  {t('hub.pageCounter', { page: latestPage.value + 1 })}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={!latestNext.value[latestPage.value] || latestLoading.value}
                  onClick={() => void loadLatest(latestPage.value + 1)}
                >
                  {t('hub.pageNext')}
                </Button>
              </div>
            </>
          ) : null}
        </section>
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
        onDownloadFile={(repo, file) => void startDownload(repo, file, targetDir.value || undefined)}
        onDownloadGroup={(repo, files) => void downloadGroup(repo, files)}
      />

      {/* ── Downloads panel drawer (trigger = page header RIGHT → right sheet) ── */}
      <Drawer open={downloadsOpen.value} onClose={() => (downloadsOpen.value = false)} title={t('hub.dlTitle')} side="right">
        {finishedTasks.length > 0 ? (
          <div class="hub-dl__toolbar">
            <Button
              variant="soft"
              size="sm"
              onClick={() => {
                clearDeleteFiles.value = false
                clearOpen.value = true
                void refreshAssistants() // fresh reference counts for the warning
              }}
            >
              <Trash2 size={13} aria-hidden="true" /> {t('hub.dlClearAll', { count: finishedTasks.length })}
            </Button>
          </div>
        ) : null}
        {activeTasks.length === 0 ? (
          <EmptyState emoji="📥" title={t('hub.dlEmpty')} />
        ) : (
          <ul class="hub-dllist">
            {activeTasks.map((tk) => {
              // live task from the shared store (SSE keeps it fresh)
              const task = downloads.value[tk.id] ?? tk
              return (
              <li key={task.id} class="hub-dl">
                <div class="hub-dl__head">
                  <span class="hub-dl__name" title={`${task.repo_id}/${task.filename}`}>
                    {task.filename}
                  </span>
                  <Badge tone={statusTone(task.status)}>{t(`hub.dlStatus_${task.status}`)}</Badge>
                </div>
                {/* full path on disk + REAL file size for a completed download
                    (server stat's it at serialization time — ADR-003 honest) */}
                <div class="hub-dl__path dialog-text--dim" title={task.target_path}>
                  <span aria-hidden="true">📁</span> {task.target_path}
                  {task.status === 'done' && task.file_size != null ? (
                    <span class="hub-dl__size tnum"> · {fmtBytes(task.file_size)}</span>
                  ) : null}
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
                    <Button variant="danger" size="sm" onClick={() => void cancelDownload(task.id)}>
                      <XCircle size={13} aria-hidden="true" /> {t('hub.dlCancel')}
                    </Button>
                  ) : null}
                  {task.status === 'done' ? (
                    <>
                      <Button variant="ghost" size="sm" onClick={() => void revealDownload(task.id)}>
                        <FolderOpen size={13} aria-hidden="true" /> {t('hub.dlOpenFolder')}
                      </Button>
                      <Button variant="primary" size="sm" onClick={() => openLoadNow(task)}>
                        <HardDriveDownload size={13} aria-hidden="true" /> {t('hub.loadNow')}
                      </Button>
                    </>
                  ) : null}
                  {task.status === 'failed' || task.status === 'cancelled' ? (
                    // v1.1: resume appends the kept .part (Range) — cheap vs
                    // the old retry that re-downloaded from byte 0.
                    <Button variant="soft" size="sm" onClick={() => void resumeDownload(task.id)}>
                      <Play size={13} aria-hidden="true" /> {t('hub.dlResume')}
                    </Button>
                  ) : null}
                  <Button
                    variant="ghost"
                    size="sm"
                    class="hub-dl__delete"
                    aria-label={t('hub.dlDelete')}
                    title={t('hub.dlDeleteTitle')}
                    onClick={() => {
                      // a completed download may own a model file — ask first
                      if (task.status === 'done') {
                        deleteTarget.value = task
                        void refreshAssistants() // fresh reference counts for the warning
                      } else void deleteDownload(task.id)
                    }}
                  >
                    <Trash2 size={13} aria-hidden="true" />
                  </Button>
                </div>
              </li>
              )
            })}
          </ul>
        )}
        <p class="set-note">
          <Tip label={t('hub.dlNote')} /> {t('hub.dlNote')}
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
            <Button variant="primary" loading={loadingNow.value} onClick={() => void loadFromDownload()}>
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

      {/* ── Delete confirm (done task: keep file vs delete file too) ── */}
      <Dialog
        open={deleteTarget.value !== null}
        onClose={() => (deletingNow.value ? undefined : (deleteTarget.value = null))}
        title={t('hub.dlDeleteDoneTitle')}
        size="sm"
        footer={
          <>
            <Button variant="ghost" disabled={deletingNow.value} onClick={() => (deleteTarget.value = null)}>
              {t('common.cancel')}
            </Button>
            <Button variant="soft" disabled={deletingNow.value} onClick={() => { const tk = deleteTarget.value; if (tk) void confirmDelete(tk, false) }}>
              {t('hub.dlDeleteKeepFile')}
            </Button>
            <Button variant="danger" disabled={deletingNow.value} onClick={() => { const tk = deleteTarget.value; if (tk) void confirmDelete(tk, true) }}>
              <Trash2 size={14} aria-hidden="true" /> {t('hub.dlDeleteFileToo')}
            </Button>
          </>
        }
      >
        <p class="dialog-text">
          <FileBox size={15} aria-hidden="true" />{' '}
          {t('hub.dlDeleteDoneBody', {
            filename: deleteTarget.value?.filename ?? '',
            size: fmtBytes(deleteTarget.value?.total_bytes ?? null),
          })}
        </p>
        <p class="dialog-text dialog-text--dim">{t('hub.dlDeleteWarn')}</p>
        {delRefsTotal > 0 ? (
          <p class="dialog-text dialog-text--warn">
            ⚠ {t('hub.dlDeleteRefs', { convs: delConvRefs, assistants: delAssistantCount })}
          </p>
        ) : null}
      </Dialog>

      {/* ── Clear-finished confirm (all terminal rows at once) ── */}
      <Dialog
        open={clearOpen.value}
        onClose={() => (clearingNow.value ? undefined : (clearOpen.value = false))}
        title={t('hub.dlClearAllTitle')}
        size="sm"
        footer={
          <>
            <Button variant="ghost" disabled={clearingNow.value} onClick={() => (clearOpen.value = false)}>
              {t('common.cancel')}
            </Button>
            <Button variant="danger" loading={clearingNow.value} onClick={() => void confirmClear()}>
              <Trash2 size={14} aria-hidden="true" /> {t('hub.dlClearAllGo', { count: finishedTasks.length })}
            </Button>
          </>
        }
      >
        <p class="dialog-text">
          <FileBox size={15} aria-hidden="true" />{' '}
          {t('hub.dlClearAllBody', { count: finishedTasks.length })}
        </p>
        {doneCount > 0 ? (
          <label class="hub-clear-opt">
            <input
              type="checkbox"
              checked={clearDeleteFiles.value}
              onChange={(e) => (clearDeleteFiles.value = (e.target as HTMLInputElement).checked)}
            />
            <span>{t('hub.dlClearFilesToo', { count: doneCount })}</span>
          </label>
        ) : null}
        <p class="dialog-text dialog-text--dim">
          {doneCount > 0 ? t('hub.dlClearWarn') : t('hub.dlClearNoFiles')}
        </p>
        {clearRefCount > 0 ? (
          <p class="dialog-text dialog-text--warn">
            ⚠ {t('hub.dlClearRefs', { count: clearRefCount })}
          </p>
        ) : null}
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


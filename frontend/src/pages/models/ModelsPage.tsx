/* 🧠 Models (spec §9.4) — loaded models + scan panel + load form + library.
   Endpoints: /v1/models, /v1/models/scan, /v1/models/load,
   /v1/models/unload, /v1/browse, /v1/browse-dir (all pre-existing), and
   P5: GET /v1/config (models_dirs) for the Library view + Hub shortcut.
   File DELETION stays OUT of v1 (spec — unauthenticated server; the tooltip
   says so honestly). Quant advisories from MODEL_GUIDE + ISSUE-011/018.
   `may_need_upgrade` → pip install hint. */
import { useEffect, useRef } from 'preact/hooks'
import { useSignal } from '@preact/signals'
import {
  BarChart3,
  FolderOpen,
  FolderSearch,
  Globe,
  HardDriveDownload,
  MessageSquare,
  RefreshCw,
  Search,
  XCircle,
} from 'lucide-preact'
import type { ModelStatus } from '@/core/api'
import { apiJSON, ApiError } from '@/core/api'
import { Card } from '@/components/Card'
import { Badge } from '@/components/Badge'
import { Button } from '@/components/Button'
import { Dialog } from '@/components/Dialog'
import { EmptyState } from '@/components/EmptyState'
import { Tip } from '@/components/Tip'
import { toast } from '@/components/Toast'
import { navigate } from '@/core/router'
import { models } from '@/core/store'
import { statsFocusModel, chatFocusModel, hubFocusQuery } from '@/core/nav-hints'
import { fetchConfig } from '@/core/config'
import {
  browseDir,
  browseFile,
  estimateVramMiB,
  fetchHardware,
  guessQuant,
  loadModel,
  MEASURED_TOK_S,
  QUANT_QUALITY_NOTES,
  quantAdvisory,
  quantSiblings,
  scanModels,
  suggestModelId,
  unloadModel,
  type HardwareInfo,
  type ScanModel,
} from '@/core/models'
import { fmtDateTime, fmtNumber, locale, relativeDay, t } from '@/i18n'

const LS_UNLOAD_REMEMBER = 'ws-unload-remember-session'

type SortKey = 'name' | 'size'

async function refreshModels() {
  try {
    models.value = await apiJSON<ModelStatus[]>('/v1/models', undefined, { timeoutMs: 5000 })
  } catch {
    /* health dot tells the story */
  }
}

function defaultThreads(): number {
  const cores = navigator.hardwareConcurrency || 4
  return Math.max(1, Math.round(cores / 2))
}

export function ModelsPage() {
  locale.value
  const loaded = models.value

  // scan state
  const scanDir = useSignal('')
  const scanning = useSignal(false)
  const scanResults = useSignal<ScanModel[] | null>(null)
  const scanError = useSignal('')
  const filter = useSignal('')
  const sort = useSignal<SortKey>('size')
  const browsingDir = useSignal(false)
  const scanSeqRef = useRef(0) // request-sequence guard: latest scan wins

  // load form state
  const loadPath = useSignal('')
  const loadId = useSignal('')
  const loadBuf = useSignal(64)
  const loadCtx = useSignal(2048)
  const loadThreads = useSignal(defaultThreads())
  // GPU-only (P7.5): -1 = auto, 0 = CPU, N = layers; '' = server default
  const loadGpuLayers = useSignal<number>(-1)
  const loadKvCache = useSignal('')
  const loadingModel = useSignal(false)

  // quant advisor (EXP-011): sibling quants + VRAM headroom
  const hw = useSignal<HardwareInfo | null>(null)

  // dialogs
  const unloadTarget = useSignal<string | null>(null)
  const reloadTarget = useSignal<ModelStatus | null>(null)
  const rememberUnload = useSignal(false)

  // library (P5): the model folders the server actually scans (GET /v1/config)
  const libDirs = useSignal<string[]>([])

  useEffect(() => {
    refreshModels()
    void fetchConfig()
      .then((c) => (libDirs.value = c.models_dirs))
      .catch(() => (libDirs.value = []))
    void fetchHardware()
      .then((h) => (hw.value = h))
      .catch(() => (hw.value = null))
  }, [])

  /** Loaded models whose file lives under a given scan dir (string prefix —
      an honest best effort: the server reports raw paths, no realpath API). */
  const loadedIn = (dir: string): ModelStatus[] => {
    const norm = dir.replace(/[\\/]+$/, '').replace(/\\/g, '/')
    return loaded.filter((m) => m.path.replace(/\\/g, '/').startsWith(norm + '/') || m.path.replace(/\\/g, '/') === norm)
  }

  const openHub = () => {
    hubFocusQuery.value = '' // no term — the Hub shows its curated shelves
    navigate('hub')
  }

  const runScan = async () => {
    const seq = ++scanSeqRef.current
    scanning.value = true
    scanError.value = ''
    try {
      const res = await scanModels(scanDir.value.trim() || undefined)
      if (seq !== scanSeqRef.current) return // stale response — a newer scan owns the UI
      scanResults.value = res.models
      toast('info', t('models.scan.done', { count: res.total }))
    } catch (e) {
      if (seq !== scanSeqRef.current) return // stale failure — don't clobber the newer scan
      scanError.value = e instanceof ApiError && e.detail ? e.detail : String(e)
    } finally {
      if (seq === scanSeqRef.current) scanning.value = false
    }
  }

  const onBrowseDir = async () => {
    browsingDir.value = true
    try {
      const res = await browseDir()
      if (res.path) scanDir.value = res.path
      else if (res.error) toast('error', t('models.scan.browseFailed'), { body: res.error })
    } catch (e) {
      toast('error', t('models.scan.browseFailed'), {
        body: e instanceof ApiError && e.detail ? e.detail : undefined,
      })
    } finally {
      browsingDir.value = false
    }
  }

  const onBrowseFile = async () => {
    try {
      const res = await browseFile()
      if (res.path) {
        loadPath.value = res.path
        if (!loadId.value.trim()) loadId.value = suggestModelId(res.path)
      } else if (res.error) {
        toast('error', t('models.scan.browseFailed'), { body: res.error })
      }
    } catch (e) {
      toast('error', t('models.scan.browseFailed'), {
        body: e instanceof ApiError && e.detail ? e.detail : undefined,
      })
    }
  }

  const pickScanResult = (m: ScanModel) => {
    loadPath.value = m.path
    loadId.value = suggestModelId(m.path)
  }

  const doUnload = async (id: string) => {
    try {
      await unloadModel(id)
      if (rememberUnload.value) sessionStorage.setItem(LS_UNLOAD_REMEMBER, '1')
      models.value = models.value.filter((m) => m.id !== id)
      toast('success', t('overview.models.unloaded', { id }))
      unloadTarget.value = null
    } catch (e) {
      toast('error', t('overview.models.unloadFailed'), {
        body: e instanceof ApiError && e.detail ? e.detail : undefined,
      })
    }
  }

  const doReload = async (m: ModelStatus) => {
    loadingModel.value = true
    try {
      await loadModel({
        model_id: m.id,
        model_path: m.path,
        buffer_mb: m.buffer_mb || 64,
        n_ctx: loadCtxDefault(m),
        force: true,
      })
      await refreshModels()
      toast('success', t('models.loaded.reload', { id: m.id }))
      reloadTarget.value = null
    } catch (e) {
      toast('error', t('models.loaded.reloadFailed'), {
        body: e instanceof ApiError && e.detail ? e.detail : undefined,
      })
    } finally {
      loadingModel.value = false
    }
  }

  const doLoad = async () => {
    if (!loadPath.value.trim() || !loadId.value.trim()) return
    loadingModel.value = true
    try {
      await loadModel({
        model_id: loadId.value.trim(),
        model_path: loadPath.value.trim(),
        buffer_mb: loadBuf.value,
        n_ctx: loadCtx.value,
        n_threads: loadThreads.value,
        gpu_layers: loadGpuLayers.value,
        kv_cache_type: loadKvCache.value.trim() === '' ? null : loadKvCache.value.trim(),
      })
      await refreshModels()
      toast('success', t('models.load.done', { id: loadId.value.trim() }), {
        actionLabel: t('models.load.openChat'),
        onAction: () => {
          chatFocusModel.value = loadId.value.trim()
          navigate('chat')
        },
      })
      loadPath.value = ''
      loadId.value = ''
    } catch (e) {
      toast('error', t('models.load.failed'), {
        body: e instanceof ApiError && e.detail ? e.detail : String(e),
      })
    } finally {
      loadingModel.value = false
    }
  }

  const visible = (scanResults.value ?? [])
    .filter((m) => (filter.value ? (m.name + m.architecture + (m.quant ?? '')).toLowerCase().includes(filter.value.toLowerCase()) : true))
    .sort((a, b) => (sort.value === 'size' ? b.size_bytes - a.size_bytes : a.name.localeCompare(b.name)))

  const loadQuant = guessQuant(loadPath.value)
  const advisory = quantAdvisory(loadQuant)

  // ── Quant advisor (EXP-011) ────────────────────────────────────────
  // When a model path is picked and scan results are available, list the
  // sibling quants and (if the GPU is known) suggest the smallest quant
  // that FITS total VRAM — the trade measured on this machine (IQ1_M 79
  // vs IQ2_M 56 tok/s at n-cpu-moe 0). Honest: no GPU info → show the
  // siblings without a fit claim.
  const siblings = loadPath.value ? quantSiblings(loadPath.value, scanResults.value) : []
  const totalVram = hw.value?.gpu?.total_vram_mb ?? null
  const pickedSize = scanResults.value?.find(
    (m) => m.path.replace(/\\/g, '/') === loadPath.value.replace(/\\/g, '/'),
  )?.size_bytes ?? 0
  const pickedVram = pickedSize > 0 ? estimateVramMiB(pickedSize, loadCtx.value) : null
  const picksGpu = loadGpuLayers.value !== 0 // -1 (auto) or N>0 → GPU offload
  const overVram = pickedVram != null && totalVram != null && picksGpu && pickedVram > totalVram
  const bestFit =
    totalVram != null && picksGpu
      ? siblings.find((s) => estimateVramMiB(s.size_bytes, loadCtx.value) <= totalVram) ?? null
      : null
  const bestQuant = bestFit ? guessQuant(bestFit.path) : null
  const bestTokS = bestQuant ? MEASURED_TOK_S[bestQuant] : null
  const pickedTokS = loadQuant ? MEASURED_TOK_S[loadQuant] : null
  const showQuantAdvisor =
    (siblings.length > 0 || overVram) && (bestFit || overVram)

  const switchToQuant = (path: string) => {
    loadPath.value = path
    // The id follows the file (same rule as the scan "Use in load form"):
    // swapping quant must not leave a stale id from the other file — a
    // load with mismatched id/path would register under the wrong name.
    loadId.value = suggestModelId(path)
  }

  return (
    <div class="page">
      <header class="page__header">
        <h1 class="page__title">
          <span aria-hidden="true">🧠</span> {t('nav.models')}
        </h1>
      </header>

      {/* ── Loaded models ─────────────────────────────────────── */}
      <section class="md-section">
        <h2 class="md-section__title">{t('models.loaded.title')}</h2>
        {loaded.length === 0 ? (
          <Card>
            <EmptyState emoji="💤" title={t('models.loaded.emptyTitle')} body={t('models.loaded.emptyBody')} />
          </Card>
        ) : (
          <div class="md-loaded">
            {loaded.map((m) => {
              const quant = guessQuant(m.path || m.id)
              return (
                <Card key={m.id} class="md-card">
                  <div class="md-card__head">
                    <span class="status-dot status-dot--online" aria-hidden="true" />
                    <span class="md-card__id" title={m.path}>{m.id}</span>
                  </div>
                  <div class="md-card__badges">
                    <Badge tone="neutral">{m.arch ?? 'unknown'}</Badge>
                    {quant ? <Badge tone="brand">{quant}</Badge> : null}
                    {m.n_experts > 0 ? <Badge tone="info">MoE · {fmtNumber(m.n_experts)} exp</Badge> : null}
                  </div>
                  <dl class="md-card__meta">
                    <div>
                      <dt>{t('models.loaded.buffer')}</dt>
                      <dd class="tnum">{fmtNumber(m.buffer_mb)} MB</dd>
                    </div>
                    <div>
                      <dt>{t('models.loaded.lastUsed')}</dt>
                      <dd>
                        {m.last_used ? (
                          <span title={fmtDateTime(new Date(m.last_used).getTime())}>
                            {relativeDay(new Date(m.last_used).getTime())}
                          </span>
                        ) : (
                          t('overview.models.neverUsed')
                        )}
                      </dd>
                    </div>
                  </dl>
                  <div class="md-card__actions">
                    <Button variant="danger" size="sm" onClick={() => {
                      if (sessionStorage.getItem(LS_UNLOAD_REMEMBER) === '1') doUnload(m.id)
                      else unloadTarget.value = m.id
                    }}>
                      <XCircle size={13} aria-hidden="true" /> {t('models.loaded.unload')}
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => (reloadTarget.value = m)}>
                      <RefreshCw size={13} aria-hidden="true" /> {t('models.loaded.reloadBtn')}
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => {
                      statsFocusModel.value = m.id
                      navigate('stats')
                    }}>
                      <BarChart3 size={13} aria-hidden="true" /> {t('models.loaded.viewStats')}
                    </Button>
                    <Button variant="soft" size="sm" onClick={() => {
                      chatFocusModel.value = m.id
                      navigate('chat')
                    }}>
                      <MessageSquare size={13} aria-hidden="true" /> {t('models.loaded.useChat')}
                    </Button>
                  </div>
                </Card>
              )
            })}
          </div>
        )}
      </section>

      {/* ── Scan panel ────────────────────────────────────────── */}
      <section class="md-section">
        <h2 class="md-section__title">
          {t('models.scan.title')}
          <Tip label={t('models.scan.tip')} />
        </h2>
        <Card class="md-scan">
          <div class="md-scan__row">
            <input
              class="md-input md-scan__dir"
              type="text"
              placeholder={t('models.scan.dirPlaceholder')}
              value={scanDir.value}
              onInput={(e) => (scanDir.value = (e.target as HTMLInputElement).value)}
              aria-label={t('models.scan.dirLabel')}
            />
            <Button variant="ghost" loading={browsingDir.value} onClick={onBrowseDir}>
              <FolderOpen size={14} aria-hidden="true" /> {t('models.scan.browse')}
            </Button>
            <Button variant="primary" loading={scanning.value} onClick={runScan}>
              <FolderSearch size={14} aria-hidden="true" /> {t('models.scan.run')}
            </Button>
          </div>
          <p class="md-scan__defaults">
            {t('models.scan.defaults')}{' '}
            <code>./models</code> · <code>./research/models</code> · <code>~/models</code> ·{' '}
            <code>WS_MODELS_DIR</code>{t('models.scan.defaultsJan')}
          </p>
          {scanError.value ? <p class="md-error">{scanError.value}</p> : null}
        </Card>

        {scanResults.value !== null ? (
          <Card class="md-results">
            <div class="md-results__bar">
              <div class="md-results__search">
                <Search size={14} aria-hidden="true" />
                <input
                  class="md-input"
                  type="search"
                  placeholder={t('models.scan.filter')}
                  value={filter.value}
                  onInput={(e) => (filter.value = (e.target as HTMLInputElement).value)}
                  aria-label={t('models.scan.filter')}
                />
              </div>
              <label class="md-results__sort">
                {t('models.scan.sort')}
                <select
                  class="md-input md-select"
                  value={sort.value}
                  onChange={(e) => (sort.value = (e.target as HTMLSelectElement).value as SortKey)}
                >
                  <option value="size">{t('models.scan.sortSize')}</option>
                  <option value="name">{t('models.scan.sortName')}</option>
                </select>
              </label>
              <span class="md-results__count tnum">{t('models.scan.found', { count: visible.length })}</span>
            </div>
            {visible.length === 0 ? (
              <EmptyState emoji="🔍" title={t('models.scan.noneTitle')} body={t('models.scan.noneBody')} />
            ) : (
              <div class="md-results__grid">
                {visible.map((m) => (
                  <div key={m.path} class="md-result">
                    <div class="md-result__name" title={m.path}>{m.name}</div>
                    <div class="md-result__badges">
                      <Badge tone="neutral">{m.architecture}</Badge>
                      {m.quant ? <Badge tone="brand">{m.quant}</Badge> : null}
                      <Badge tone="neutral">{fmtNumber(m.size_gb, { maximumFractionDigits: 2 })} GB</Badge>
                    </div>
                    {m.may_need_upgrade ? (
                      <p class="md-result__warn">
                        ⚠️ {t('models.scan.needUpgrade')} <code>pip install -U llama-cpp-python</code>
                      </p>
                    ) : null}
                    <Button variant="soft" size="sm" onClick={() => pickScanResult(m)}>
                      <HardDriveDownload size={13} aria-hidden="true" /> {t('models.scan.use')}
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </Card>
        ) : null}
      </section>

      {/* ── Load form ─────────────────────────────────────────── */}
      <section class="md-section">
        <h2 class="md-section__title">{t('models.load.title')}</h2>
        <Card class="md-load">
          <div class="md-load__pathrow">
            <input
              class="md-input"
              type="text"
              placeholder={t('models.load.pathPlaceholder')}
              value={loadPath.value}
              onInput={(e) => {
                loadPath.value = (e.target as HTMLInputElement).value
                if (!loadId.value.trim()) loadId.value = suggestModelId(loadPath.value)
              }}
              aria-label={t('models.load.pathLabel')}
            />
            <Button variant="ghost" onClick={onBrowseFile}>
              <FolderOpen size={14} aria-hidden="true" /> {t('models.scan.browse')}
            </Button>
          </div>
          {advisory ? (
            <p class={`md-advisory md-advisory--${advisory}`}>
              {advisory === 'full'
                ? t('models.load.advFull', { quant: loadQuant ?? '' })
                : t('models.load.advLow', { quant: loadQuant ?? '' })}
            </p>
          ) : null}
          {showQuantAdvisor ? (
            <div class="md-quant-advisor">
              <p class="md-quant-advisor__title">
                {t('models.load.quantTitle')} <span class="dialog-text--dim">{t('models.load.quantMeasured')}</span>
              </p>
              {overVram ? (
                <p class={`md-quant-advisor__row${bestFit ? '' : ' md-quant-advisor__row--warn'}`}>
                  ⚠️ {t('models.load.quantOverVram', {
                    quant: loadQuant ?? '?',
                    need: fmtNumber(Math.round((pickedVram ?? 0) / 1024)),
                    total: fmtNumber(Math.round((totalVram ?? 0) / 1024)),
                  })}
                </p>
              ) : null}
              {siblings.map((s) => {
                const q = guessQuant(s.path)
                const tokS = q ? MEASURED_TOK_S[q] : null
                const isBest = bestFit != null && s.path.replace(/\\/g, '/') === bestFit.path.replace(/\\/g, '/')
                const fits = totalVram != null ? estimateVramMiB(s.size_bytes, loadCtx.value) <= totalVram : null
                return (
                  <div key={s.path} class={`md-quant-advisor__row${isBest ? ' md-quant-advisor__row--best' : ''}`}>
                    <span class="md-quant-advisor__quant">{q ?? '?'}</span>
                    <span class="tnum">{fmtNumber(s.size_gb, { maximumFractionDigits: 2 })} GB</span>
                    {tokS != null ? <Badge tone="brand">~{fmtNumber(tokS)} tok/s</Badge> : null}
                    {q && QUANT_QUALITY_NOTES[q] ? <Badge tone="neutral">{QUANT_QUALITY_NOTES[q]}</Badge> : null}
                    {fits === false ? <Badge tone="warn">{t('models.load.quantNoFit')}</Badge> : null}
                    {fits === true ? <Badge tone="ok">{t('models.load.quantFits')}</Badge> : null}
                    {isBest ? <Badge tone="info">{t('models.load.quantBest')}</Badge> : null}
                    <Button variant="ghost" size="sm" onClick={() => switchToQuant(s.path)}>
                      {t('models.load.quantUse')}
                    </Button>
                  </div>
                )
              })}
            </div>
          ) : null}
          <div class="md-load__fields">
            <label>
              {t('models.load.modelId')}
              <input
                class="md-input"
                type="text"
                value={loadId.value}
                onInput={(e) => (loadId.value = (e.target as HTMLInputElement).value)}
              />
            </label>
            <label>
              {t('models.load.buf')}
              <input
                class="md-input tnum"
                type="number"
                min={1}
                step={16}
                value={loadBuf.value}
                onInput={(e) => (loadBuf.value = Number((e.target as HTMLInputElement).value) || 64)}
              />
            </label>
            <label>
              {t('models.load.ctx')}
              <input
                class="md-input tnum"
                type="number"
                min={8}
                step={512}
                value={loadCtx.value}
                onInput={(e) => (loadCtx.value = Number((e.target as HTMLInputElement).value) || 2048)}
              />
            </label>
            <label>
              {t('models.load.threads', { count: defaultThreads() })}
              <input
                class="md-input tnum"
                type="number"
                min={1}
                value={loadThreads.value}
                onInput={(e) => (loadThreads.value = Number((e.target as HTMLInputElement).value) || 1)}
              />
            </label>
            <label>
              {t('models.load.gpuLayers')}
              <input
                class="md-input tnum"
                type="number"
                min={-1}
                step={1}
                value={loadGpuLayers.value}
                onInput={(e) => {
                  // Explicit null check: 0 is a VALID value (CPU-only) and
                  // must survive the falsy-coalescing trap (`x || -1`).
                  const n = Number((e.target as HTMLInputElement).value)
                  loadGpuLayers.value = Number.isNaN(n) ? -1 : n
                }}
              />
            </label>
            <label>
              {t('models.load.kvCache')}
              <input
                class="md-input"
                type="text"
                placeholder={t('models.load.kvCachePlaceholder')}
                value={loadKvCache.value}
                onInput={(e) => (loadKvCache.value = (e.target as HTMLInputElement).value)}
              />
            </label>
          </div>
          <div class="md-load__submit">
            <Button
              variant="primary"
              disabled={!loadPath.value.trim() || !loadId.value.trim() || loadingModel.value}
              loading={loadingModel.value}
              onClick={doLoad}
            >
              <HardDriveDownload size={15} aria-hidden="true" /> {t('models.load.submit')}
            </Button>
          </div>
        </Card>
      </section>

      {/* ── Library (P5: models dirs + loaded/on-disk + Hub shortcut) ── */}
      <section class="md-section">
        <h2 class="md-section__title">
          {t('models.library.title')}
          <Tip label={t('models.library.tip')} />
        </h2>
        {libDirs.value.length === 0 ? (
          <Card>
            <EmptyState emoji="📁" title={t('common.notAvailable')} body={t('models.library.fetchFailed')} />
          </Card>
        ) : (
          <div class="md-lib">
            {libDirs.value.map((dir) => {
              const here = loadedIn(dir)
              return (
                <Card key={dir} class="md-lib__card">
                  <div class="md-lib__head">
                    <code class="md-lib__path" title={dir}>
                      {dir}
                    </code>
                    <Badge tone={here.length > 0 ? 'ok' : 'neutral'}>
                      {t('models.library.loadedCount', { count: here.length })}
                    </Badge>
                  </div>
                  {here.length > 0 ? (
                    <ul class="md-lib__loaded">
                      {here.map((m) => (
                        <li key={m.id} title={m.path}>
                          <span class="status-dot status-dot--online" aria-hidden="true" />
                          {m.id} <span class="dialog-text--dim">({t('models.library.onDisk')})</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p class="dialog-text--dim md-lib__none">{t('models.library.noneHere')}</p>
                  )}
                  <div class="md-card__actions">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        scanDir.value = dir
                        void runScan()
                      }}
                    >
                      <FolderSearch size={13} aria-hidden="true" /> {t('models.library.scanThis')}
                    </Button>
                    <Button variant="soft" size="sm" onClick={openHub}>
                      <Globe size={13} aria-hidden="true" /> {t('models.library.findHub')}
                    </Button>
                  </div>
                </Card>
              )
            })}
          </div>
        )}
        <p class="set-note">
          <Tip label={t('models.library.noDelete')} /> {t('models.library.noDelete')}
        </p>
      </section>

      {/* ── Unload confirm (with session-remember, spec §8.3) ─── */}
      <Dialog
        open={unloadTarget.value !== null}
        onClose={() => (unloadTarget.value = null)}
        title={t('overview.models.unloadTitle')}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => (unloadTarget.value = null)}>
              {t('common.cancel')}
            </Button>
            <Button variant="danger" onClick={() => unloadTarget.value && doUnload(unloadTarget.value)}>
              {t('models.loaded.unload')}
            </Button>
          </>
        }
      >
        <p class="dialog-text">{t('overview.models.unloadBody', { id: unloadTarget.value ?? '' })}</p>
        <label class="md-remember">
          <input
            type="checkbox"
            checked={rememberUnload.value}
            onChange={(e) => (rememberUnload.value = (e.target as HTMLInputElement).checked)}
          />
          {t('models.loaded.remember')}
        </label>
      </Dialog>

      {/* ── Reload(force) confirm ─────────────────────────────── */}
      <Dialog
        open={reloadTarget.value !== null}
        onClose={() => (loadingModel.value ? undefined : (reloadTarget.value = null))}
        title={t('models.loaded.reloadTitle')}
        size="sm"
        footer={
          <>
            <Button variant="ghost" disabled={loadingModel.value} onClick={() => (reloadTarget.value = null)}>
              {t('common.cancel')}
            </Button>
            <Button variant="primary" loading={loadingModel.value} onClick={() => reloadTarget.value && doReload(reloadTarget.value)}>
              {t('models.loaded.reloadBtn')}
            </Button>
          </>
        }
      >
        <p class="dialog-text">
          {t('models.loaded.reloadBody', { id: reloadTarget.value?.id ?? '' })}
        </p>
        <p class="dialog-text dialog-text--dim">{t('models.loaded.reloadNote')}</p>
      </Dialog>

      {/* ── Load progress (not cancellable — server has no cancel API) ── */}
      <Dialog open={loadingModel.value} onClose={() => undefined} title={t('models.load.progressTitle')} size="sm" hideClose>
        <div class="md-progress">
          <span class="btn__spinner" aria-hidden="true" />
          <div>
            <p class="dialog-text">{t('models.load.progressBody')}</p>
            <p class="dialog-text dialog-text--dim">{t('models.load.progressNote')}</p>
          </div>
        </div>
      </Dialog>
    </div>
  )
}

/** Reload uses the default context — the server does not expose the current
    n_ctx (honest note shown in the confirm dialog). */
function loadCtxDefault(_m: ModelStatus): number {
  return 2048
}

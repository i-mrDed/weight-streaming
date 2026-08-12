/* ⚙️ Settings (spec §9.8) — HONEST by design.
   - Appearance / Language / Chat defaults = runtime + persisted (localStorage).
   - Server (P5, wired to the P4 endpoints):
     · READ — every key from GET /v1/config with its real source badge
       (env / default / runtime), plus models_dirs, issues_dir, version.
     · RUNTIME EDIT — the safe subset {idle_unload_timeout, max_loaded_models}
       applies live via PATCH /v1/config; the gated subset {buffer/n_ctx/
       n_threads} applies to models loaded afterwards (the server says so in
       `notes`, and the UI warns before sending).
     · RESTART-ONLY KEYS — the server refuses them (HTTP 409) and answers
       with an env snippet; the UI renders that snippet for copy instead of
       a scary error toast (honest capability claim).
     · "Change for next start" snippet generator stays (real WS_* env names).
   - Diagnostics = debug context + log-tail viewer/downloader (GET /v1/logs/tail).
   - Data = clear chat history (confirm) + export/import prefs (client-only). */
import { useEffect } from 'preact/hooks'
import { useSignal } from '@preact/signals'
import { Copy, Download, DownloadCloud, FileJson, RefreshCw, Sparkles, Trash2, Upload } from 'lucide-preact'
import {
  autoMode,
  density,
  particlesEnabled,
  resolvedThemeId,
  setAutoMode,
  setDensity,
  setTheme,
  toggleParticles,
  type Density,
} from '@/theme/manager'
import { THEMES } from '@/theme/registry'
import { MCPSection } from './MCPSection'
import { AgentSection } from './AgentSection'
import { TieringSection } from './TieringSection'
import {
  availableLocales,
  fmtNumber,
  LOCALE_META,
  locale,
  setLocale,
  t,
} from '@/i18n'
import { displayName, health, serverHostPort, setDisplayName } from '@/core/store'
import {
  notificationsEnabled,
  readDefaults,
  writeDefaults,
  clearAllConversations,
  convIndex,
  setNotificationsEnabled,
  type ChatParams,
} from '@/pages/chat/store'
import { fetchDebugContext, downloadText, type DebugContext } from '@/core/issues'
import {
  fetchConfig,
  fetchLogsTail,
  patchConfig,
  type PatchRejected,
  type ServerConfigResponse,
} from '@/core/config'
import { ApiError, setApiToken } from '@/core/api'
import { navigate } from '@/core/router'
import { Badge } from '@/components/Badge'
import { Button } from '@/components/Button'
import { Card } from '@/components/Card'
import { Dialog } from '@/components/Dialog'
import { Segmented } from '@/components/Segmented'
import { Tip } from '@/components/Tip'
import { toast } from '@/components/Toast'

// Repo/license are static, verified at authoring time (git remote + the
// frontend package.json, which declares NO license) — not fabricated at
// runtime and not a server value. License honestly shows n/a until added.
const REPO_URL = 'https://github.com/i-mrDed/weight-streaming'
const LICENSE = 'n/a'

interface Prefs {
  theme: string
  auto: boolean
  particles: boolean
  density: Density
  locale: string
  displayName: string
  chat: { params: ChatParams; systemPrompt: string }
  notifications: boolean
}

function readPrefs(): Prefs {
  const d = readDefaults()
  return {
    theme: resolvedThemeId.value,
    auto: autoMode.value,
    particles: particlesEnabled.value,
    density: density.value,
    locale: locale.value,
    displayName: displayName.value,
    chat: { params: d.params, systemPrompt: d.systemPrompt },
    notifications: notificationsEnabled.value,
  }
}

// env vars the server actually reads (weight_stream/server/config.py)
const ENV_FIELDS: { key: keyof EnvDraft; env: string; label: string }[] = [
  { key: 'host', env: 'WS_HOST', label: 'settings.server.field.host' },
  { key: 'port', env: 'WS_PORT', label: 'settings.server.field.port' },
  { key: 'bufferMb', env: 'WS_BUFFER_MB', label: 'settings.server.field.bufferMb' },
  { key: 'nCtx', env: 'WS_N_CTX', label: 'settings.server.field.nCtx' },
  { key: 'nThreads', env: 'WS_N_THREADS', label: 'settings.server.field.nThreads' },
  { key: 'gpuLayers', env: 'WS_GPU_LAYERS', label: 'settings.server.field.gpuLayers' },
  { key: 'kvCacheType', env: 'WS_KV_CACHE_TYPE', label: 'settings.server.field.kvCacheType' },
  { key: 'idleTimeout', env: 'WS_IDLE_TIMEOUT', label: 'settings.server.field.idleTimeout' },
  { key: 'maxModels', env: 'WS_MAX_MODELS', label: 'settings.server.field.maxModels' },
  { key: 'logLevel', env: 'WS_LOG_LEVEL', label: 'settings.server.field.logLevel' },
]

interface EnvDraft {
  host: string
  port: string
  bufferMb: string
  nCtx: string
  nThreads: string
  gpuLayers: string
  kvCacheType: string
  idleTimeout: string
  maxModels: string
  logLevel: string
}

// GET /v1/config key → label key (unknown future keys fall back to the raw name)
const CONFIG_LABELS: Record<string, string> = {
  host: 'settings.server.field.host',
  port: 'settings.server.field.port',
  default_buffer_mb: 'settings.server.field.bufferMb',
  default_n_ctx: 'settings.server.field.nCtx',
  default_n_threads: 'settings.server.field.nThreads',
  default_gpu_layers: 'settings.server.field.gpuLayers',
  default_kv_cache_type: 'settings.server.field.kvCacheType',
  idle_unload_timeout: 'settings.server.field.idleTimeout',
  max_loaded_models: 'settings.server.field.maxModels',
  lower_process_priority: 'settings.server.field.lowerPriority',
  max_concurrent_requests: 'settings.server.field.maxRequests',
  request_queue_depth: 'settings.server.field.queueDepth',
  log_level: 'settings.server.field.logLevel',
}

// Keys the server answers with 409 + snippet (api_server._CONFIG_REJECT_REASONS).
// Listed only to offer them in the form — the 409 body carries the real reasons.
const RESTART_KEYS = [
  'host',
  'port',
  'log_level',
  'lower_process_priority',
  'max_concurrent_requests',
  'request_queue_depth',
] as const

// "Model folders" show the first N, then a "Show {N} folders" toggle (P5.3c) —
// Windows paths are long, so we do not cram every one into the card.
const DIRS_COLLAPSED = 3

// Tone + tooltip for a config key's true source dot (legend lives in the head
// of Effective configuration; the dot keeps per-row honesty without a per-row
// badge). Sourced from the real GET /v1/config `source` field.
function srcDotTone(source: string): { tone: 'ok' | 'info' | 'neutral'; tip: string } {
  if (source === 'runtime') {
    return { tone: 'ok', tip: 'settings.server.srcRuntimeTip' }
  }
  if (source === 'env') {
    return { tone: 'info', tip: 'settings.server.srcEnvTip' }
  }
  return { tone: 'neutral', tip: 'settings.server.srcDefaultTip' }
}

function fmtCfgValue(v: unknown): string {
  if (typeof v === 'boolean') return v ? 'true' : 'false'
  if (v == null) return '–'
  return String(v)
}

export function SettingsPage() {
  locale.value
  const dbg = useSignal<DebugContext | null>(null)
  const dbgLoading = useSignal(false)

  // chat defaults draft
  const defs = readDefaults()
  const temperature = useSignal(defs.params.temperature)
  const topP = useSignal(defs.params.top_p)
  const maxTokens = useSignal(defs.params.max_tokens)
  const systemPrompt = useSignal(defs.systemPrompt)

  // display name draft
  const nameDraft = useSignal(displayName.value)

  // snippet generator
  const env = useSignal<EnvDraft>({
    host: '127.0.0.1',
    port: '8765',
    bufferMb: '64',
    nCtx: '2048',
    nThreads: '',
    gpuLayers: '-1',
    kvCacheType: '',
    idleTimeout: '0',
    maxModels: '4',
    logLevel: 'info',
  })
  const shell = useSignal<'bash' | 'powershell'>('bash')

  // data
  const clearOpen = useSignal(false)
  const storageBytes = useSignal<number | null>(null)

  // diagnostics
  const showCtx = useSignal(false)

  // server config (P4 GET/PATCH /v1/config — wired in P5)
  const serverCfg = useSignal<ServerConfigResponse | null>(null)
  const cfgLoading = useSignal(false)
  const dirsOpen = useSignal(false) // models_dirs collapse/expand (P5.3c)
  const rtIdle = useSignal('0') // idle_unload_timeout draft
  const rtMax = useSignal('4') // max_loaded_models draft
  const rtBuf = useSignal('64') // default_buffer_mb draft (gated)
  const rtCtx = useSignal('2048') // default_n_ctx draft (gated)
  const rtThreads = useSignal('') // default_n_threads draft (gated; '' = keep)
  const rtGpuLayers = useSignal('-1') // default_gpu_layers draft (gated; -1 = auto)
  const rtKvCache = useSignal('') // default_kv_cache_type draft (gated; '' = server default)
  const applying = useSignal(false)
  const restartKey = useSignal<string>('host')
  const restartVal = useSignal('')
  const restartResult = useSignal<PatchRejected | null>(null)
  const restartBusy = useSignal(false)

  // API access token (B1): mirrors server WS_API_TOKEN so the console's
  // requests carry Authorization when the server enforces auth.
  let storedToken = ''
  try {
    storedToken = localStorage.getItem('ws-api-token') ?? ''
  } catch {
    /* storage unavailable */
  }
  const apiToken = useSignal(storedToken)
  const saveApiToken = () => {
    setApiToken(apiToken.value)
    toast('success', t('settings.server.tokenSaved'))
  }

  // log tail (P4 GET /v1/logs/tail — wired in P5)
  const logLinesCount = useSignal(100)
  const logLines = useSignal<string[] | null>(null)
  const logLoading = useSignal(false)

  const loadConfig = async () => {
    cfgLoading.value = true
    try {
      const c = await fetchConfig()
      serverCfg.value = c
      // seed the runtime drafts from the real live values
      rtIdle.value = fmtCfgValue(c.config.idle_unload_timeout?.value)
      rtMax.value = fmtCfgValue(c.config.max_loaded_models?.value)
      rtBuf.value = fmtCfgValue(c.config.default_buffer_mb?.value)
      rtCtx.value = fmtCfgValue(c.config.default_n_ctx?.value)
      rtThreads.value = fmtCfgValue(c.config.default_n_threads?.value)
      rtGpuLayers.value = fmtCfgValue(c.config.default_gpu_layers?.value)
      rtKvCache.value = fmtCfgValue(c.config.default_kv_cache_type?.value)
    } catch {
      serverCfg.value = null // health dot tells the real story
    } finally {
      cfgLoading.value = false
    }
  }

  const applyRuntime = async () => {
    applying.value = true
    restartResult.value = null
    const body: Record<string, unknown> = {
      idle_unload_timeout: Number(rtIdle.value),
      max_loaded_models: Number(rtMax.value),
      default_buffer_mb: Number(rtBuf.value),
      default_n_ctx: Number(rtCtx.value),
      // Empty field = server default (-1 auto) — never Number('') which is 0
      // (CPU-only) and would silently lock every later load to the CPU.
      default_gpu_layers: rtGpuLayers.value.trim() === '' ? -1 : Number(rtGpuLayers.value),
    }
    if (rtThreads.value.trim() !== '') body.default_n_threads = Number(rtThreads.value)
    if (rtKvCache.value.trim() !== '') body.default_kv_cache_type = rtKvCache.value.trim()
    try {
      const res = await patchConfig(body)
      if (res.status === 'applied') {
        const gated = Object.keys(res.notes).length > 0
        toast(gated ? 'warning' : 'success', gated ? t('settings.server.appliedGated') : t('settings.server.applied'))
        await loadConfig() // source badges flip to "runtime" — the truth, from the server
      } else {
        // only restart-only keys get 409 — this form never sends them, so a
        // rejection here is shown verbatim rather than hidden (honest)
        restartResult.value = res
        toast('error', t('settings.server.applyFailed'), { body: res.detail })
      }
    } catch (e) {
      toast('error', t('settings.server.applyFailed'), {
        body: e instanceof ApiError && e.detail ? e.detail : String(e),
      })
    } finally {
      applying.value = false
    }
  }

  const requestRestartSnippet = async () => {
    restartBusy.value = true
    restartResult.value = null
    try {
      const res = await patchConfig({ [restartKey.value]: restartVal.value })
      if (res.status === 'rejected') {
        restartResult.value = res // the HONEST answer: reasons + env snippet
      } else {
        // The server unexpectedly applied a "restart-only" key — say so plainly.
        toast('success', t('settings.server.applied'))
        await loadConfig()
      }
    } catch (e) {
      toast('error', t('settings.server.applyFailed'), {
        body: e instanceof ApiError && e.detail ? e.detail : String(e),
      })
    } finally {
      restartBusy.value = false
    }
  }

  const copyRestartSnippet = async () => {
    if (!restartResult.value) return
    try {
      await navigator.clipboard?.writeText(restartResult.value.snippet)
      toast('success', t('settings.toast.snippetCopied'))
    } catch {
      toast('error', t('chat.copyFailed'))
    }
  }

  const loadLogs = async () => {
    logLoading.value = true
    try {
      const res = await fetchLogsTail(logLinesCount.value)
      logLines.value = res.lines
    } catch {
      logLines.value = []
    } finally {
      logLoading.value = false
    }
  }

  const downloadLogs = () => {
    const lines = logLines.value ?? []
    downloadText('server-tail.log', lines.join('\n') + '\n', 'text/plain')
  }

  useEffect(() => {
    // accurate version + redacted snapshot for About/Diagnostics/Server
    dbgLoading.value = true
    void fetchDebugContext().then((c) => {
      dbg.value = c
      dbgLoading.value = false
    })
    void loadConfig()
    // honest local-storage usage (chat + prefs we own)
    try {
      let bytes = 0
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i)
        if (k && k.startsWith('ws-')) bytes += k.length + (localStorage.getItem(k)?.length ?? 0)
      }
      storageBytes.value = bytes * 2 // JS strings are UTF-16
    } catch {
      storageBytes.value = null
    }
  }, [])

  const saveChatDefaults = () => {
    writeDefaults({
      params: { temperature: temperature.value, top_p: topP.value, max_tokens: maxTokens.value },
      systemPrompt: systemPrompt.value,
      perConv: true,
    })
    toast('success', t('common.save'))
  }

  const testNotif = () => {
    if (typeof Notification === 'undefined' || Notification.permission !== 'granted') {
      toast('warning', t('settings.chatDefaults.testNotifBlocked'))
      return
    }
    new Notification(t('settings.chatDefaults.testNotif'), { body: t('settings.chatDefaults.testNotifBody') })
  }

  const snippet = (): string => {
    const e = env.value
    const pairs = ENV_FIELDS.map((f) => ({ env: f.env, val: (e[f.key] as string).trim() })).filter((p) => p.val !== '')
    if (shell.value === 'powershell') {
      const setLines = pairs.map((p) => `$env:${p.env} = "${p.val}"`).join('; ')
      return `${setLines}; python -m weight_stream.server`
    }
    const pre = pairs.map((p) => `${p.env}=${p.val}`).join(' ')
    return `${pre} python -m weight_stream.server`
  }

  const copySnippet = async () => {
    try {
      await navigator.clipboard?.writeText(snippet())
      toast('success', t('settings.toast.snippetCopied'))
    } catch {
      toast('error', t('chat.copyFailed'))
    }
  }

  const exportSettings = () => {
    const prefs = readPrefs()
    downloadText('weight-streaming-settings.json', JSON.stringify(prefs, null, 2), 'application/json')
    toast('success', t('settings.toast.exported'))
  }

  const importSettings = () => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'application/json,.json'
    input.onchange = () => {
      const file = input.files?.[0]
      if (!file) return
      const reader = new FileReader()
      reader.onload = () => {
        try {
          const p = JSON.parse(String(reader.result)) as Partial<Prefs>
          if (p.theme) setTheme(p.theme)
          if (typeof p.auto === 'boolean') setAutoMode(p.auto)
          if (typeof p.particles === 'boolean' && p.particles !== particlesEnabled.value) toggleParticles()
          if (p.density) setDensity(p.density)
          if (p.locale) setLocale(p.locale)
          if (typeof p.displayName === 'string') {
            setDisplayName(p.displayName)
            nameDraft.value = p.displayName
          }
          if (typeof p.notifications === 'boolean') {
            setNotificationsEnabled(p.notifications)
          }
          if (p.chat?.params) {
            temperature.value = p.chat.params.temperature ?? temperature.value
            topP.value = p.chat.params.top_p ?? topP.value
            maxTokens.value = p.chat.params.max_tokens ?? maxTokens.value
            systemPrompt.value = p.chat?.systemPrompt ?? systemPrompt.value
            saveChatDefaults()
          }
          toast('success', t('settings.toast.imported'))
        } catch {
          toast('error', t('settings.toast.importFailed'))
        }
      }
      reader.readAsText(file)
    }
    input.click()
  }

  const copyContext = async () => {
    if (!dbg.value) return
    try {
      await navigator.clipboard?.writeText(JSON.stringify(dbg.value, null, 2))
      toast('success', t('settings.toast.contextCopied'))
    } catch {
      toast('error', t('chat.copyFailed'))
    }
  }

  const accurateVersion = dbg.value?.app_version || t('common.notAvailable')

  return (
    <div class="page">
      <header class="page__header">
        <h1 class="page__title">
          <span aria-hidden="true">⚙️</span> {t('nav.settings')}
        </h1>
      </header>

      {/* Appearance */}
      <section id="settings-appearance" class="md-section">
        <h2 class="md-section__title">{t('settings.appearance.title')}</h2>
        <Card class="set-card">
          <div class="set-themes">
            {THEMES.map((th) => (
              <button
                key={th.id}
                type="button"
                class={`set-theme${!autoMode.value && resolvedThemeId.value === th.id ? ' is-on' : ''}`}
                onClick={() => setTheme(th.id)}
                aria-pressed={!autoMode.value && resolvedThemeId.value === th.id}
              >
                <span
                  class="set-theme__swatch"
                  style={{ background: th.preview.canvas, color: th.preview.text }}
                  aria-hidden="true"
                >
                  <span class="set-theme__accent" style={{ background: th.preview.accent }} />
                </span>
                <span class="set-theme__name">{t(th.nameKey)}</span>
              </button>
            ))}
          </div>
          <label class="set-row">
            <span>
              {t('settings.appearance.auto')} <Tip label={t('settings.appearance.autoHint')} />
            </span>
            <input
              type="checkbox"
              checked={autoMode.value}
              onChange={(e) => setAutoMode((e.target as HTMLInputElement).checked)}
            />
          </label>
          <label class="set-row">
            <span>
              {t('settings.appearance.particles')} <Tip label={t('settings.appearance.particlesHint')} />
            </span>
            <input type="checkbox" checked={particlesEnabled.value} onChange={() => toggleParticles()} />
          </label>
          <div class="set-row">
            <span>
              {t('settings.appearance.density')} <Tip label={t('settings.appearance.densityHint')} />
            </span>
            <Segmented
              ariaLabel={t('settings.appearance.density')}
              size="sm"
              value={density.value}
              onChange={(v) => {
                setDensity(v as Density)
                toast('info', t('settings.toast.densityChanged', { name: t(`settings.appearance.${v}`) }))
              }}
              options={[
                { value: 'comfortable', label: t('settings.appearance.comfortable') },
                { value: 'compact', label: t('settings.appearance.compact') },
              ]}
            />
          </div>
        </Card>
      </section>

      {/* Language */}
      <section id="settings-language" class="md-section">
        <h2 class="md-section__title">{t('settings.language.title')}</h2>
        <Card class="set-card">
          <div class="set-row">
            <span>{t('settings.language.title')}</span>
            <select
              class="md-input md-select set-select"
              value={locale.value}
              onChange={(e) => {
                const code = (e.target as HTMLSelectElement).value
                setLocale(code)
                toast('info', t('common.toast.languageChanged', { name: LOCALE_META[code]?.nativeName ?? code }))
              }}
            >
              {availableLocales.map((code) => (
                <option key={code} value={code}>
                  {LOCALE_META[code]?.nativeName ?? code}
                </option>
              ))}
            </select>
          </div>
          <label class="set-field">
            <span>
              {t('settings.language.displayName')} <Tip label={t('settings.language.displayNameHint')} />
            </span>
            <input
              class="md-input"
              type="text"
              value={nameDraft.value}
              onInput={(e) => (nameDraft.value = (e.target as HTMLInputElement).value)}
              onBlur={() => setDisplayName(nameDraft.value)}
            />
          </label>
        </Card>
      </section>

      {/* Chat defaults */}
      <section id="settings-chatDefaults" class="md-section">
        <h2 class="md-section__title">{t('settings.chatDefaults.title')}</h2>
        <Card class="set-card">
          <p class="dialog-text--dim">{t('settings.chatDefaults.hint')}</p>
          <div class="set-nums">
            <label class="set-field">
              <span>{t('settings.chatDefaults.temperature')}</span>
              <input
                class="md-input tnum"
                type="number"
                min={0}
                max={2}
                step={0.1}
                value={temperature.value}
                onInput={(e) => (temperature.value = Number((e.target as HTMLInputElement).value) || 0)}
              />
            </label>
            <label class="set-field">
              <span>{t('settings.chatDefaults.topP')}</span>
              <input
                class="md-input tnum"
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={topP.value}
                onInput={(e) => (topP.value = Number((e.target as HTMLInputElement).value) || 0)}
              />
            </label>
            <label class="set-field">
              <span>{t('settings.chatDefaults.maxTokens')}</span>
              <input
                class="md-input tnum"
                type="number"
                min={1}
                step={64}
                value={maxTokens.value}
                onInput={(e) => (maxTokens.value = Math.max(1, Number((e.target as HTMLInputElement).value) || 1))}
              />
            </label>
          </div>
          <label class="set-field">
            <span>{t('settings.chatDefaults.systemPreset')}</span>
            <textarea
              class="md-input iss-textarea"
              rows={2}
              placeholder={t('settings.chatDefaults.systemPresetPlaceholder')}
              value={systemPrompt.value}
              onInput={(e) => (systemPrompt.value = (e.target as HTMLInputElement).value)}
            />
          </label>
          <div class="set-row">
            <span>
              {t('settings.chatDefaults.notifications')} <Tip label={t('settings.chatDefaults.notificationsHint')} />
            </span>
            <input
              type="checkbox"
              checked={notificationsEnabled.value}
              onChange={(e) => {
                setNotificationsEnabled((e.target as HTMLInputElement).checked)
              }}
            />
          </div>
          <div class="set-actions">
            <Button variant="primary" size="sm" onClick={saveChatDefaults}>
              {t('common.save')}
            </Button>
            <Button variant="ghost" size="sm" onClick={testNotif}>
              {t('settings.chatDefaults.testNotif')}
            </Button>
          </div>
        </Card>
      </section>

      {/* Server — three sub-cards, ONE clear intent each (P5.3c).
           A · Status & Config  (read)      — live values + effective config + dirs
           B · Live runtime edits (write)   — safe + gated form, applies live
           C · For next start (restart)     — restart-only key→snippet + generator */}
      <section id="settings-server" class="md-section">
        <h2 class="md-section__title">{t('settings.server.title')}</h2>

        {/* Card A · Status & Config (read-only) */}
        <Card class="set-card">
          <h3 class="set-card__title">{t('settings.server.cardStatus')}</h3>
          <p class="dialog-text--dim">{t('settings.server.readHint')}</p>
          <dl class="set-dl">
            <div>
              <dt>{t('settings.server.status')}</dt>
              <dd>
                <Badge tone={health.value === 'online' ? 'ok' : health.value === 'offline' ? 'error' : 'neutral'}>
                  {t(`common.health.${health.value}`)}
                </Badge>
              </dd>
            </div>
            <div>
              <dt>{t('settings.server.hostPort')}</dt>
              <dd class="tnum">{serverHostPort.value || t('common.notAvailable')}</dd>
            </div>
            <div>
              <dt>
                {t('settings.server.version')} <Tip label={t('settings.server.versionSource')} />
              </dt>
              <dd class="tnum">{dbgLoading.value ? t('common.loading') : accurateVersion}</dd>
            </div>
          </dl>
          {/* single note — rendered once (P5.3c removed the duplicated Tip+text) */}
          <p class="set-note">{t('settings.server.healthVersionNote')}</p>

          {/* per-key live values with their TRUE source (GET /v1/config).
              One legend explains the sources; each row keeps a subtle per-key
              dot (with tooltip) instead of a bulky per-row badge. */}
          <div class="set-cfghead">
            <h4 class="set-subtitle">{t('settings.server.configKeys')}</h4>
            <Button variant="ghost" size="sm" loading={cfgLoading.value} onClick={() => void loadConfig()}>
              <RefreshCw size={13} aria-hidden="true" /> {t('common.retry')}
            </Button>
          </div>
          {serverCfg.value ? (
            <>
              <p class="set-cfglegend">{t('settings.server.srcLegend')}</p>
              <dl class="set-dl set-dl--cfg">
                {Object.entries(serverCfg.value.config).map(([key, entry]) => {
                  const dot = srcDotTone(entry.source)
                  const label = CONFIG_LABELS[key] ? t(CONFIG_LABELS[key]) : key
                  return (
                    <div key={key}>
                      <dt>
                        <span
                          class={`set-src-dot is-${dot.tone}`}
                          role="img"
                          title={t(dot.tip)}
                          aria-label={`${label} · ${t(dot.tip)}`}
                          data-source={entry.source}
                        />
                        {label}
                      </dt>
                      <dd class="tnum">{fmtCfgValue(entry.value)}</dd>
                    </div>
                  )
                })}
              </dl>
              <div class="set-dirs">
                <span class="set-dirs__label">
                  {t('settings.server.modelsDirs')} <Tip label={t('settings.server.modelsDirsHint')} />
                </span>
                <ul>
                  {(dirsOpen.value ? serverCfg.value.models_dirs : serverCfg.value.models_dirs.slice(0, DIRS_COLLAPSED)).map((d) => (
                    <li key={d}>
                      <code>{d}</code>
                    </li>
                  ))}
                </ul>
                {serverCfg.value.models_dirs.length > DIRS_COLLAPSED ? (
                  <button type="button" class="set-dirs__toggle" onClick={() => (dirsOpen.value = !dirsOpen.value)}>
                    {dirsOpen.value
                      ? t('settings.server.modelsDirsHide')
                      : t('settings.server.modelsDirsShow', { count: serverCfg.value.models_dirs.length })}
                  </button>
                ) : null}
              </div>
              <div class="set-dirs">
                <span class="set-dirs__label">{t('settings.server.issuesDir')}</span>
                <ul>
                  <li>
                    <code>{serverCfg.value.issues_dir}</code>
                  </li>
                </ul>
              </div>
              <div class="set-dirs">
                <span class="set-dirs__label">{t('settings.server.configVersion')}</span>
                <ul>
                  <li>
                    <code class="tnum">{serverCfg.value.version}</code>
                  </li>
                </ul>
              </div>
            </>
          ) : (
            <p class="set-note">{cfgLoading.value ? t('common.loading') : t('common.notAvailable')}</p>
          )}
        </Card>

        {/* Card B · Live runtime edits (write) */}
        <Card class="set-card">
          <h3 class="set-card__title">{t('settings.server.runtimeTitle')}</h3>
          <p class="dialog-text--dim">{t('settings.server.runtimeHint')}</p>
          <p class="set-note set-note--warn">⚠️ {t('settings.server.gatedWarn')}</p>
          <div class="set-env">
            <label class="set-field">
              <span>
                {t('settings.server.field.idleTimeout')} <Badge tone="ok" class="set-src">{t('settings.server.runtimeSafe')}</Badge>
              </span>
              <input
                class="md-input tnum"
                type="number"
                min={0}
                step={10}
                value={rtIdle.value}
                onInput={(e) => (rtIdle.value = (e.target as HTMLInputElement).value)}
              />
            </label>
            <label class="set-field">
              <span>
                {t('settings.server.field.maxModels')} <Badge tone="ok" class="set-src">{t('settings.server.runtimeSafe')}</Badge>
              </span>
              <input
                class="md-input tnum"
                type="number"
                min={1}
                step={1}
                value={rtMax.value}
                onInput={(e) => (rtMax.value = (e.target as HTMLInputElement).value)}
              />
            </label>
            <label class="set-field">
              <span>
                {t('settings.server.field.bufferMb')} <Badge tone="warn" class="set-src">{t('settings.server.runtimeGated')}</Badge>
              </span>
              <input
                class="md-input tnum"
                type="number"
                min={1}
                step={16}
                value={rtBuf.value}
                onInput={(e) => (rtBuf.value = (e.target as HTMLInputElement).value)}
              />
            </label>
            <label class="set-field">
              <span>
                {t('settings.server.field.nCtx')} <Badge tone="warn" class="set-src">{t('settings.server.runtimeGated')}</Badge>
              </span>
              <input
                class="md-input tnum"
                type="number"
                min={8}
                step={512}
                value={rtCtx.value}
                onInput={(e) => (rtCtx.value = (e.target as HTMLInputElement).value)}
              />
            </label>
            <label class="set-field">
              <span>
                {t('settings.server.field.nThreads')} <Badge tone="warn" class="set-src">{t('settings.server.runtimeGated')}</Badge>
              </span>
              <input
                class="md-input tnum"
                type="number"
                min={1}
                value={rtThreads.value}
                onInput={(e) => (rtThreads.value = (e.target as HTMLInputElement).value)}
              />
            </label>
            <label class="set-field">
              <span>
                {t('settings.server.field.gpuLayers')} <Badge tone="warn" class="set-src">{t('settings.server.runtimeGated')}</Badge>
              </span>
              <input
                class="md-input tnum"
                type="number"
                min={-1}
                value={rtGpuLayers.value}
                onInput={(e) => (rtGpuLayers.value = (e.target as HTMLInputElement).value)}
              />
            </label>
            <label class="set-field">
              <span>
                {t('settings.server.field.kvCacheType')} <Badge tone="warn" class="set-src">{t('settings.server.runtimeGated')}</Badge>
              </span>
              <input
                class="md-input"
                type="text"
                placeholder="f16 · q8_0 · q4_0"
                value={rtKvCache.value}
                onInput={(e) => (rtKvCache.value = (e.target as HTMLInputElement).value)}
              />
            </label>
          </div>
          <div class="set-actions">
            <Button variant="primary" size="sm" loading={applying.value} onClick={() => void applyRuntime()}>
              {t('settings.server.apply')}
            </Button>
          </div>
        </Card>

        {/* Card C · For next start (restart-only) */}
        <Card class="set-card">
          <h3 class="set-card__title">{t('settings.server.cardRestart')}</h3>
          <p class="dialog-text--dim">{t('settings.server.restartHint')}</p>
          <div class="set-restart">
            <label class="set-field">
              <span>{t('settings.server.restartKey')}</span>
              <select
                class="md-input md-select"
                value={restartKey.value}
                onChange={(e) => (restartKey.value = (e.target as HTMLSelectElement).value)}
              >
                {RESTART_KEYS.map((k) => (
                  <option key={k} value={k}>
                    {CONFIG_LABELS[k] ? t(CONFIG_LABELS[k]) : k}
                  </option>
                ))}
              </select>
            </label>
            <label class="set-field set-restart__val">
              <span>{t('settings.server.restartValue')}</span>
              <input
                class="md-input"
                type="text"
                value={restartVal.value}
                onInput={(e) => (restartVal.value = (e.target as HTMLInputElement).value)}
              />
            </label>
            <Button
              variant="soft"
              size="sm"
              loading={restartBusy.value}
              disabled={restartVal.value.trim() === ''}
              onClick={() => void requestRestartSnippet()}
            >
              {t('settings.server.requestSnippet')}
            </Button>
          </div>
          {restartResult.value ? (
            <div class="set-snippetblock">
              <p class="set-snippetblock__title">{t('settings.server.snippetTitle')}</p>
              {Object.keys(restartResult.value.rejected).length > 0 ? (
                <ul class="set-snippetblock__reasons">
                  {Object.entries(restartResult.value.rejected).map(([k, reason]) => (
                    <li key={k}>
                      <code>{k}</code> — {reason}
                    </li>
                  ))}
                </ul>
              ) : null}
              <pre class="set-snippet">{restartResult.value.snippet || restartResult.value.detail}</pre>
              <div class="set-actions">
                <Button variant="ghost" size="sm" onClick={() => void copyRestartSnippet()}>
                  <Copy size={13} aria-hidden="true" /> {t('settings.server.copySnippet')}
                </Button>
              </div>
            </div>
          ) : null}

          <h4 class="set-subtitle set-card__subtitle">{t('settings.server.applyTitle')}</h4>
          <p class="dialog-text--dim">{t('settings.server.applyHint')}</p>
          <div class="set-env">
            {ENV_FIELDS.map((f) => (
              <label key={f.env} class="set-field">
                <span>
                  {t(f.label)} <code>{f.env}</code>
                </span>
                <input
                  class="md-input tnum"
                  type="text"
                  value={env.value[f.key]}
                  onInput={(e) => (env.value = { ...env.value, [f.key]: (e.target as HTMLInputElement).value })}
                />
              </label>
            ))}
          </div>
          <div class="set-row">
            <Segmented
              ariaLabel="shell"
              size="sm"
              value={shell.value}
              onChange={(v) => (shell.value = v as 'bash' | 'powershell')}
              options={[
                { value: 'bash', label: 'bash / zsh' },
                { value: 'powershell', label: 'PowerShell' },
              ]}
            />
            <Button variant="soft" size="sm" onClick={() => void copySnippet()}>
              <Copy size={13} aria-hidden="true" /> {t('settings.server.copySnippet')}
            </Button>
          </div>
          <pre class="set-snippet">{snippet()}</pre>
          <p class="set-note set-note--warn">⚠️ {t('settings.server.restartNote')}</p>
        </Card>

        {/* Card D · API access token (B1) — WS_API_TOKEN */}
        <Card class="set-card">
          <h3 class="set-card__title">{t('settings.server.tokenTitle')}</h3>
          <p class="dialog-text--dim">{t('settings.server.tokenHint')}</p>
          <div class="set-restart">
            <label class="set-field set-restart__val">
              <input
                class="md-input"
                type="password"
                autocomplete="off"
                placeholder={t('settings.server.tokenPlaceholder')}
                value={apiToken.value}
                onInput={(e) => (apiToken.value = (e.target as HTMLInputElement).value)}
              />
            </label>
            <Button variant="primary" size="sm" onClick={saveApiToken}>
              {t('common.save')}
            </Button>
          </div>
        </Card>
      </section>

      {/* Auto-tiering (P8) */}
      <section id="settings-tiering" class="md-section">
        <h2 class="md-section__title">{t('settings.tiering.title')}</h2>
        <TieringSection />
      </section>

      {/* Agent & Workspace (AGENT_TOOLS_PLAN.md) */}
      <section id="settings-agent" class="md-section">
        <h2 class="md-section__title">{t('settings.agent.title')}</h2>
        <AgentSection />
      </section>

      {/* MCP (P7.4) */}
      <section id="settings-mcp" class="md-section">
        <h2 class="md-section__title">{t('settings.mcp.title')}</h2>
        <MCPSection />
      </section>

      {/* Data */}
      <section id="settings-data" class="md-section">
        <h2 class="md-section__title">{t('settings.data.title')}</h2>
        <Card class="set-card">
          <div class="set-row">
            <span>
              {t('settings.data.storage')}:{' '}
              <span class="tnum">
                {storageBytes.value != null ? `${fmtNumber(Math.round(storageBytes.value / 1024))} KB` : t('common.notAvailable')}
              </span>{' '}
              · {t('settings.data.conversations')}: <span class="tnum">{convIndex.value.length}</span>
            </span>
          </div>
          <div class="set-actions">
            <Button variant="ghost" size="sm" onClick={exportSettings}>
              <Download size={13} aria-hidden="true" /> {t('settings.data.export')}
            </Button>
            <Button variant="ghost" size="sm" onClick={importSettings}>
              <Upload size={13} aria-hidden="true" /> {t('settings.data.import')}
            </Button>
            <Button variant="danger" size="sm" onClick={() => (clearOpen.value = true)}>
              <Trash2 size={13} aria-hidden="true" /> {t('settings.data.clearHistory')}
            </Button>
          </div>
          <p class="dialog-text--dim">{t('settings.data.clearHistoryHint')}</p>
        </Card>
      </section>

      {/* Diagnostics */}
      <section id="settings-diagnostics" class="md-section">
        <h2 class="md-section__title">{t('settings.diagnostics.title')}</h2>
        <Card class="set-card">
          <div class="set-actions">
            <Button variant="soft" size="sm" onClick={() => (showCtx.value = !showCtx.value)}>
              <FileJson size={13} aria-hidden="true" /> {t('settings.diagnostics.debugContext')}
            </Button>
            <Button variant="ghost" size="sm" disabled={!dbg.value} onClick={() => void copyContext()}>
              <Copy size={13} aria-hidden="true" /> {t('settings.diagnostics.copyContext')}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => navigate('issues')}>
              <Sparkles size={13} aria-hidden="true" /> {t('settings.diagnostics.reportPrefill')}
            </Button>
          </div>
          <p class="dialog-text--dim">{t('settings.diagnostics.debugContextHint')}</p>
          {showCtx.value ? (
            <pre class="set-snippet">{dbg.value ? JSON.stringify(dbg.value, null, 2) : t('common.loading')}</pre>
          ) : null}

          {/* log tail (GET /v1/logs/tail — real lines from the server's ring
              buffer; empty until the server actually starts logging) */}
          <h3 class="set-subtitle">{t('settings.diagnostics.logTitle')}</h3>
          <div class="set-logbar">
            <select
              class="md-input md-select set-logbar__lines"
              value={String(logLinesCount.value)}
              aria-label={t('settings.diagnostics.logLines', { count: logLinesCount.value })}
              onChange={(e) => (logLinesCount.value = Number((e.target as HTMLSelectElement).value))}
            >
              {[50, 100, 500, 1000].map((n) => (
                <option key={n} value={String(n)}>
                  {t('settings.diagnostics.logLines', { count: n })}
                </option>
              ))}
            </select>
            <Button variant="soft" size="sm" loading={logLoading.value} onClick={() => void loadLogs()}>
              <RefreshCw size={13} aria-hidden="true" /> {t('common.retry')}
            </Button>
            <Button variant="ghost" size="sm" disabled={logLines.value == null} onClick={downloadLogs}>
              <Download size={13} aria-hidden="true" /> {t('settings.diagnostics.logDownload')}
            </Button>
          </div>
          {logLines.value != null ? (
            logLines.value.length === 0 ? (
              <p class="set-note">{t('settings.diagnostics.logEmpty')}</p>
            ) : (
              <pre class="set-snippet set-log">
                {logLines.value.join('\n')}
              </pre>
            )
          ) : null}
          <p class="set-note">
            <Tip label={t('settings.diagnostics.logHint')} /> {t('settings.diagnostics.logHint')}
          </p>
        </Card>
      </section>

      {/* About */}
      <section id="settings-about" class="md-section">
        <h2 class="md-section__title">{t('settings.about.title')}</h2>
        <Card class="set-card set-about">
          <p class="set-about__tag">{t('settings.about.tagline')}</p>
          <dl class="set-dl">
            <div>
              <dt>{t('settings.about.version')}</dt>
              <dd class="tnum">{dbgLoading.value ? t('common.loading') : accurateVersion}</dd>
            </div>
            <div>
              <dt>{t('settings.about.license')}</dt>
              <dd>{LICENSE}</dd>
            </div>
          </dl>
          <div class="set-actions">
            <Button variant="ghost" size="sm" onClick={() => navigate('docs')}>
              <DownloadCloud size={13} aria-hidden="true" /> {t('settings.about.docs')}
            </Button>
            <a class="btn btn--ghost btn--sm" href={REPO_URL} target="_blank" rel="noopener noreferrer">
              {t('settings.about.github')}
            </a>
          </div>
        </Card>
      </section>

      <Dialog
        open={clearOpen.value}
        onClose={() => (clearOpen.value = false)}
        title={t('settings.data.clearConfirmTitle')}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => (clearOpen.value = false)}>
              {t('common.cancel')}
            </Button>
            <Button
              variant="danger"
              onClick={() => {
                clearAllConversations()
                clearOpen.value = false
                toast('success', t('settings.toast.cleared'))
              }}
            >
              <Trash2 size={13} aria-hidden="true" /> {t('settings.data.clearConfirm')}
            </Button>
          </>
        }
      >
        <p class="dialog-text">{t('settings.data.clearConfirmBody')}</p>
      </Dialog>
    </div>
  )
}

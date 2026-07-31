/* ⚙️ Settings (spec §9.8) — HONEST by design.
   - Appearance / Language / Chat defaults = runtime + persisted (localStorage).
   - Server = READ-ONLY from /health + /v1/debug/context (version taken from
     debug context, the accurate value — NOT /health's stale 0.11.0).
   - "Change for next start" = a SNIPPET GENERATOR (real WS_* env names from
     server/config.py). It never pretends to edit the running server; /v1/config
     (P4) is shown as n/a until it exists.
   - Data = clear chat history (confirm) + export/import prefs (client-only). */
import { useEffect } from 'preact/hooks'
import { useSignal } from '@preact/signals'
import { Copy, Download, DownloadCloud, FileJson, Sparkles, Trash2, Upload } from 'lucide-preact'
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
const REPO_URL = 'https://github.com/mrDedchai/OpenCode-workspace'
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
  { key: 'host', env: 'WS_HOST', label: 'server.field.host' },
  { key: 'port', env: 'WS_PORT', label: 'server.field.port' },
  { key: 'bufferMb', env: 'WS_BUFFER_MB', label: 'server.field.bufferMb' },
  { key: 'nCtx', env: 'WS_N_CTX', label: 'server.field.nCtx' },
  { key: 'nThreads', env: 'WS_N_THREADS', label: 'server.field.nThreads' },
  { key: 'idleTimeout', env: 'WS_IDLE_TIMEOUT', label: 'server.field.idleTimeout' },
  { key: 'maxModels', env: 'WS_MAX_MODELS', label: 'server.field.maxModels' },
  { key: 'logLevel', env: 'WS_LOG_LEVEL', label: 'server.field.logLevel' },
]

interface EnvDraft {
  host: string
  port: string
  bufferMb: string
  nCtx: string
  nThreads: string
  idleTimeout: string
  maxModels: string
  logLevel: string
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

  useEffect(() => {
    // accurate version + redacted snapshot for About/Diagnostics/Server
    dbgLoading.value = true
    void fetchDebugContext().then((c) => {
      dbg.value = c
      dbgLoading.value = false
    })
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
      <section class="md-section">
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
      <section class="md-section">
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
      <section class="md-section">
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

      {/* Server (read-only + apply-on-restart) */}
      <section class="md-section">
        <h2 class="md-section__title">{t('settings.server.title')}</h2>
        <Card class="set-card">
          <h3 class="set-subtitle">{t('settings.server.readTitle')}</h3>
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
          <p class="set-note">
            <Tip label={t('settings.server.healthVersionNote')} /> {t('settings.server.healthVersionNote')}
          </p>
          <p class="set-note">
            <Tip label={t('settings.server.p4Note')} /> {t('settings.server.p4Note')}
          </p>

          <h3 class="set-subtitle">{t('settings.server.applyTitle')}</h3>
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
          <p class="set-note">⚠️ {t('settings.server.restartNote')}</p>
        </Card>
      </section>

      {/* Data */}
      <section class="md-section">
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
      <section class="md-section">
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
        </Card>
      </section>

      {/* About */}
      <section class="md-section">
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

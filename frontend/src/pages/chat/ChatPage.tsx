/* 💬 Chat (spec §9.2) — real conversations (localStorage), SSE streaming
   via /v1/chat/completions with rAF batching, Stop keeps partial text,
   sticky-bottom (80px), XSS-safe markdown + code copy, <think> accordions,
   desktop notification on long background generations, parameter drawer,
   system-prompt presets, export .md.

   Honest capability labels: agent mode + reasoning effort are accepted by
   the server but NOT executed (tooltips say so — honest telemetry covers
   capabilities too). Per-message tok/s + tokens come from /v1/stats AFTER
   the run (the stream carries no usage field). */
import { useEffect, useRef } from 'preact/hooks'
import { useSignal } from '@preact/signals'
import {
  Bot,
  Brain,
  ChevronDown,
  CircleStop,
  Copy,
  Eye,
  EyeOff,
  PanelLeftClose,
  PanelLeftOpen,
  Send,
  Settings2,
} from 'lucide-preact'
import { sseRequest } from '@/core/api'
import { Badge } from '@/components/Badge'
import { Button } from '@/components/Button'
import { Drawer } from '@/components/Drawer'
import { EmptyState } from '@/components/EmptyState'
import { Menu } from '@/components/Menu'
import { Segmented } from '@/components/Segmented'
import { Tip } from '@/components/Tip'
import { toast } from '@/components/Toast'
import { navigate } from '@/core/router'
import { models } from '@/core/store'
import { chatFocusModel } from '@/core/nav-hints'
import { fetchStats } from '@/core/stats'
import { guessQuant } from '@/core/models'
import { renderMarkdown } from '@/core/markdown'
import { fmtNumber, t } from '@/i18n'
import {
  activeConv,
  activeId,
  autoTitle,
  createConversation,
  notificationsEnabled,
  persist,
  selectConversation,
  type ChatMsg,
  type Conversation,
} from './store'
import { ConversationSidebar } from './ConversationSidebar'
import { ParamDrawer } from './ParamDrawer'
import { RichText } from './RichText'

const LS_NOTIF_ASKED = 'ws-notif-asked'
const STICK_PX = 80
const NOTIFY_AFTER_MS = 20_000

function maybeAskNotificationPermission() {
  if (typeof Notification === 'undefined') return
  try {
    if (Notification.permission === 'default' && localStorage.getItem(LS_NOTIF_ASKED) !== '1') {
      localStorage.setItem(LS_NOTIF_ASKED, '1')
      Notification.requestPermission().catch(() => undefined)
    }
  } catch { /* non-fatal */ }
}

export function ChatPage() {
  const draft = useSignal('')
  const generating = useSignal(false)
  const msgTick = useSignal(0) // bump to repaint streaming message
  const drawerOpen = useSignal(false)
  const sideDrawer = useSignal(false) // mobile sidebar sheet
  const sideCollapsed = useSignal(false) // desktop rail
  const agentMode = useSignal<'default' | 'agent'>('default')
  // Reasoning effort — per-model override persisted in localStorage, because
  // models support different effort levels (user feedback). Default medium.
  const effort = useSignal<'low' | 'medium' | 'high'>('medium')
  const effortModel = useSignal<string | null>(null) // model the override belongs to
  const readEffort = (modelId: string): 'low' | 'medium' | 'high' => {
    try {
      const v = localStorage.getItem(`ws-effort:${modelId}`)
      if (v === 'low' || v === 'medium' || v === 'high') return v
    } catch { /* non-fatal */ }
    return 'medium'
  }
  const setEffort = (v: 'low' | 'medium' | 'high') => {
    effort.value = v
    const id = activeConv.value?.model
    if (id) {
      effortModel.value = id
      try { localStorage.setItem(`ws-effort:${id}`, v) } catch { /* non-fatal */ }
    }
  }
  // Reasoning mode (P7.1c) — auto/on/off, per-model, persisted. Only shown
  // for reasoning-capable models (like Jan). Sent to server as reasoning_mode.
  const reasoningMode = useSignal<'auto' | 'on' | 'off'>('auto')
  const reasoningModel = useSignal<string | null>(null)
  const readReasoning = (modelId: string): 'auto' | 'on' | 'off' => {
    try {
      const v = localStorage.getItem(`ws-reasoning:${modelId}`)
      if (v === 'auto' || v === 'on' || v === 'off') return v
    } catch { /* non-fatal */ }
    return 'auto'
  }
  const cycleReasoning = () => {
    const next = reasoningMode.value === 'auto' ? 'on' : reasoningMode.value === 'on' ? 'off' : 'auto'
    reasoningMode.value = next
    const id = activeConv.value?.model
    if (id) {
      reasoningModel.value = id
      try { localStorage.setItem(`ws-reasoning:${id}`, next) } catch { /* non-fatal */ }
    }
  }
  // Thinking budget (P7.1c) — 5 levels like Jan: low/medium/high/xhigh/
  // unlimited. Per-model, persisted. Sent to server as thinking_budget.
  const thinkingBudget = useSignal<'low' | 'medium' | 'high' | 'xhigh' | 'unlimited'>('unlimited')
  const budgetModel = useSignal<string | null>(null)
  const readBudget = (modelId: string): 'low' | 'medium' | 'high' | 'xhigh' | 'unlimited' => {
    try {
      const v = localStorage.getItem(`ws-budget:${modelId}`)
      if (v === 'low' || v === 'medium' || v === 'high' || v === 'xhigh' || v === 'unlimited') return v
    } catch { /* non-fatal */ }
    return 'unlimited'
  }
  const setBudget = (v: 'low' | 'medium' | 'high' | 'xhigh' | 'unlimited') => {
    thinkingBudget.value = v
    const id = activeConv.value?.model
    if (id) {
      budgetModel.value = id
      try { localStorage.setItem(`ws-budget:${id}`, v) } catch { /* non-fatal */ }
    }
  }
  // User toggle: show/hide completed thinking accordions (persisted).
  const showThinking = useSignal<boolean>(() => {
    try {
      return localStorage.getItem('ws-show-thinking') !== '0'
    } catch {
      return true
    }
  })
  const toggleThinking = () => {
    showThinking.value = !showThinking.value
    try {
      localStorage.setItem('ws-show-thinking', showThinking.value ? '1' : '0')
    } catch { /* non-fatal */ }
  }

  const scrollRef = useRef<HTMLDivElement>(null)
  const stickRef = useRef(true)
  const abortRef = useRef<(() => void) | null>(null)
  const taRef = useRef<HTMLTextAreaElement>(null)

  const loaded = models.value

  // Consume "use in chat" hint from Models (once).
  if (chatFocusModel.value) {
    const wanted = chatFocusModel.value
    chatFocusModel.value = ''
    const conv = activeConv.value
    if (conv && loaded.some((m) => m.id === wanted)) {
      conv.model = wanted
      persist(conv)
    }
  }

  // Ensure there is an active conversation when models exist.
  if (!activeId.value && loaded.length > 0) {
    createConversation(loaded[0].id)
  }

  const conv = activeConv.value

  // Sync per-model effort: when the active model changes, load its saved
  // override (honest per-model preference). Must run after `conv` exists.
  if (conv?.model && conv.model !== effortModel.value) {
    effortModel.value = conv.model
    effort.value = readEffort(conv.model)
  }
  // Sync per-model reasoning mode (P7.1c) — same pattern as effort.
  if (conv?.model && conv.model !== reasoningModel.value) {
    reasoningModel.value = conv.model
    reasoningMode.value = readReasoning(conv.model)
  }
  // Sync per-model thinking budget (P7.1c) — same pattern.
  if (conv?.model && conv.model !== budgetModel.value) {
    budgetModel.value = conv.model
    thinkingBudget.value = readBudget(conv.model)
  }
  // Is the active model reasoning-capable? (from backend capabilities)
  const activeModel = loaded.find((m) => m.id === conv?.model) ?? null
  const reasoningCapable = activeModel?.capabilities?.reasoning ?? false

  useEffect(() => () => abortRef.current?.(), [])

  // Copy-button delegation for rendered code blocks.
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const onClick = (e: Event) => {
      const btn = (e.target as HTMLElement | null)?.closest?.('.codeblock__copy') as HTMLButtonElement | null
      if (!btn) return
      const code = btn.closest('.codeblock')?.querySelector('code')?.textContent ?? ''
      navigator.clipboard
        ?.writeText(code)
        .then(() => {
          const prev = btn.textContent
          btn.textContent = t('common.copied')
          btn.classList.add('is-copied')
          window.setTimeout(() => {
            btn.textContent = prev
            btn.classList.remove('is-copied')
          }, 1500)
        })
        .catch(() => toast('error', t('chat.copyFailed')))
    }
    el.addEventListener('click', onClick)
    return () => el.removeEventListener('click', onClick)
  }, [])

  const onScroll = () => {
    const el = scrollRef.current
    if (!el) return
    stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < STICK_PX
  }

  const scrollToBottom = () => {
    const el = scrollRef.current
    if (el && stickRef.current) el.scrollTop = el.scrollHeight
  }

  const mutateConv = (fn: (c: Conversation) => void) => {
    const c = activeConv.value
    if (!c) return
    fn(c)
    persist(c)
    msgTick.value += 1
  }

  const stop = () => abortRef.current?.()

  const send = async () => {
    const text = draft.value.trim()
    let c = activeConv.value
    if (!c) {
      if (loaded.length === 0) return
      c = createConversation(loaded[0].id)
    }
    if (!text || generating.value || !c.model) return

    maybeAskNotificationPermission()
    const startedAt = Date.now()

    autoTitle(c, text)
    const userMsg: ChatMsg = { role: 'user', content: text, ts: Date.now() }
    const botMsg: ChatMsg = { role: 'assistant', content: '', ts: Date.now() }
    c.messages.push(userMsg, botMsg)
    persist(c)
    draft.value = ''
    if (taRef.current) taRef.current.style.height = 'auto'
    generating.value = true
    stickRef.current = true

    const sys = [
      c.systemPrompt.trim(),
      agentMode.value === 'agent' ? t('chat.agent.suffix') : '',
    ]
      .filter(Boolean)
      .join('\n\n')
    const history = c.messages
      .slice(0, -1) // drop the empty assistant placeholder
      .filter((m) => m.content.trim())
      .map((m) => ({ role: m.role, content: m.content }))
    const messages = [...(sys ? [{ role: 'system', content: sys }] : []), ...history]

    const { response, abort } = sseRequest('/v1/chat/completions', {
      model: c.model,
      messages,
      stream: true,
      temperature: c.params.temperature,
      top_p: c.params.top_p,
      max_tokens: c.params.max_tokens,
      reasoning_effort: effort.value,
      reasoning_mode: reasoningCapable ? reasoningMode.value : undefined,
      thinking_budget: reasoningCapable ? thinkingBudget.value : undefined,
    })
    abortRef.current = abort

    let acc = ''
    let raf = 0
    let stopped = false
    let errMsg = ''
    const flush = () => {
      raf = 0
      botMsg.content = acc
      msgTick.value += 1
      scrollToBottom()
    }

    try {
      const res = await response
      if (!res.ok || !res.body) {
        let detail = `HTTP ${res.status}`
        try {
          const body = await res.json()
          if (body?.detail) detail = String(body.detail)
        } catch { /* non-JSON */ }
        throw new Error(detail)
      }
      const reader = res.body.getReader()
      const dec = new TextDecoder()
      let buf = ''
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        let idx: number
        while ((idx = buf.indexOf('\n')) !== -1) {
          const line = buf.slice(0, idx).trim()
          buf = buf.slice(idx + 1)
          if (!line.startsWith('data:')) continue
          const payload = line.slice(5).trim()
          if (!payload || payload === '[DONE]') continue
          try {
            const chunk = JSON.parse(payload)
            const delta = chunk?.choices?.[0]?.delta?.content
            if (typeof delta === 'string' && delta) {
              acc += delta
              if (!raf) raf = requestAnimationFrame(flush)
            }
          } catch {
            /* partial JSON fragment — wait for more */
          }
        }
      }
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') {
        stopped = true
      } else {
        errMsg = e instanceof Error ? e.message : String(e)
      }
    } finally {
      if (raf) cancelAnimationFrame(raf)
      flush()
      generating.value = false
      abortRef.current = null
      botMsg.stopped = stopped || undefined
      botMsg.error = errMsg || undefined

      // Footer stats — real numbers from /v1/stats (last generation block).
      // Call WITHOUT ?model=: the server puts a single model's stat dict
      // directly under `models` in that mode (api_server.py:181 — it is not
      // keyed by id), so only the all-models shape matches StatsPayload and
      // can be indexed by our model id.
      try {
        const s = await fetchStats(undefined, 5000)
        const g = s.models[c!.model]?.generation
        if (g && typeof g.tokens_per_sec === 'number' && g.tokens_per_sec > 0) {
          botMsg.stats = {
            tokS: g.tokens_per_sec,
            tokens: typeof g.token_count === 'number' ? g.token_count : undefined,
          }
        }
      } catch { /* footer simply stays empty — honest */ }

      persist(c!)
      msgTick.value += 1

      if (errMsg) toast('error', t('chat.genFailed'), { body: errMsg })
      if (!errMsg && notificationsEnabled.value && Date.now() - startedAt > NOTIFY_AFTER_MS && document.hidden) {
        try {
          if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
            new Notification(t('chat.notif.title'), { body: t('chat.notif.body') })
          }
        } catch { /* non-fatal */ }
      }
    }
  }

  const onComposerKey = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void send()
    }
  }

  const autoGrow = () => {
    const ta = taRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`
  }

  const msgs = conv?.messages ?? []
  const chars = draft.value.length
  const estTokens = chars > 0 ? Math.max(1, Math.ceil(chars / 3)) : 0
  void msgTick.value // subscribe → repaint while streaming

  return (
    <div class={`chat${sideCollapsed.value ? ' chat--collapsed' : ''}`}>
      {/* ── Conversation sidebar (desktop) ────────────────────── */}
      <aside class="chat__side" aria-hidden={sideCollapsed.value || undefined}>
        <ConversationSidebar onNew={() => loaded.length && createConversation(loaded[0].id)} />
      </aside>

      {/* ── Mobile sidebar sheet ──────────────────────────────── */}
      {/* side="left": the toggle that opens this lives in the top-LEFT of the
          toolbar, so the sheet must enter from the left (see Drawer convention). */}
      <Drawer open={sideDrawer.value} onClose={() => (sideDrawer.value = false)} title={t('chat.side.title')} width={320} side="left">
        <ConversationSidebar
          onNew={() => {
            if (loaded.length) createConversation(loaded[0].id)
            sideDrawer.value = false
          }}
        />
      </Drawer>

      <section class="chat__main">
        {/* toolbar */}
        <header class="chat__toolbar">
          <button
            class="icon-btn chat__side-toggle chat__side-toggle--desktop"
            aria-label={sideCollapsed.value ? t('chat.side.show') : t('chat.side.hide')}
            onClick={() => (sideCollapsed.value = !sideCollapsed.value)}
          >
            {sideCollapsed.value ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          </button>
          <button
            class="icon-btn chat__side-toggle chat__side-toggle--mobile"
            aria-label={t('chat.side.title')}
            onClick={() => (sideDrawer.value = true)}
          >
            <PanelLeftOpen size={16} />
          </button>

          {loaded.length > 0 ? (
            <Menu
              ariaLabel={t('chat.model.label')}
              align="start"
              trigger={
                <span class="chat__model-trigger">
                  🧠 <b>{conv?.model || loaded[0].id}</b>
                  {guessQuant(conv?.model) ? <Badge tone="brand">{guessQuant(conv!.model)}</Badge> : null}
                  <ChevronDown size={13} aria-hidden="true" />
                </span>
              }
              header={t('chat.model.label')}
              items={[
                ...loaded.map((m) => ({
                  key: m.id,
                  label: (
                    <>
                      {m.id}{' '}
                      {guessQuant(m.path || m.id) ? <Badge tone="brand">{guessQuant(m.path || m.id)}</Badge> : null}
                    </>
                  ),
                  active: conv?.model === m.id,
                  hint: m.arch ?? undefined,
                  onSelect: () => mutateConv((c) => (c.model = m.id)),
                })),
                {
                  key: '__models',
                  label: `🧩 ${t('chat.model.manage')}`,
                  onSelect: () => navigate('models'),
                },
                {
                  key: '__hub',
                  label: `🌐 ${t('chat.model.hub')}`,
                  onSelect: () => navigate('hub'),
                },
              ]}
            />
          ) : (
            <Button variant="soft" size="sm" onClick={() => navigate('models')}>
              {t('chat.model.none')}
            </Button>
          )}

          <span class="chat__tool-group">
            <Menu
              ariaLabel={t('chat.agent.label')}
              align="start"
              trigger={
                <span class="chat__model-trigger">
                  {agentMode.value === 'agent' ? '🤖' : '💬'} {t(`chat.agent.${agentMode.value}`)}
                  <ChevronDown size={13} aria-hidden="true" />
                </span>
              }
              header={t('chat.agent.label')}
              items={[
                {
                  key: 'default',
                  label: t('chat.agent.default'),
                  active: agentMode.value === 'default',
                  onSelect: () => (agentMode.value = 'default'),
                },
                {
                  key: 'agent',
                  label: t('chat.agent.agent'),
                  active: agentMode.value === 'agent',
                  onSelect: () => (agentMode.value = 'agent'),
                },
              ]}
            />
            <Tip label={t('chat.agent.tip')} />
          </span>

          <span class="chat__tool-group">
            <Segmented
              ariaLabel={t('chat.effort.label')}
              size="sm"
              value={effort.value}
              onChange={(v) => setEffort(v as 'low' | 'medium' | 'high')}
              options={[
                { value: 'low', label: t('chat.effort.low') },
                { value: 'medium', label: t('chat.effort.med') },
                { value: 'high', label: t('chat.effort.high') },
              ]}
            />
            <Tip label={t('chat.effort.tip')} />
          </span>

          {/* Reasoning mode (P7.1c) — 3-state Auto/On/Off, only for
              reasoning-capable models (like Jan). Cycles on click. */}
          {reasoningCapable ? (
            <button
              class={`icon-btn${reasoningMode.value !== 'auto' ? ' is-active' : ''}`}
              aria-label={t('chat.reasoning.label')}
              aria-pressed={reasoningMode.value !== 'auto'}
              title={`${t('chat.reasoning.label')}: ${t(`chat.reasoning.${reasoningMode.value}`)}`}
              onClick={cycleReasoning}
            >
              <Brain size={16} />
              <span class="icon-btn__badge">{reasoningMode.value === 'auto' ? 'A' : reasoningMode.value === 'on' ? '1' : '0'}</span>
            </button>
          ) : null}

          {/* Thinking budget (P7.1c) — 5 levels like Jan, only for reasoning
              models. Compact select. */}
          {reasoningCapable ? (
            <select
              class="icon-btn thinking-budget"
              aria-label={t('chat.budget.label')}
              title={t('chat.budget.label')}
              value={thinkingBudget.value}
              onChange={(e) => setBudget((e.target as HTMLSelectElement).value as typeof thinkingBudget.value)}
            >
              <option value="low">{t('chat.budget.low')}</option>
              <option value="medium">{t('chat.budget.medium')}</option>
              <option value="high">{t('chat.budget.high')}</option>
              <option value="xhigh">{t('chat.budget.xhigh')}</option>
              <option value="unlimited">{t('chat.budget.unlimited')}</option>
            </select>
          ) : null}

          {/* Thinking visibility toggle (user feedback: show/hide thinking) */}
          <button
            class={`icon-btn${showThinking.value ? ' is-active' : ''}`}
            aria-label={t('chat.thinkingToggle')}
            aria-pressed={showThinking.value}
            title={t('chat.thinkingToggle')}
            onClick={toggleThinking}
          >
            {showThinking.value ? <Eye size={16} /> : <EyeOff size={16} />}
          </button>

          <span class="chat__toolbar-spacer" />

          <button class="icon-btn" aria-label={t('chat.drawer.title')} onClick={() => (drawerOpen.value = true)}>
            <Settings2 size={16} />
          </button>
        </header>

        {/* messages */}
        <div class="chat__scroll" ref={scrollRef} onScroll={onScroll}>
          {msgs.length === 0 ? (
            <div class="chat__emptywrap">
              {loaded.length === 0 ? (
                <EmptyState emoji="🧠" title={t('chat.empty.noModelTitle')} body={t('chat.empty.noModelBody')}>
                  <Button variant="primary" onClick={() => navigate('models')}>
                    {t('chat.empty.goModels')}
                  </Button>
                </EmptyState>
              ) : (
                <EmptyState emoji="💬" title={t('chat.empty.title')} body={t('chat.empty.body')} />
              )}
            </div>
          ) : (
            <div class="chat__msgs">
              {msgs.map((m, i) => {
                const streaming = generating.value && m.role === 'assistant' && i === msgs.length - 1
                return (
                  <article key={i} class={`msg msg--${m.role}`}>
                    {m.role === 'assistant' ? (
                      <div class="msg__avatar" aria-hidden="true">
                        <Bot size={15} />
                      </div>
                    ) : null}
                    <div class="msg__bubble">
                      {m.role === 'user' ? (
                        <div class="msg__md" dangerouslySetInnerHTML={{ __html: renderMarkdown(m.content) }} />
                      ) : (
                        <RichText text={m.content} streaming={streaming} showThinking={showThinking.value} />
                      )}
                      {m.error ? <p class="msg__error">⚠️ {m.error}</p> : null}
                      {streaming && !m.content ? <span class="msg__dots" aria-hidden="true" /> : null}
                      {!streaming && (m.stats || m.stopped) ? (
                        <footer class="msg__foot tnum">
                          {m.stats?.tokS != null ? (
                            <span>▲ {fmtNumber(m.stats.tokS, { maximumFractionDigits: 1 })} tok/s</span>
                          ) : null}
                          {m.stats?.tokens != null ? <span>· {fmtNumber(m.stats.tokens)} tokens</span> : null}
                          {m.stopped ? <Badge tone="warn">{t('chat.stopped')}</Badge> : null}
                        </footer>
                      ) : null}
                      {m.role === 'assistant' && !streaming && m.content ? (
                        <button
                          class="msg__copy"
                          aria-label={t('common.copy')}
                          title={t('common.copy')}
                          onClick={() => {
                            navigator.clipboard
                              ?.writeText(m.content)
                              .then(() => toast('success', t('common.copied')))
                              .catch(() => toast('error', t('chat.copyFailed')))
                          }}
                        >
                          <Copy size={12} /> {t('common.copy')}
                        </button>
                      ) : null}
                    </div>
                  </article>
                )
              })}
            </div>
          )}
          {/* live-region: announce run state, never per-token (spec §7.2) */}
          <p class="sr-only" aria-live="polite" role="status">
            {generating.value ? t('common.a11y.generating') : msgs.length ? t('common.a11y.generationDone') : ''}
          </p>
        </div>

        {/* composer */}
        <footer class="chat__composer">
          {conv && loaded.length > 0 ? (
            <>
              <textarea
                ref={taRef}
                class="chat__input"
                rows={1}
                placeholder={t('chat.composer.placeholder')}
                value={draft.value}
                onInput={(e) => {
                  draft.value = (e.target as HTMLTextAreaElement).value
                  autoGrow()
                }}
                onKeyDown={onComposerKey}
                aria-label={t('chat.composer.placeholder')}
              />
              <div class="chat__composer-meta">
                <span class="tnum">
                  {chars > 0 ? t('chat.composer.estimate', { chars: fmtNumber(chars), tokens: fmtNumber(estTokens) }) : ''}
                </span>
                {generating.value ? (
                  <Button variant="danger" onClick={stop}>
                    <CircleStop size={15} aria-hidden="true" /> {t('chat.composer.stop')}
                  </Button>
                ) : (
                  <Button variant="primary" disabled={!chars} onClick={() => void send()}>
                    <Send size={15} aria-hidden="true" /> {t('chat.composer.send')}
                  </Button>
                )}
              </div>
            </>
          ) : (
            <div class="chat__composer-off">
              {loaded.length === 0 ? t('chat.composer.noModel') : t('common.loading')}
            </div>
          )}
        </footer>
      </section>

      <ParamDrawer open={drawerOpen.value} onClose={() => (drawerOpen.value = false)} conv={conv} onChange={mutateConv} />
    </div>
  )
}

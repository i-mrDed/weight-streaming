/* 💬 Chat (spec §9.2) — real conversations (localStorage), SSE streaming
   via /v1/chat/completions with rAF batching, Stop keeps partial text,
   sticky-bottom (80px), XSS-safe markdown + code copy, <think> accordions,
   desktop notification on long background generations, parameter drawer,
   system-prompt presets, export .md.

   Agent mode (AGENT_TOOLS_PLAN.md): real tool loop — sends tools (MCP ∪
   built-in workspace tools) as non-streaming turns, executes tool_calls,
   feeds results back as `tool` role messages, capped at MAX_AGENT_ITERS.
   Per-message tok/s + tokens come from /v1/stats AFTER the run (the stream
   carries no usage field). */
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
import { callAgentTool, callMCPTool, listAgentTools, listMCPTools, sseRequest } from '@/core/api'
import {
  MAX_AGENT_ITERS,
  buildWireMessages,
  formatToolResult,
  toolWireName,
  truncateToolResult,
  type WireMsg,
  type WireToolDef,
} from '@/core/chat'
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
import { routeTiering } from '@/core/tiering'
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
import { assistants, refreshAssistants } from '@/core/assistants'
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
  // Assistant (P7.2): select a persona → apply its system prompt to the conv.
  // The list lives in the shared assistants store (core/assistants) — the
  // Chat toolbar and the Assistants page read the same signal, so a
  // create/edit/delete there is instantly visible here. Refresh on mount so
  // direct visits (deep link / first load) are never stale.
  useEffect(() => {
    refreshAssistants().catch(() => { /* non-fatal — offline */ })
  }, [])
  const applyAssistant = async (id: string) => {
    if (!id) return
    const a = assistants.value.find((x) => x.id === id)
    if (a && conv) {
      mutateConv((c) => { c.systemPrompt = a.system_prompt })
      toast('success', a.name)
    }
  }
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
  // NOTE: useSignal does NOT invoke a function initializer — the value must
  // be computed eagerly via IIFE, or the persisted preference is never read
  // and the stored function is used as the value (truthy) instead.
  const showThinking = useSignal<boolean>((() => {
    try {
      return localStorage.getItem('ws-show-thinking') !== '0'
    } catch {
      return true
    }
  })())
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
  const AUTO_MODEL = '__auto__'

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

  const stop = () => abortRef.current?.()  /** SSE streaming chat turn (default mode + final fallback when no tools). */
  const streamChat = async (
    c: Conversation,
    botMsg: ChatMsg,
    messages: WireMsg[],
    opts: { modelId: string; tierMaxTokens: number | null; startedAt: number },
  ) => {
    const { response, abort } = sseRequest('/v1/chat/completions', {
      model: opts.modelId,
      messages,
      stream: true,
      temperature: c.params.temperature,
      top_p: c.params.top_p,
      max_tokens: opts.tierMaxTokens ? Math.min(c.params.max_tokens, opts.tierMaxTokens) : c.params.max_tokens,
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
        const g = s.models[c.model]?.generation
        if (g && typeof g.tokens_per_sec === 'number' && g.tokens_per_sec > 0) {
          botMsg.stats = {
            tokS: g.tokens_per_sec,
            tokens: typeof g.token_count === 'number' ? g.token_count : undefined,
          }
        }
      } catch { /* footer simply stays empty — honest */ }

      persist(c)
      msgTick.value += 1

      if (errMsg) toast('error', t('chat.genFailed'), { body: errMsg })
      if (!errMsg && notificationsEnabled.value && Date.now() - opts.startedAt > NOTIFY_AFTER_MS && document.hidden) {
        try {
          if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
            new Notification(t('chat.notif.title'), { body: t('chat.notif.body') })
          }
        } catch { /* non-fatal */ }
      }
    }
  }

  /** Non-streaming single agent turn (model decides: content or tool_calls). */
  const chatOnce = async (
    c: Conversation,
    msgs: WireMsg[],
    toolDefs: WireToolDef[],
    opts: { modelId: string; tierMaxTokens: number | null },
  ): Promise<unknown | null> => {
    const { response, abort } = sseRequest('/v1/chat/completions', {
      model: opts.modelId,
      messages: msgs,
      stream: false,
      tools: toolDefs,
      // Tool-calling turns need the model to emit tool_calls JSON, not a
      // chain of thought. Qwen3-family templates default thinking ON;
      // llama-server reads this via chat_template_kwargs (P7.x E2E fix).
      chat_template_kwargs: { enable_thinking: false },
      temperature: c.params.temperature,
      top_p: c.params.top_p,
      max_tokens: opts.tierMaxTokens ? Math.min(c.params.max_tokens, opts.tierMaxTokens) : c.params.max_tokens,
      reasoning_effort: effort.value,
      reasoning_mode: reasoningCapable ? reasoningMode.value : undefined,
      thinking_budget: reasoningCapable ? thinkingBudget.value : undefined,
    })
    abortRef.current = abort
    try {
      const res = await response
      if (!res.ok) {
        let detail = `HTTP ${res.status}`
        try {
          const body = await res.json()
          if (body?.detail) detail = String(body.detail)
        } catch { /* non-JSON */ }
        throw new Error(detail)
      }
      return (await res.json()) as unknown
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') return null
      toast('error', t('chat.genFailed'), { body: e instanceof Error ? e.message : String(e) })
      return null
    } finally {
      abortRef.current = null
    }
  }

  /** Agent loop (AGENT_TOOLS_PLAN.md): tools → tool_calls → execute → loop. */
  const runAgent = async (
    c: Conversation,
    initial: WireMsg[],
    opts: { modelId: string; tierMaxTokens: number | null; startedAt: number },
  ) => {
    // Gather tools: MCP servers (P7.4) + built-in workspace tools.
    const toolDefs: WireToolDef[] = []
    const toolMap = new Map<
      string,
      { kind: 'mcp'; serverId: string; tool: string } | { kind: 'builtin'; tool: string }
    >()
    try {
      const [mcpTools, agentTools] = await Promise.all([listMCPTools(), listAgentTools()])
      for (const t of mcpTools) {
        const n = toolWireName(t.server_name, t.name)
        toolDefs.push({
          type: 'function',
          function: { name: n, description: t.description, parameters: (t.inputSchema ?? {}) as Record<string, unknown> },
        })
        toolMap.set(n, { kind: 'mcp', serverId: t.server_id, tool: t.name })
      }
      for (const t of agentTools) {
        toolDefs.push({ type: 'function', function: { name: t.name, description: t.description, parameters: t.parameters } })
        toolMap.set(t.name, { kind: 'builtin', tool: t.name })
      }
    } catch {
      /* server unreachable / endpoints missing → no tools, degrade to plain chat */
    }
    if (toolDefs.length === 0) {
      toast('info', t('chat.agent.noTools'))
      const botMsg: ChatMsg = { role: 'assistant', content: '', ts: Date.now() }
      c.messages.push(botMsg)
      persist(c)
      await streamChat(c, botMsg, initial, opts)
      return
    }

    let msgs = initial
    let iters = 0
    let finalText = ''

    while (iters < MAX_AGENT_ITERS) {
      iters += 1
      const data = await chatOnce(c, msgs, toolDefs, opts)
      if (!data) {
        finalText = ''
        break // aborted or failed — keep partial, mark stopped below
      }
      const choice = (data as { choices?: Array<{ message?: { content?: unknown; tool_calls?: unknown } }> })?.choices?.[0]
      const content = typeof choice?.message?.content === 'string' ? choice.message.content : ''
      const rawCalls: unknown[] = Array.isArray(choice?.message?.tool_calls) ? choice.message.tool_calls : []
      if (rawCalls.length === 0) {
        finalText = content
        break
      }

      // Assistant message with the requested tool calls.
      const asst: ChatMsg = {
        role: 'assistant',
        content: content || '',
        ts: Date.now(),
        tool_calls: rawCalls.map((rc, i) => {
          const r = rc as { id?: string; function?: { name?: string; arguments?: string } }
          return {
            id: r.id || `tc-${iters}-${i}`,
            name: r.function?.name || 'unknown',
            arguments: typeof r.function?.arguments === 'string' ? r.function.arguments : '{}',
          }
        }),
      }
      c.messages.push(asst)
      persist(c)
      msgTick.value += 1
      scrollToBottom()

      // Execute each call, feed the result back as a `tool` message.
      for (const tc of asst.tool_calls ?? []) {
        const toolMsg: ChatMsg = {
          role: 'tool',
          content: '',
          ts: Date.now(),
          tool_call_id: tc.id,
          name: tc.name,
          toolState: 'running',
        }
        c.messages.push(toolMsg)
        persist(c)
        msgTick.value += 1
        scrollToBottom()
        try {
          let args: unknown = {}
          try {
            args = tc.arguments ? JSON.parse(tc.arguments) : {}
          } catch {
            args = { raw: tc.arguments }
          }
          const ref = toolMap.get(tc.name)
          if (!ref) throw new Error(t('chat.tool.unknown', { name: tc.name }))
          const out =
            ref.kind === 'mcp'
              ? (await callMCPTool(ref.serverId, ref.tool, args)).result
              : (await callAgentTool(ref.tool, args)).result
          toolMsg.content = truncateToolResult(formatToolResult(out))
          toolMsg.toolState = 'done'
        } catch (e) {
          toolMsg.content = `⚠️ ${e instanceof Error ? e.message : String(e)}`
          toolMsg.toolState = 'error'
        }
        persist(c)
        msgTick.value += 1
        scrollToBottom()
      }
      msgs = buildWireMessages(c.messages)
    }

    const stopped = !finalText
    const botMsg: ChatMsg = {
      role: 'assistant',
      content: finalText || t('chat.agent.maxIters'),
      ts: Date.now(),
      stopped: stopped ? true : undefined,
    }
    c.messages.push(botMsg)
    persist(c)
    generating.value = false
    abortRef.current = null
    msgTick.value += 1
    scrollToBottom()

    if (notificationsEnabled.value && Date.now() - opts.startedAt > NOTIFY_AFTER_MS && document.hidden) {
      try {
        if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
          new Notification(t('chat.notif.title'), { body: t('chat.notif.body') })
        }
      } catch { /* non-fatal */ }
    }
  }

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
    c.messages.push(userMsg)
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
    const messages: WireMsg[] = [
      ...(sys ? [{ role: 'system' as const, content: sys }] : []),
      ...buildWireMessages(c.messages),
    ]

    // Auto-tiering: when the conversation is on ⚡ Auto, ask the server to
    // route this request to fast or quality and use the resolved model.
    let modelId = c.model
    // The tier's own output budget (EXP-023): the fast tier is for quick
    // answers — clamp max_tokens so a degenerate long generation (Gemma 4
    // repetition loop) burns at most the tier's budget, never the user's
    // 8K setting.
    let tierMaxTokens: number | null = null
    if (c.model === AUTO_MODEL) {
      try {
        const routed = await routeTiering({
          messages: messages.map((m) => ({ role: m.role, content: m.content ?? '' })),
          options: {
            reasoning_mode: reasoningCapable ? reasoningMode.value : undefined,
          },
        })
        modelId = routed.model_id
        tierMaxTokens = routed.max_tokens ?? null
        toast('info', `${t('chat.model.auto')} → ${routed.tier === 'fast' ? '⚡' : '🎯'} ${routed.model_id}`)
      } catch (e) {
        toast('error', String(e))
        generating.value = false
        return
      }
    }

    const opts = { modelId, tierMaxTokens, startedAt }

    if (agentMode.value === 'agent') {
      await runAgent(c, messages, opts)
    } else {
      const botMsg: ChatMsg = { role: 'assistant', content: '', ts: Date.now() }
      c.messages.push(botMsg)
      persist(c)
      await streamChat(c, botMsg, messages, opts)
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
                  {conv?.model === AUTO_MODEL ? (
                    <>⚡ <b>{t('chat.model.auto')}</b></>
                  ) : (
                    <>🧠 <b>{conv?.model || loaded[0].id}</b></>
                  )}
                  {conv?.model !== AUTO_MODEL && guessQuant(conv?.model)
                    ? <Badge tone="brand">{guessQuant(conv!.model)}</Badge>
                    : null}
                  <ChevronDown size={13} aria-hidden="true" />
                </span>
              }
              header={t('chat.model.label')}
              items={[
                {
                  key: AUTO_MODEL,
                  label: t('chat.model.auto'),
                  active: conv?.model === AUTO_MODEL,
                  hint: t('chat.model.autoHint'),
                  onSelect: () => mutateConv((c) => (c.model = AUTO_MODEL)),
                },
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
              models. Custom Menu, NOT a native <select>: Chrome on Windows
              draws its own OS popup that ignores option colours, so the
              dropdown text blended into the background (user feedback). The
              Menu panel is fully CSS-themed with high-contrast text. */}
          {reasoningCapable ? (
            <Menu
              ariaLabel={`${t('chat.budget.label')}: ${t(`chat.budget.${thinkingBudget.value}`)}`}
              align="start"
              trigger={
                <span class="chat__budget-trigger">
                  ⚡ {t(`chat.budget.${thinkingBudget.value}`)}
                  <ChevronDown size={13} aria-hidden="true" />
                </span>
              }
              header={t('chat.budget.label')}
              items={(['low', 'medium', 'high', 'xhigh', 'unlimited'] as const).map((v) => ({
                key: v,
                label: t(`chat.budget.${v}`),
                active: thinkingBudget.value === v,
                onSelect: () => setBudget(v),
              }))}
            />
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

          {/* Assistant selector (P7.2) — apply a persona's system prompt.
              Same Menu conversion as the budget selector: the native <select>
              popup is OS-drawn on Chrome/Windows and ignores option colours. */}
          {assistants.value.length > 0 ? (
            <Menu
              ariaLabel={t('chat.assistant')}
              align="start"
              trigger={
                <span class="chat__assistant-trigger">
                  🧑 {t('chat.assistant')}
                  <ChevronDown size={13} aria-hidden="true" />
                </span>
              }
              header={t('chat.assistant')}
              items={assistants.value.map((a) => ({
                key: a.id,
                label: a.name,
                onSelect: () => void applyAssistant(a.id),
              }))}
            />
          ) : null}

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
                const toolCalls = m.role === 'assistant' ? m.tool_calls : undefined
                return (
                  <article key={i} class={`msg msg--${m.role}`}>
                    {m.role === 'assistant' ? (
                      <div class="msg__avatar" aria-hidden="true">
                        <Bot size={15} />
                      </div>
                    ) : null}
                    <div class="msg__bubble">
                      {m.role === 'tool' ? (
                        <div
                          class={`tool-card${m.toolState === 'error' ? ' tool-card--error' : ''}${m.toolState === 'running' ? ' tool-card--running' : ''}`}
                        >
                          <div class="tool-card__head">
                            <span class="tool-card__icon" aria-hidden="true">🛠️</span>
                            <span class="tool-card__name">{m.name || t('chat.tool.label')}</span>
                            <span class="tool-card__state">
                              {m.toolState === 'running'
                                ? t('chat.tool.running')
                                : m.toolState === 'error'
                                  ? t('chat.tool.error')
                                  : t('chat.tool.done')}
                            </span>
                          </div>
                          {m.toolState === 'running' ? (
                            <span class="msg__dots" aria-hidden="true" />
                          ) : m.toolState === 'error' ? (
                            <p class="tool-card__err">{m.content}</p>
                          ) : m.content ? (
                            <details class="tool-card__result">
                              <summary>{t('chat.tool.result')}</summary>
                              <pre class="tool-card__pre">{m.content}</pre>
                            </details>
                          ) : null}
                        </div>
                      ) : (
                        <>
                          {toolCalls?.length ? (
                            <div class="tool-card">
                              {toolCalls.map((tc, j) => (
                                <div key={j} class="tool-card__call">
                                  <span class="tool-card__icon" aria-hidden="true">🔧</span>
                                  <span class="tool-card__name">{tc.name}</span>
                                  <details class="tool-card__args">
                                    <summary>{t('chat.tool.args')}</summary>
                                    <pre class="tool-card__pre">{tc.arguments}</pre>
                                  </details>
                                </div>
                              ))}
                            </div>
                          ) : null}
                          {m.role === 'user' ? (
                            <div class="msg__md" dangerouslySetInnerHTML={{ __html: renderMarkdown(m.content) }} />
                          ) : (
                            <RichText text={m.content} streaming={streaming} showThinking={showThinking.value} />
                          )}
                          {m.error ? <p class="msg__error">⚠️ {m.error}</p> : null}
                          {streaming && !m.content && !toolCalls?.length ? <span class="msg__dots" aria-hidden="true" /> : null}
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
                        </>
                      )}
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

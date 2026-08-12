/* Chat conversations — real persistence in localStorage (spec §9.2):
   one index key + one key per conversation. No server storage exists for
   chat; this is honest client-side history. */
import { signal } from '@preact/signals'
import { t } from '@/i18n'

export type ChatRole = 'user' | 'assistant' | 'tool'

export interface MsgStats {
  tokS?: number
  tokens?: number
}

/** A tool call requested by the model (P7.3 wire shape, client copy). */
export interface ChatToolCall {
  id: string
  name: string
  arguments: string
}

export type ToolState = 'running' | 'done' | 'error'

export interface ChatMsg {
  role: ChatRole
  content: string
  ts: number
  stopped?: boolean
  error?: string
  stats?: MsgStats
  /** assistant only — tool calls the model requested (agent mode) */
  tool_calls?: ChatToolCall[]
  /** tool role only — id the model used in tool_calls */
  tool_call_id?: string
  /** tool role only — wire tool name (e.g. filesystem.read_file) */
  name?: string
  /** tool role only — running/done/error for the tool card */
  toolState?: ToolState
}

export interface ChatParams {
  temperature: number
  top_p: number
  max_tokens: number
}

export interface Conversation {
  id: string
  title: string
  model: string
  createdAt: number
  updatedAt: number
  systemPrompt: string
  params: ChatParams
  /** use params/systemPrompt stored on THIS conversation vs global defaults */
  perConv: boolean
  messages: ChatMsg[]
}

export interface ConvMeta {
  id: string
  title: string
  model: string
  createdAt: number
  updatedAt: number
}

const INDEX_KEY = 'ws-chat-index-v1'
const convKey = (id: string) => `ws-chat-conv-v1-${id}`
const DEFAULTS_KEY = 'ws-chat-defaults-v1'
const LS_NOTIF = 'ws-chat-notif'

/** Desktop-notification preference for long background generations. Defaults
 *  ON; the browser still gates on actual permission (Settings has a test). */
export const notificationsEnabled = signal<boolean>((() => {
  try {
    return localStorage.getItem(LS_NOTIF) !== '0'
  } catch {
    return true
  }
})())

export function setNotificationsEnabled(on: boolean) {
  notificationsEnabled.value = on
  try {
    if (on) localStorage.removeItem(LS_NOTIF)
    else localStorage.setItem(LS_NOTIF, '0')
  } catch {
    /* non-fatal */
  }
}

export const DEFAULT_PARAMS: ChatParams = { temperature: 0.7, top_p: 0.95, max_tokens: 1024 }

export function readDefaults(): { params: ChatParams; systemPrompt: string; perConv: boolean } {
  try {
    const raw = JSON.parse(localStorage.getItem(DEFAULTS_KEY) || 'null')
    if (raw) {
      return {
        params: { ...DEFAULT_PARAMS, ...raw.params },
        systemPrompt: typeof raw.systemPrompt === 'string' ? raw.systemPrompt : '',
        perConv: raw.perConv !== false,
      }
    }
  } catch { /* fresh */ }
  return { params: { ...DEFAULT_PARAMS }, systemPrompt: '', perConv: true }
}

export function writeDefaults(d: { params: ChatParams; systemPrompt: string; perConv: boolean }) {
  try {
    localStorage.setItem(DEFAULTS_KEY, JSON.stringify(d))
  } catch { /* non-fatal */ }
}

function readIndex(): ConvMeta[] {
  try {
    const raw = JSON.parse(localStorage.getItem(INDEX_KEY) || '[]')
    return Array.isArray(raw) ? raw : []
  } catch {
    return []
  }
}

export const convIndex = signal<ConvMeta[]>(readIndex())
export const activeId = signal<string | null>(null)
export const activeConv = signal<Conversation | null>(null)

function writeIndex(list: ConvMeta[]) {
  convIndex.value = list
  try {
    localStorage.setItem(INDEX_KEY, JSON.stringify(list))
  } catch { /* storage full / private mode — in-memory keeps working */ }
}

export function loadConversation(id: string): Conversation | null {
  try {
    return JSON.parse(localStorage.getItem(convKey(id)) || 'null') as Conversation | null
  } catch {
    return null
  }
}

export function selectConversation(id: string | null) {
  activeId.value = id
  activeConv.value = id ? loadConversation(id) : null
}

export function createConversation(model: string): Conversation {
  const d = readDefaults()
  const now = Date.now()
  const conv: Conversation = {
    id: `c-${now}-${Math.random().toString(36).slice(2, 8)}`,
    title: t('chat.newTitle'),
    model,
    createdAt: now,
    updatedAt: now,
    systemPrompt: d.systemPrompt,
    params: { ...d.params },
    perConv: d.perConv,
    messages: [],
  }
  persist(conv)
  selectConversation(conv.id)
  return conv
}

export function persist(conv: Conversation) {
  conv.updatedAt = Date.now()
  try {
    localStorage.setItem(convKey(conv.id), JSON.stringify(conv))
  } catch { /* non-fatal */ }
  const meta: ConvMeta = {
    id: conv.id,
    title: conv.title,
    model: conv.model,
    createdAt: conv.createdAt,
    updatedAt: conv.updatedAt,
  }
  const list = readIndex().filter((m) => m.id !== conv.id)
  list.unshift(meta)
  writeIndex(list)
  if (activeId.value === conv.id) activeConv.value = { ...conv }
}

export function deleteConversation(id: string) {
  try {
    localStorage.removeItem(convKey(id))
  } catch { /* non-fatal */ }
  writeIndex(readIndex().filter((m) => m.id !== id))
  if (activeId.value === id) {
    activeId.value = null
    activeConv.value = null
  }
}

/** Wipe ALL saved conversations (Settings → Data). Client-only, honest. */
export function clearAllConversations() {
  const ids = readIndex().map((m) => m.id)
  for (const id of ids) {
    try {
      localStorage.removeItem(convKey(id))
    } catch {
      /* non-fatal */
    }
  }
  writeIndex([])
  activeId.value = null
  activeConv.value = null
}

/** Auto-title from the first user message (only while still default). */
export function autoTitle(conv: Conversation, firstUserText: string) {
  if (conv.title === t('chat.newTitle') || !conv.title.trim()) {
    conv.title = firstUserText.replace(/\s+/g, ' ').trim().slice(0, 48) || t('chat.newTitle')
  }
}

/* ── Export as Markdown (D1) ─────────────────────────────────── */

export function exportMarkdown(conv: Conversation) {
  const fm = [
    '---',
    `model: ${JSON.stringify(conv.model)}`,
    `date: ${new Date(conv.createdAt).toISOString()}`,
    `temperature: ${conv.params.temperature}`,
    `top_p: ${conv.params.top_p}`,
    `max_tokens: ${conv.params.max_tokens}`,
    '---',
    '',
  ].join('\n')
  const body = conv.messages
    .map((m) => {
      const head =
        m.role === 'user' ? '🧑 User' : m.role === 'tool' ? `🛠️ Tool${m.name ? `: ${m.name}` : ''}` : '🤖 Assistant'
      return `## ${head}\n\n${m.content}\n`
    })
    .join('\n')
  const blob = new Blob([`# ${conv.title}\n\n${fm}\n${body}`], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${conv.title.replace(/[^\p{L}\p{N}_ -]+/gu, '').trim().slice(0, 60) || 'chat'}.md`
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 4000)
}

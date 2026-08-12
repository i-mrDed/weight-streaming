/* Agent-loop helpers for ChatPage — pure functions, no DOM/network, so the
   loop logic is unit-testable (see chat.test.ts).

   Wire format follows the OpenAI chat-completions shape used by P7.3:
   - assistant messages may carry `tool_calls: [{id, type, function:{name, arguments}}]`
   - tool results are `{role:'tool', tool_call_id, content}`
   - tool definitions are `{type:'function', function:{name, description, parameters}}`
*/
import type { ChatMsg } from '@/pages/chat/store'

/** Hard cap on agent turns (each turn = one model round-trip). Guards
    against runaway tool loops. */
export const MAX_AGENT_ITERS = 10
/** Per-call cap on tool result text fed back to the model (protects context). */
export const MAX_TOOL_RESULT_CHARS = 32_000
/** Token budget for tool-calling turns: the model needs room to emit the
    tool_calls JSON. Final answers use the conversation's own max_tokens. */
export const MAX_AGENT_TURN_TOKENS = 1024

export interface WireToolCall {
  id: string
  name: string
  arguments: string
}

export interface WireToolCallFragment {
  index?: number
  id?: string
  type?: string
  function?: { name?: string; arguments?: string }
}

/** A single chat-completions wire message. */
export interface WireMsg {
  role: string
  content: string | null
  tool_calls?: Array<{
    id: string
    type: 'function'
    function: { name: string; arguments: string }
  }>
  tool_call_id?: string
}

export interface WireToolDef {
  type: 'function'
  function: {
    name: string
    description: string
    parameters: Record<string, unknown>
  }
}

/** OpenAI streams tool_calls as fragments by index (id may come on the first
    fragment, arguments in pieces). Merge them like the server does
    (llama_server._accumulate_tool_calls). */
export function accumulateToolCalls(
  acc: WireToolCall[],
  fragments: WireToolCallFragment[] | null | undefined,
): WireToolCall[] {
  if (!fragments) return acc
  const next = [...acc]
  for (const frag of fragments) {
    const idx = frag.index ?? 0
    while (next.length <= idx) {
      next.push({ id: '', name: '', arguments: '' })
    }
    const target = next[idx]
    if (frag.id) target.id = frag.id
    if (frag.function?.name) target.name = frag.function.name
    if (frag.function?.arguments) target.arguments += frag.function.arguments
  }
  return next
}

/** Cap tool-result text sent back to the model. */
export function truncateToolResult(text: string): string {
  if (text.length <= MAX_TOOL_RESULT_CHARS) return text
  const head = text.slice(0, Math.floor(MAX_TOOL_RESULT_CHARS * 0.9))
  const tail = text.slice(-Math.floor(MAX_TOOL_RESULT_CHARS * 0.1))
  return `${head}\n… [truncated ${text.length - MAX_TOOL_RESULT_CHARS} chars] …\n${tail}`
}

/** Normalize a tool-call response (MCP CallToolResult or built-in {result})
    into a plain text string for display + model context. */
export function formatToolResult(resp: unknown): string {
  if (resp == null) return '(no result)'
  const r = resp as { result?: unknown; content?: unknown; structuredContent?: unknown }
  const payload = r.result ?? r.structuredContent ?? r.content ?? resp
  if (typeof payload === 'string') return payload
  if (Array.isArray(payload)) {
    const parts = payload
      .map((p) => {
        if (p == null) return ''
        if (typeof p === 'string') return p
        const o = p as { type?: string; text?: string }
        return o.type === 'text' && typeof o.text === 'string' ? o.text : JSON.stringify(p)
      })
      .filter(Boolean)
    return parts.join('\n')
  }
  if (typeof payload === 'object') {
    const text = (payload as { text?: unknown }).text
    if (typeof text === 'string') return text
    return JSON.stringify(payload, null, 2)
  }
  return String(payload)
}

/** Build the OpenAI wire-format messages for a turn from conversation msgs.
    `msgs` may include assistant entries with tool_calls and `tool` role
    entries with tool_call_id (agent turns); plain entries pass through. */
export function buildWireMessages(msgs: ChatMsg[]): WireMsg[] {
  const out: WireMsg[] = []
  for (const m of msgs) {
    if (m.role === 'tool') {
      out.push({ role: 'tool', content: m.content || '', tool_call_id: m.tool_call_id })
    } else if (m.role === 'assistant') {
      const wire: WireMsg = { role: 'assistant', content: m.content || null }
      if (m.tool_calls?.length) {
        wire.tool_calls = m.tool_calls.map((tc) => ({
          id: tc.id,
          type: 'function' as const,
          function: { name: tc.name, arguments: tc.arguments },
        }))
      }
      out.push(wire)
    } else {
      out.push({ role: m.role, content: m.content })
    }
  }
  return out
}

/** Namespaced wire name for an MCP tool: `<server_name>.<tool_name>`.
    The client keeps the reverse map to route calls back. */
export function toolWireName(serverName: string, toolName: string): string {
  return `${serverName}.${toolName}`
}

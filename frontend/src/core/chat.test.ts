import { describe, expect, it } from 'vitest'
import {
  MAX_TOOL_RESULT_CHARS,
  accumulateToolCalls,
  buildWireMessages,
  formatToolResult,
  toolWireName,
  truncateToolResult,
} from './chat'
import type { ChatMsg } from '@/pages/chat/store'

describe('accumulateToolCalls', () => {
  it('merges fragments by index', () => {
    const acc = accumulateToolCalls([], [
      { index: 0, id: 'call_1', type: 'function', function: { name: 'filesystem.read_file' } },
      { index: 0, function: { arguments: '{"path":' } },
      { index: 0, function: { arguments: '"C:/x"}' } },
    ])
    expect(acc).toEqual([
      { id: 'call_1', name: 'filesystem.read_file', arguments: '{"path":"C:/x"}' },
    ])
  })

  it('handles multiple parallel calls by index', () => {
    const acc = accumulateToolCalls([], [
      { index: 0, id: 'a', function: { name: 't1' } },
      { index: 1, id: 'b', function: { name: 't2' } },
      { index: 1, function: { arguments: '{}' } },
    ])
    expect(acc).toHaveLength(2)
    expect(acc[1]).toEqual({ id: 'b', name: 't2', arguments: '{}' })
  })

  it('returns acc unchanged on null fragments', () => {
    expect(accumulateToolCalls([{ id: 'x', name: 'y', arguments: '' }], null)).toHaveLength(1)
  })
})

describe('truncateToolResult', () => {
  it('passes short text through', () => {
    expect(truncateToolResult('hi')).toBe('hi')
  })
  it('truncates long text with marker + head/tail', () => {
    const long = 'a'.repeat(MAX_TOOL_RESULT_CHARS + 5000)
    const out = truncateToolResult(long)
    expect(out.length).toBeLessThan(long.length)
    expect(out).toContain('[truncated 5000 chars]')
    expect(out.startsWith('a')).toBe(true)
    expect(out.endsWith('a')).toBe(true)
  })
})

describe('formatToolResult', () => {
  it('joins MCP content array', () => {
    expect(formatToolResult({ content: [{ type: 'text', text: 'line1' }, { type: 'text', text: 'line2' }] }))
      .toBe('line1\nline2')
  })
  it('reads structuredContent object', () => {
    expect(formatToolResult({ structuredContent: { ok: true } })).toContain('"ok"')
  })
  it('prefers result wrapper (built-in)', () => {
    expect(formatToolResult({ result: 'hello' })).toBe('hello')
  })
  it('plain string pass-through', () => {
    expect(formatToolResult('plain')).toBe('plain')
  })
  it('null → (no result)', () => {
    expect(formatToolResult(null)).toBe('(no result)')
  })
})

describe('buildWireMessages', () => {
  it('passes plain user/assistant through', () => {
    const msgs: ChatMsg[] = [
      { role: 'user', content: 'hi', ts: 1 },
      { role: 'assistant', content: 'yo', ts: 2 },
    ]
    expect(buildWireMessages(msgs)).toEqual([
      { role: 'user', content: 'hi' },
      { role: 'assistant', content: 'yo' },
    ])
  })
  it('serializes assistant tool_calls + tool results', () => {
    const msgs: ChatMsg[] = [
      { role: 'user', content: 'list files', ts: 1 },
      {
        role: 'assistant',
        content: '',
        ts: 2,
        tool_calls: [{ id: 'call_9', name: 'filesystem.list_directory', arguments: '{"path":"."}' }],
      },
      { role: 'tool', content: 'a.txt', ts: 3, tool_call_id: 'call_9' },
    ]
    const wire = buildWireMessages(msgs)
    expect(wire[1]).toMatchObject({
      role: 'assistant',
      content: null,
      tool_calls: [
        { id: 'call_9', type: 'function', function: { name: 'filesystem.list_directory', arguments: '{"path":"."}' } },
      ],
    })
    expect(wire[2]).toEqual({ role: 'tool', content: 'a.txt', tool_call_id: 'call_9' })
  })
  it('empty assistant content → null content when tool_calls present', () => {
    const wire = buildWireMessages([
      { role: 'assistant', content: '', ts: 1, tool_calls: [{ id: 'c', name: 'x', arguments: '{}' }] },
    ])
    expect(wire[0].content).toBeNull()
  })
})

describe('toolWireName', () => {
  it('namespaces MCP tools by server', () => {
    expect(toolWireName('filesystem', 'read_file')).toBe('filesystem.read_file')
  })
})

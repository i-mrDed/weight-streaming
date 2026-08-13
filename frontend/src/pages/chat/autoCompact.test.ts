/* Tests for auto-compact (context-management, research/12):
   - maybeAutoCompact triggers once at AUTO_COMPACT_TURNS user turns
   - calls summarizeConversation with messages + existing summary
   - persists the summary and shows a toast; silent on failure
*/
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

describe('maybeAutoCompact', () => {
  const origFetch = globalThis.fetch

  afterEach(() => {
    globalThis.fetch = origFetch
    vi.restoreAllMocks()
  })

  function makeConv(turns: number, summary?: string) {
    const messages: Array<{ role: 'user' | 'assistant'; content: string; stopped?: boolean; ts: number }> = []
    for (let i = 0; i < turns; i++) {
      messages.push({ role: 'user', content: `u${i}`, ts: i })
      messages.push({ role: 'assistant', content: `a${i}`, ts: i + 100 })
    }
    return {
      id: 'c1', title: 't', model: 'm', createdAt: 0, updatedAt: 0,
      systemPrompt: '', perConv: false, messages, summary,
      params: { temperature: 0.7, top_p: 0.9, max_tokens: 1024 },
    }
  }

  it('skips when summary already exists', async () => {
    globalThis.fetch = vi.fn() as unknown as typeof fetch
    const { maybeAutoCompact } = await import('./autoCompact')
    const c = makeConv(20, 'existing')
    const ok = await maybeAutoCompact(c)
    expect(ok).toBe(false)
    expect(globalThis.fetch).not.toHaveBeenCalled()
  })

  it('skips below threshold turns', async () => {
    globalThis.fetch = vi.fn() as unknown as typeof fetch
    const { maybeAutoCompact } = await import('./autoCompact')
    const c = makeConv(7)
    const ok = await maybeAutoCompact(c)
    expect(ok).toBe(false)
    expect(globalThis.fetch).not.toHaveBeenCalled()
  })

  it('summarizes at threshold and persists', async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ summary: 'SUM', input_tokens_estimate: 10, summary_tokens_estimate: 2, model: 'm' }),
    })) as unknown as typeof fetch

    const { maybeAutoCompact } = await import('./autoCompact')
    const c = makeConv(8)
    const ok = await maybeAutoCompact(c)
    expect(ok).toBe(true)
    expect(c.summary).toBe('SUM')
    const call = vi.mocked(globalThis.fetch).mock.calls[0]
    expect(call[0]).toContain('/v1/conversation/summarize')
    const body = JSON.parse(String(call[1]?.body))
    expect(body.messages.length).toBeGreaterThan(0)
  })

  it('silent on failure', async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: false, status: 500, json: async () => ({}),
    })) as unknown as typeof fetch

    const { maybeAutoCompact } = await import('./autoCompact')
    const c = makeConv(8)
    const ok = await maybeAutoCompact(c)
    expect(ok).toBe(false)
    expect(c.summary).toBeUndefined()
  })
})
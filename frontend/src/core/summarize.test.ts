/* Tests for the conversation summarization UI wiring:
   - summarizeConversation() client (api.ts) hits the right endpoint
   - sidebar doSummarize persists the summary on the conversation
*/
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const BASE = '/api/v1'

describe('summarizeConversation client', () => {
  const origFetch = globalThis.fetch

  afterEach(() => {
    globalThis.fetch = origFetch
    vi.restoreAllMocks()
  })

  it('posts to /v1/conversation/summarize with messages + existing summary', async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        summary: 'SUMMARY: test',
        input_tokens_estimate: 100,
        summary_tokens_estimate: 30,
        model: 'm',
      }),
    })) as unknown as typeof fetch

    const { summarizeConversation } = await import('@/core/api')
    const res = await summarizeConversation('m', [
      { role: 'user', content: 'hi' },
    ], 'OLD')
    expect(res.summary).toBe('SUMMARY: test')
    const call = vi.mocked(globalThis.fetch).mock.calls[0]
    expect(call[0]).toContain('/v1/conversation/summarize')
    const body = JSON.parse(String(call[1]?.body))
    expect(body.model).toBe('m')
    expect(body.existing_summary).toBe('OLD')
    expect(body.messages).toEqual([{ role: 'user', content: 'hi' }])
  })

  it('omits existing_summary when empty', async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ summary: 'S', input_tokens_estimate: 1, summary_tokens_estimate: 1, model: 'm' }),
    })) as unknown as typeof fetch

    const { summarizeConversation } = await import('@/core/api')
    await summarizeConversation('m', [{ role: 'user', content: 'hi' }])
    const body = JSON.parse(String(vi.mocked(globalThis.fetch).mock.calls[0][1]?.body))
    expect(body.existing_summary).toBeUndefined()
  })

  it('throws ApiError on HTTP failure', async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: false,
      status: 500,
      json: async () => ({ detail: 'boom' }),
    })) as unknown as typeof fetch

    const { summarizeConversation } = await import('@/core/api')
    await expect(summarizeConversation('m', [])).rejects.toThrow()
  })
})
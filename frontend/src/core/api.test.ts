/* Unit tests for core/api.ts — the API client used by every page.
   Covers the B1 auth wiring (WS_API_TOKEN → Bearer header on JSON + SSE),
   the token store, and the network/http error taxonomy. fetch and
   localStorage are stubbed; no server needed.
   Run:  cd frontend && npx vitest run src/core/api.test.ts
*/
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, apiJSON, authHeaders, setApiToken, sseRequest } from './api'

function makeStorage(): Storage {
  const map = new Map<string, string>()
  return {
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => void map.set(k, v),
    removeItem: (k: string) => void map.delete(k),
    clear: () => map.clear(),
    key: (i: number) => [...map.keys()][i] ?? null,
    get length() {
      return map.size
    },
  } as Storage
}

function mockFetchOnce(impl: (url: string, init?: RequestInit) => Promise<Response>) {
  const fn = vi.fn(impl)
  vi.stubGlobal('fetch', fn)
  return fn
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('authHeaders', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('returns no auth header when no token is stored', () => {
    vi.stubGlobal('localStorage', makeStorage())
    expect(authHeaders()).toEqual({})
  })

  it('returns a Bearer header when a token is stored', () => {
    const s = makeStorage()
    s.setItem('ws-api-token', 'tok-123')
    vi.stubGlobal('localStorage', s)
    expect(authHeaders()).toEqual({ Authorization: 'Bearer tok-123' })
  })

  it('survives localStorage being unavailable', () => {
    vi.stubGlobal('localStorage', undefined)
    expect(authHeaders()).toEqual({})
  })
})

describe('setApiToken', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('trims and stores the token', () => {
    const s = makeStorage()
    vi.stubGlobal('localStorage', s)
    setApiToken('  abc  ')
    expect(s.getItem('ws-api-token')).toBe('abc')
  })

  it('removes the token when the value is empty', () => {
    const s = makeStorage()
    s.setItem('ws-api-token', 'abc')
    vi.stubGlobal('localStorage', s)
    setApiToken('   ')
    expect(s.getItem('ws-api-token')).toBeNull()
  })
})

describe('apiJSON', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('attaches the Bearer header when a token is set', async () => {
    const s = makeStorage()
    s.setItem('ws-api-token', 'tok-9')
    vi.stubGlobal('localStorage', s)
    const fetchMock = mockFetchOnce(async (url, init) => {
      expect(url).toBe('/v1/models')
      expect(init?.headers).toMatchObject({ Authorization: 'Bearer tok-9' })
      return jsonResponse([{ id: 'm' }])
    })
    const out = await apiJSON<{ id: string }[]>('/v1/models')
    expect(out).toEqual([{ id: 'm' }])
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('adds Content-Type: application/json only when a body is present', async () => {
    vi.stubGlobal('localStorage', makeStorage())
    const fetchMock = mockFetchOnce(async (_url, init) => {
      expect(init?.headers).not.toHaveProperty('Content-Type')
      return jsonResponse({ ok: true })
    })
    await apiJSON('/v1/assistants')
    expect(fetchMock).toHaveBeenCalledWith(
      '/v1/assistants',
      expect.not.objectContaining({ body: expect.anything() }),
    )
  })

  it('sends body + Content-Type + auth on POST', async () => {
    const s = makeStorage()
    s.setItem('ws-api-token', 'tok-x')
    vi.stubGlobal('localStorage', s)
    const fetchMock = mockFetchOnce(async (_url, init) => {
      expect(init?.method).toBe('POST')
      expect(init?.headers).toMatchObject({
        'Content-Type': 'application/json',
        Authorization: 'Bearer tok-x',
      })
      expect(init?.body).toBe('{"name":"a"}')
      return jsonResponse({ id: 'a1' })
    })
    await apiJSON('/v1/assistants', { method: 'POST', body: JSON.stringify({ name: 'a' }) })
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('throws ApiError http with status + parsed detail on non-ok', async () => {
    vi.stubGlobal('localStorage', makeStorage())
    mockFetchOnce(async () => jsonResponse({ detail: 'model not found' }, 404))
    const err = (await apiJSON('/v1/models/load', { method: 'POST', body: '{}' }).catch((e) => e)) as ApiError
    expect(err).toBeInstanceOf(ApiError)
    expect(err.kind).toBe('http')
    expect(err.status).toBe(404)
    expect(err.detail).toBe('model not found')
  })

  it('keeps detail undefined when the error body is not JSON', async () => {
    vi.stubGlobal('localStorage', makeStorage())
    mockFetchOnce(async () => new Response('oops', { status: 500 }))
    const err = (await apiJSON('/v1/whatever').catch((e) => e)) as ApiError
    expect(err).toBeInstanceOf(ApiError)
    expect(err.kind).toBe('http')
    expect(err.status).toBe(500)
    expect(err.detail).toBeUndefined()
  })

  it('wraps network failures as ApiError network', async () => {
    vi.stubGlobal('localStorage', makeStorage())
    mockFetchOnce(async () => {
      throw new TypeError('Failed to fetch')
    })
    const err = (await apiJSON('/v1/models').catch((e) => e)) as ApiError
    expect(err).toBeInstanceOf(ApiError)
    expect(err.kind).toBe('network')
  })
})

describe('sseRequest', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('POSTs with Content-Type + auth header', () => {
    const s = makeStorage()
    s.setItem('ws-api-token', 'tok-sse')
    vi.stubGlobal('localStorage', s)
    mockFetchOnce(async () => new Response('ok'))
    const { response } = sseRequest('/v1/generate', { prompt: 'hi' })
    expect(response).toBeInstanceOf(Promise)
    const fn = vi.mocked(fetch)
    const [url, init] = fn.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/v1/generate')
    expect(init.method).toBe('POST')
    expect(init.headers).toMatchObject({
      'Content-Type': 'application/json',
      Authorization: 'Bearer tok-sse',
    })
    expect(JSON.parse(String(init.body))).toEqual({ prompt: 'hi' })
  })

  it('abort() aborts the underlying request', async () => {
    vi.stubGlobal('localStorage', makeStorage())
    let aborted = false
    mockFetchOnce(async (_url, init) => {
      await new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => {
          aborted = true
          reject(new DOMException('aborted', 'AbortError'))
        })
      })
      throw new Error('unreachable')
    })
    const { response, abort } = sseRequest('/v1/generate', {})
    abort()
    await expect(response).rejects.toThrow()
    expect(aborted).toBe(true)
  })
})

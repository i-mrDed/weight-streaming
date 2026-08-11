/* Unit tests for core/models.ts — the load-form data path added for the
   Models page extra-args field (2026-08-11):
   - mtpDraftArgs(): auto-wire MTP draft flags from scan results (the rule
     shared by the load form and the tier pin), pure + offline.
   - loadModel(): forwards extra_args verbatim in the POST body.
   No server, no DOM — fetch/localStorage stubbed.
   Run:  cd frontend && npx vitest run src/core/models.test.ts
*/
import { afterEach, describe, expect, it, vi } from 'vitest'

import { loadModel, mtpDraftArgs, type ScanModel } from './models'

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

const BASE_DIR = 'C:/models/Gemma4-12B-QAT'

function scanModel(name: string, dir = BASE_DIR, path?: string): ScanModel {
  return {
    path: path ?? `${dir}/${name}`,
    name,
    size_bytes: 1_000_000,
    size_gb: 1,
    directory: dir,
    architecture: 'gemma4',
    quant: name.match(/Q(4|8)_0/i)?.[0] ?? 'Q4_K_M',
    may_need_upgrade: false,
  }
}

describe('mtpDraftArgs', () => {
  it('wires draft-mtp flags when the model has an MTP sibling draft', () => {
    const main = scanModel('gemma-4-12B-it-qat-UD-Q4_K_XL.gguf')
    const draft = scanModel(
      'mtp-gemma-4-12B-it-Q8_0.gguf',
      `${BASE_DIR}/MTP`,
      `${BASE_DIR}/MTP/mtp-gemma-4-12B-it-Q8_0.gguf`,
    )
    const args = mtpDraftArgs(main.path, [main, draft])
    expect(args).toBe(
      '--spec-type draft-mtp --spec-draft-model C:/models/Gemma4-12B-QAT/MTP/mtp-gemma-4-12B-it-Q8_0.gguf --spec-draft-n-max 2',
    )
  })

  it('returns "" when no MTP sibling exists', () => {
    const main = scanModel('gemma-4-12B-it-qat-UD-Q4_K_XL.gguf')
    const other = scanModel('gemma-4-12B-it-qat-UD-Q4_K_XL.gguf', 'D:/elsewhere')
    expect(mtpDraftArgs(main.path, [main, other])).toBe('')
  })

  it('ignores a draft-looking file NOT under the MTP/ subdir', () => {
    const main = scanModel('gemma-4-12B-it-qat-UD-Q4_K_XL.gguf')
    // Same directory as the main model — must NOT be treated as a draft.
    const notInMtp = scanModel('mtp-gemma-4-12B-it-Q8_0.gguf')
    expect(mtpDraftArgs(main.path, [main, notInMtp])).toBe('')
  })

  it('returns "" for an empty path or no scan results', () => {
    expect(mtpDraftArgs('', null)).toBe('')
    expect(mtpDraftArgs('C:/x.gguf', null)).toBe('')
  })
})

describe('loadModel', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('forwards extra_args verbatim in the POST body', async () => {
    vi.stubGlobal('localStorage', makeStorage())
    const fetchMock = mockFetchOnce(async (_url, init) => {
      expect(init?.method).toBe('POST')
      const body = JSON.parse(String(init?.body))
      expect(body.extra_args).toBe('--spec-type draft-mtp --spec-draft-model C:/d.gguf --spec-draft-n-max 2')
      return jsonResponse({ status: 'loaded', model_id: 'm' })
    })
    await loadModel({
      model_id: 'm',
      model_path: 'C:/model.gguf',
      buffer_mb: 64,
      n_ctx: 2048,
      extra_args: '--spec-type draft-mtp --spec-draft-model C:/d.gguf --spec-draft-n-max 2',
    })
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('omits extra_args from the body when empty', async () => {
    vi.stubGlobal('localStorage', makeStorage())
    const fetchMock = mockFetchOnce(async (_url, init) => {
      const body = JSON.parse(String(init?.body))
      expect(body).not.toHaveProperty('extra_args')
      return jsonResponse({ status: 'loaded', model_id: 'm' })
    })
    await loadModel({ model_id: 'm', model_path: 'C:/model.gguf', buffer_mb: 64, n_ctx: 2048 })
    expect(fetchMock).toHaveBeenCalledOnce()
  })
})

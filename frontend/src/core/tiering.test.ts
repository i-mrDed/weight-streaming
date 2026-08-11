/* Unit tests for core/tiering.ts setTier() — the Models-page tier pin.
   Covers the EXP-023 per-tier n_ctx/max_tokens survival rule: a re-pin
   must NOT silently reset the tier's context window / output budget
   (the pin UI has no fields for them), while a different-model pin must
   still clear stale MTP draft args (would crash the spawn otherwise).
   Only the network boundary (apiJSON) is mocked — setTier and the
   fetch/save helpers run their REAL code, so a regression in either is
   caught here. No server, no DOM.
   Run:  cd frontend && npx vitest run src/core/tiering.test.ts
*/
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiJSON } from './api'
import { setTier, type TieringConfig } from './tiering'

vi.mock('./api', async (importOriginal) => {
  const mod = await importOriginal<typeof import('./api')>()
  return {
    ...mod,
    apiJSON: vi.fn(),
  }
})

const FAST = 'C:/models/Gemma4-12B-QAT/gemma-4-12B-it-qat-UD-Q4_K_XL.gguf'
const FAST_DRAFT = 'C:/models/Gemma4-12B-QAT/MTP/mtp-gemma-4-12B-it-Q8_0.gguf'
const OTHER = 'D:/models/qwen-7b-q4_k_m.gguf'

function makeConfig(over: Partial<TieringConfig> = {}): TieringConfig {
  return {
    enabled: true,
    max_prompt_chars: 2000,
    reasoning_quality: 'high',
    fast: {
      model_id: 'gemma-4-12b-qat-mtp',
      model_path: FAST,
      extra_args: `-fa on --spec-type draft-mtp --spec-draft-model ${FAST_DRAFT} --spec-draft-n-max 2`,
      n_ctx: 8192,
      max_tokens: 2048,
    },
    quality: {
      model_id: 'gemma-4-26b-qat-mtp',
      model_path: 'C:/models/Gemma4-26B-A4B-QAT/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf',
      extra_args: '-fa on',
      n_ctx: 4096,
      max_tokens: 8192,
    },
    ...over,
  }
}

const mockedApi = vi.mocked(apiJSON)

/** The config the test's PUT would persist — echoed back by the fake API. */
function putBody(): TieringConfig {
  const call = mockedApi.mock.calls.find(([, init]) => init?.method === 'PUT')
  expect(call, 'expected a PUT /v1/tiering/config call').toBeDefined()
  return JSON.parse(String(call?.[1]?.body)) as TieringConfig
}

beforeEach(() => {
  vi.clearAllMocks()
  // Fake server: GET returns the current config; PUT echoes the body back
  // as the saved config (matching the real resolve_state round-trip shape).
  mockedApi.mockImplementation(async (path, init) => {
    if (init?.method === 'PUT') {
      return { status: 'saved', config: JSON.parse(String(init.body)) }
    }
    return { config: makeConfig(), problems: [] }
  })
})

describe('setTier', () => {
  it('keeps the tier n_ctx/max_tokens + extra_args on a same-model re-pin', async () => {
    await setTier('fast', { model_id: 'gemma-4-12b-qat-mtp', model_path: FAST })

    const saved = putBody()
    expect(saved.fast.n_ctx).toBe(8192)
    expect(saved.fast.max_tokens).toBe(2048)
    expect(saved.fast.extra_args).toContain('--spec-type draft-mtp')
    // The OTHER tier is untouched.
    expect(saved.quality.n_ctx).toBe(4096)
    expect(saved.quality.max_tokens).toBe(8192)
  })

  it('keeps n_ctx/max_tokens but clears stale extra_args on a different-model pin', async () => {
    await setTier('fast', { model_id: 'qwen-7b', model_path: OTHER })

    const saved = putBody()
    // Gemma MTP args must NOT leak onto a Qwen load...
    expect(saved.fast.extra_args).toBe('')
    // ...but the tier's context/budget profile survives the swap.
    expect(saved.fast.n_ctx).toBe(8192)
    expect(saved.fast.max_tokens).toBe(2048)
  })

  it('honors explicit n_ctx/max_tokens overrides from the caller', async () => {
    await setTier('quality', {
      model_id: 'qwen-7b',
      model_path: OTHER,
      n_ctx: 32768,
      max_tokens: 4096,
    })

    const saved = putBody()
    expect(saved.quality.n_ctx).toBe(32768)
    expect(saved.quality.max_tokens).toBe(4096)
  })

  it('preserves a null n_ctx when the existing tier has none', async () => {
    mockedApi.mockImplementation(async (path, init) => {
      if (init?.method === 'PUT') {
        return { status: 'saved', config: JSON.parse(String(init.body)) }
      }
      return {
        config: makeConfig({
          fast: { ...makeConfig().fast, n_ctx: null, max_tokens: null },
        }),
        problems: [],
      }
    })
    await setTier('fast', { model_id: 'gemma-4-12b-qat-mtp', model_path: FAST })

    const saved = putBody()
    expect(saved.fast.n_ctx).toBeNull()
    expect(saved.fast.max_tokens).toBeNull()
  })
})

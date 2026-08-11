/* Component test — Settings → Auto-tiering (TieringSection) in jsdom.
   Verifies the EXP-023 per-tier n_ctx/max_tokens fields: values load from
   the live config into the form, and editing + Save forwards them in the
   PUT payload. Only the network boundary (core/tiering, scanModels,
   toast) is mocked — the component renders for real.
   Run:  cd frontend && npx vitest run src/pages/settings/TieringSection.test.tsx
*/
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/preact'

import { TieringSection } from './TieringSection'
import { fetchTieringConfig, saveTieringConfig } from '@/core/tiering'
import { scanModels } from '@/core/models'
import { toast } from '@/components/Toast'

vi.mock('@/core/tiering', () => ({
  fetchTieringConfig: vi.fn(),
  saveTieringConfig: vi.fn(),
  previewTiering: vi.fn(),
  unpinTier: vi.fn(),
}))
vi.mock('@/core/models', () => ({ scanModels: vi.fn() }))
vi.mock('@/components/Toast', () => ({ toast: vi.fn() }))

const CONFIG = {
  enabled: true,
  max_prompt_chars: 2000,
  reasoning_quality: 'high',
  fast: {
    model_id: 'gemma-4-12b-qat-mtp',
    model_path: 'C:/models/gemma-12b.gguf',
    extra_args: '-fa on',
    n_ctx: 8192,
    max_tokens: 2048,
    file_resolved: true,
    is_default: true,
  },
  quality: {
    model_id: 'gemma-4-26b-qat-mtp',
    model_path: 'C:/models/gemma-26b.gguf',
    extra_args: '-fa on',
    n_ctx: 4096,
    max_tokens: 8192,
    file_resolved: true,
    is_default: true,
  },
}

const mockedFetch = vi.mocked(fetchTieringConfig)
const mockedSave = vi.mocked(saveTieringConfig)

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

async function renderTiering() {
  mockedFetch.mockResolvedValue({ config: CONFIG, problems: [] })
  mockedSave.mockImplementation(async (cfg) => ({ status: 'saved', config: cfg }))
  vi.mocked(scanModels).mockResolvedValue({ models: [], total: 0 })
  render(<TieringSection />)
  // Wait for the async load() to populate the form.
  await waitFor(() => expect(screen.getAllByLabelText('Context (CTX)').length).toBe(2))
}

describe('TieringSection per-tier n_ctx/max_tokens (EXP-023)', () => {
  it('loads the tier n_ctx/max_tokens from the live config', async () => {
    await renderTiering()

    const ctx = screen.getAllByLabelText('Context (CTX)')
    expect((ctx[0] as HTMLInputElement).value).toBe('8192') // fast
    expect((ctx[1] as HTMLInputElement).value).toBe('4096') // quality
    const tokens = screen.getAllByLabelText('Max tokens')
    expect((tokens[0] as HTMLInputElement).value).toBe('2048')
    expect((tokens[1] as HTMLInputElement).value).toBe('8192')
    // Hint explains the empty = server-default behavior (one per tier).
    expect(screen.getAllByText(/Per-tier load options \(EXP-023\)/).length).toBe(2)
  })

  it('editing fast n_ctx + Save forwards the new value in the PUT payload', async () => {
    await renderTiering()

    const fastCtx = screen.getAllByLabelText('Context (CTX)')[0] as HTMLInputElement
    fireEvent.input(fastCtx, { target: { value: '16384' } })
    // The other tier is untouched.
    const tokens = screen.getAllByLabelText('Max tokens')
    fireEvent.input(tokens[0] as HTMLInputElement, { target: { value: '4096' } })

    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(mockedSave).toHaveBeenCalled())
    const payload = mockedSave.mock.calls[0][0]
    expect(payload.fast.n_ctx).toBe(16384)
    expect(payload.fast.max_tokens).toBe(4096)
    expect(payload.quality.n_ctx).toBe(4096) // untouched
    expect(payload.quality.max_tokens).toBe(8192)
  })

  it('blanking n_ctx means null (server default), not a garbage value', async () => {
    await renderTiering()

    const qualityCtx = screen.getAllByLabelText('Context (CTX)')[1] as HTMLInputElement
    fireEvent.input(qualityCtx, { target: { value: '' } })

    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(mockedSave).toHaveBeenCalled())
    const payload = mockedSave.mock.calls[0][0]
    expect(payload.quality.n_ctx).toBeNull()
    expect(payload.fast.n_ctx).toBe(8192)
  })
})

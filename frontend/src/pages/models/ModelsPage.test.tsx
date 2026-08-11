/* Component test — Models page (ModelsPage) in jsdom.
   Verifies the extra llama-server args field on the load form:
   1. typing args + Load forwards them in the /v1/models/load payload;
   2. "Use in load form" on a scan result auto-detects MTP draft flags
      (the rule shared with the tier pin).
   Network boundary mocked (core/api, core/models, core/config,
   core/tiering, store, router); the page renders for real.
   Run:  cd frontend && npx vitest run src/pages/models/ModelsPage.test.tsx
*/
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/preact'

import { ModelsPage } from './ModelsPage'
import { apiJSON } from '@/core/api'
import { fetchConfig } from '@/core/config'
import { browseFile, browseDir, fetchHardware, loadModel, scanModels } from '@/core/models'
import { setTier } from '@/core/tiering'
import { toast } from '@/components/Toast'

vi.mock('@/core/api', async (importOriginal) => {
  const mod = await importOriginal<typeof import('@/core/api')>()
  return { ...mod, apiJSON: vi.fn() }
})
vi.mock('@/core/config', () => ({ fetchConfig: vi.fn() }))
vi.mock('@/core/models', async (importOriginal) => {
  const mod = await importOriginal<typeof import('@/core/models')>()
  return {
    ...mod, // pure helpers (suggestModelId, mtpDraftArgs, …) stay real
    browseFile: vi.fn(),
    browseDir: vi.fn(),
    fetchHardware: vi.fn(),
    loadModel: vi.fn(),
    scanModels: vi.fn(),
  }
})
vi.mock('@/core/tiering', () => ({ setTier: vi.fn() }))
vi.mock('@/core/router', () => ({ navigate: vi.fn() }))
vi.mock('@/core/store', () => ({ models: { value: [] } }))
vi.mock('@/components/Toast', () => ({ toast: vi.fn() }))

const mockedApi = vi.mocked(apiJSON)
const mockedLoad = vi.mocked(loadModel)
const mockedScan = vi.mocked(scanModels)
const mockedHardware = vi.mocked(fetchHardware)

const BASE_DIR = 'C:/models/Gemma4-12B-QAT'
const DRAFT_ARGS =
  '--spec-type draft-mtp --spec-draft-model C:/models/Gemma4-12B-QAT/MTP/mtp-gemma-4-12B-it-Q8_0.gguf --spec-draft-n-max 2'

function scanModel(name: string, dir = BASE_DIR): Record<string, unknown> {
  return {
    path: `${dir}/${name}`,
    name,
    size_bytes: 6_716_356_800,
    size_gb: 6.72,
    directory: dir,
    architecture: 'gemma4',
    quant: 'Q4_K_M',
    may_need_upgrade: false,
  }
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

async function renderModels() {
  mockedApi.mockResolvedValue([]) // GET /v1/models → nothing loaded
  mockedHardware.mockResolvedValue({ gpu: null, source: 'none' })
  vi.mocked(fetchConfig).mockResolvedValue({
    config: {} as never,
    models_dirs: [],
    issues_dir: 'data/issues',
    version: '0.0.0',
  })
  vi.mocked(browseFile).mockResolvedValue({ path: null, cancelled: true })
  vi.mocked(browseDir).mockResolvedValue({ path: null, cancelled: true })
  render(<ModelsPage />)
  await waitFor(() =>
    expect(screen.getByPlaceholderText('Path to a .gguf file')).toBeTruthy())
}

describe('ModelsPage load form — extra llama-server args', () => {
  it('forwards typed extra_args in the /v1/models/load payload', async () => {
    await renderModels()

    fireEvent.input(screen.getByPlaceholderText('Path to a .gguf file'), {
      target: { value: 'C:/models/qwen-7b.gguf' },
    })
    fireEvent.input(screen.getByLabelText('Model ID'), { target: { value: 'qwen-7b' } })
    const extraArgs = screen.getByLabelText('Extra llama-server args') as HTMLInputElement
    fireEvent.input(extraArgs, { target: { value: DRAFT_ARGS } })

    fireEvent.click(screen.getByRole('button', { name: 'Load model' }))

    await waitFor(() => expect(mockedLoad).toHaveBeenCalled())
    expect(mockedLoad).toHaveBeenCalledWith(
      expect.objectContaining({
        model_id: 'qwen-7b',
        model_path: 'C:/models/qwen-7b.gguf',
        extra_args: DRAFT_ARGS,
      }),
    )
  })

  it('omits extra_args from the payload when the field is empty', async () => {
    await renderModels()

    fireEvent.input(screen.getByPlaceholderText('Path to a .gguf file'), {
      target: { value: 'C:/models/qwen-7b.gguf' },
    })
    fireEvent.input(screen.getByLabelText('Model ID'), { target: { value: 'qwen-7b' } })

    fireEvent.click(screen.getByRole('button', { name: 'Load model' }))

    await waitFor(() => expect(mockedLoad).toHaveBeenCalled())
    expect(mockedLoad.mock.calls[0][0]).toEqual(
      expect.not.objectContaining({ extra_args: expect.anything() }),
    )
  })

  it('auto-detects MTP draft args when "Use in load form" picks a Gemma model', async () => {
    await renderModels()

    const main = scanModel('gemma-4-12B-it-qat-UD-Q4_K_XL.gguf')
    const draft = scanModel(
      'mtp-gemma-4-12B-it-Q8_0.gguf',
      `${BASE_DIR}/MTP`,
    )
    // Path override for the draft (its directory differs from its parent).
    draft.path = `${BASE_DIR}/MTP/mtp-gemma-4-12B-it-Q8_0.gguf`
    mockedScan.mockResolvedValue({ models: [main, draft] as never, total: 2 })

    fireEvent.click(screen.getByRole('button', { name: 'Scan' }))
    await waitFor(() =>
      expect(screen.getAllByRole('button', { name: 'Use in load form' }).length).toBe(2))

    // Pick the MAIN model — the form must auto-wire its MTP draft.
    fireEvent.click(screen.getAllByRole('button', { name: 'Use in load form' })[0])

    await waitFor(() => {
      const extraArgs = screen.getByLabelText('Extra llama-server args') as HTMLInputElement
      expect(extraArgs.value).toContain('--spec-type draft-mtp')
      expect(extraArgs.value).toContain('mtp-gemma-4-12B-it-Q8_0.gguf')
    })

    // The auto-detected args ride along when the load is submitted.
    fireEvent.click(screen.getByRole('button', { name: 'Load model' }))
    await waitFor(() => expect(mockedLoad).toHaveBeenCalled())
    expect(mockedLoad).toHaveBeenCalledWith(
      expect.objectContaining({ extra_args: expect.stringContaining('--spec-draft-model') }),
    )
  })

  it('auto-detect leaves the field empty for a model without an MTP draft', async () => {
    await renderModels()

    const main = scanModel('qwen2-7b-instruct-q4_k_m.gguf', 'D:/models')
    mockedScan.mockResolvedValue({ models: [main] as never, total: 1 })

    fireEvent.click(screen.getByRole('button', { name: 'Scan' }))
    await waitFor(() =>
      expect(screen.getAllByRole('button', { name: 'Use in load form' }).length).toBe(1))

    fireEvent.click(screen.getAllByRole('button', { name: 'Use in load form' })[0])

    await waitFor(() => {
      const extraArgs = screen.getByLabelText('Extra llama-server args') as HTMLInputElement
      expect(extraArgs.value).toBe('')
    })
  })
})

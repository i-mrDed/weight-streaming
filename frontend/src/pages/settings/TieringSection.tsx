/* Auto-tiering settings (P8) — configure the fast/quality model pair.
   Any two GGUFs work; the shipped default is the Gemma pair proven on
   this rig (EXP-022/019). The router itself is model-agnostic. */
import { useSignal } from '@preact/signals'
import { useEffect } from 'preact/hooks'
import { Card } from '@/components/Card'
import { Button } from '@/components/Button'
import { Badge } from '@/components/Badge'
import { Segmented } from '@/components/Segmented'
import { Tip } from '@/components/Tip'
import { toast } from '@/components/Toast'
import { t } from '@/i18n'
import { scanModels, type ScanModel } from '@/core/models'
import {
  fetchTieringConfig,
  previewTiering,
  saveTieringConfig,
  unpinTier,
  type TieringConfig,
  type TieringPreviewResponse,
} from '@/core/tiering'

interface Props {
  scan: () => Promise<ScanModel[]>
}

/** Editable tier entry — the shipped default pair carries per-tier
    n_ctx/max_tokens (EXP-023); null = server default on the next route. */
interface TierFormValue {
  model_id: string
  model_path: string
  extra_args: string
  n_ctx?: number | null
  max_tokens?: number | null
}

function ModelPicker({
  label,
  value,
  models,
  resolved,
  onChange,
}: {
  label: string
  value: TierFormValue
  models: ScanModel[]
  resolved?: boolean
  onChange: (v: TierFormValue) => void
}) {
  const modelId = useSignal(value.model_id)
  const path = useSignal(value.model_path)
  const args = useSignal(value.extra_args)
  const nctx = useSignal<number | null>(value.n_ctx ?? null)
  const maxtoks = useSignal<number | null>(value.max_tokens ?? null)

  function emit() {
    onChange({
      model_id: modelId.value, model_path: path.value, extra_args: args.value,
      n_ctx: nctx.value, max_tokens: maxtoks.value,
    })
  }

  function pick(m: ScanModel) {
    modelId.value = m.name.replace(/\.gguf$/i, '').replace(/[^A-Za-z0-9._-]/g, '-').toLowerCase()
    path.value = m.path
    emit()
  }

  function parseNum(raw: string): number | null {
    const n = parseInt(raw, 10)
    return Number.isNaN(n) || n < 1 ? null : n
  }

  return (
    <div class="tier-picker">
      <div class="tier-picker__head">
        <strong>{label}</strong>
        {resolved !== undefined ? (
          resolved ? (
            <Badge tone="ok">{t('settings.tiering.resolved')}</Badge>
          ) : (
            <Badge tone="error">{t('settings.tiering.missing')}</Badge>
          )
        ) : null}
      </div>
      {models.length > 0 ? (
        <select
          class="tier-select"
          value={path.value}
          onChange={(e) => {
            const m = models.find((x) => x.path === (e.target as HTMLSelectElement).value)
            if (m) pick(m)
          }}
        >
          <option value="" disabled>{t('settings.tiering.pickPlaceholder')}</option>
          {models.map((m) => (
            <option key={m.path} value={m.path}>
              {m.name} · {m.size_gb.toFixed(1)} GB · {m.quant ?? m.architecture}
            </option>
          ))}
        </select>
      ) : (
        <p class="set-note">{t('settings.tiering.noModels')}</p>
      )}
      <input
        class="tier-input"
        type="text"
        value={modelId.value}
        placeholder={t('settings.tiering.modelId')}
        onInput={(e) => {
          modelId.value = (e.target as HTMLInputElement).value
          emit()
        }}
      />
      <input
        class="tier-input"
        type="text"
        value={path.value}
        placeholder={t('settings.tiering.pathPlaceholder')}
        onInput={(e) => {
          path.value = (e.target as HTMLInputElement).value
          emit()
        }}
      />
      <input
        class="tier-input"
        type="text"
        value={args.value}
        placeholder={t('settings.tiering.extraArgsPlaceholder')}
        onInput={(e) => {
          args.value = (e.target as HTMLInputElement).value
          emit()
        }}
      />
      <div class="tier-picker__nums">
        <label>
          {t('settings.tiering.nCtx')}
          <input
            class="tier-input tier-input--num"
            type="number"
            min={1}
            step={512}
            value={nctx.value ?? ''}
            placeholder={t('settings.tiering.nCtxPlaceholder')}
            onInput={(e) => {
              nctx.value = parseNum((e.target as HTMLInputElement).value)
              emit()
            }}
          />
        </label>
        <label>
          {t('settings.tiering.maxTokens')}
          <input
            class="tier-input tier-input--num"
            type="number"
            min={1}
            step={256}
            value={maxtoks.value ?? ''}
            placeholder={t('settings.tiering.maxTokensPlaceholder')}
            onInput={(e) => {
              maxtoks.value = parseNum((e.target as HTMLInputElement).value)
              emit()
            }}
          />
        </label>
      </div>
      <p class="set-note">{t('settings.tiering.tierNumHint')}</p>
    </div>
  )
}

export function TieringSection() {
  const cfg = useSignal<TieringConfig | null>(null)
  const models = useSignal<ScanModel[]>([])
  const loading = useSignal(true)
  const scanning = useSignal(false)
  const enabled = useSignal(true)
  const maxChars = useSignal(2000)
  const fast = useSignal<TierFormValue>({
    model_id: '', model_path: '', extra_args: '', n_ctx: null, max_tokens: null,
  })
  const quality = useSignal<TierFormValue>({
    model_id: '', model_path: '', extra_args: '', n_ctx: null, max_tokens: null,
  })
  // "Test the router" box — decides WITHOUT loading any model (server-side
  // live config, so the answer is always real).
  const previewPrompt = useSignal('')
  const previewReasoning = useSignal<'off' | 'low' | 'medium' | 'high'>('off')
  const previewing = useSignal(false)
  const previewResult = useSignal<TieringPreviewResponse | null>(null)
  const previewError = useSignal('')

  async function load() {
    loading.value = true
    try {
      const res = await fetchTieringConfig()
      const c = res.config
      cfg.value = c
      enabled.value = c.enabled
      maxChars.value = c.max_prompt_chars
      fast.value = {
        model_id: c.fast.model_id, model_path: c.fast.model_path,
        extra_args: c.fast.extra_args || '',
        n_ctx: c.fast.n_ctx ?? null, max_tokens: c.fast.max_tokens ?? null,
      }
      quality.value = {
        model_id: c.quality.model_id, model_path: c.quality.model_path,
        extra_args: c.quality.extra_args || '',
        n_ctx: c.quality.n_ctx ?? null, max_tokens: c.quality.max_tokens ?? null,
      }
    } catch (e) {
      toast('error', String(e))
    } finally {
      loading.value = false
    }
  }
  useEffect(() => { load() }, [])

  async function doScan() {
    scanning.value = true
    try {
      const res = await scanModels()
      models.value = res.models
      if (res.models.length === 0) toast('info', t('settings.tiering.noModels'))
    } catch (e) {
      toast('error', String(e))
    } finally {
      scanning.value = false
    }
  }

  async function save() {
    if (!fast.value.model_id || !fast.value.model_path ||
        !quality.value.model_id || !quality.value.model_path) {
      toast('error', t('settings.tiering.needPair'))
      return
    }
    try {
      const res = await saveTieringConfig({
        enabled: enabled.value,
        max_prompt_chars: maxChars.value,
        reasoning_quality: 'high',
        fast: fast.value,
        quality: quality.value,
      })
      cfg.value = res.config
      toast('success', t('settings.tiering.saved'))
    } catch (e) {
      toast('error', String(e))
    }
  }

  async function doPreview() {
    if (!previewPrompt.value.trim()) {
      toast('error', t('settings.tiering.previewEmpty'))
      return
    }
    previewing.value = true
    previewError.value = ''
    previewResult.value = null
    try {
      previewResult.value = await previewTiering({
        messages: [{ role: 'user', content: previewPrompt.value }],
        options: {
          reasoning_mode: previewReasoning.value === 'off' ? undefined : previewReasoning.value,
        },
      })
    } catch (e) {
      previewError.value = e instanceof Error ? e.message : String(e)
    } finally {
      previewing.value = false
    }
  }

  // Restore ONE tier to the shipped default (undo a Hub/Models pin or an
  // edit) without touching the other tier or the thresholds.
  async function resetTier(tier: 'fast' | 'quality') {
    try {
      const res = await unpinTier(tier)
      cfg.value = res.config
      const c = res.config
      if (tier === 'fast') {
        fast.value = {
          model_id: c.fast.model_id, model_path: c.fast.model_path,
          extra_args: c.fast.extra_args || '',
          n_ctx: c.fast.n_ctx ?? null, max_tokens: c.fast.max_tokens ?? null,
        }
      } else {
        quality.value = {
          model_id: c.quality.model_id, model_path: c.quality.model_path,
          extra_args: c.quality.extra_args || '',
          n_ctx: c.quality.n_ctx ?? null, max_tokens: c.quality.max_tokens ?? null,
        }
      }
      toast('success', t('settings.tiering.resetDone'))
    } catch (e) {
      toast('error', String(e))
    }
  }

  return (
    <Card class="set-card">
      <div class="set-row">
        <span>
          <strong>{t('settings.tiering.subtitle')}</strong>
          <p class="set-note">{t('settings.tiering.note')}</p>
        </span>
        <Segmented
          ariaLabel={t('settings.tiering.subtitle')}
          value={enabled.value ? 'on' : 'off'}
          onChange={(v) => (enabled.value = v === 'on')}
          options={[
            { value: 'on', label: t('common.on') },
            { value: 'off', label: t('common.off') },
          ]}
        />
      </div>

      <Tip label={t('settings.tiering.rule')} />

      {loading.value ? (
        <p class="set-note">{t('common.loading')}</p>
      ) : (
        <>
          <div class="tier-grid">
            <div class="tier-col">
              <ModelPicker
                label={`⚡ ${t('settings.tiering.fastTier')}`}
                value={fast.value}
                models={models.value}
                resolved={cfg.value?.fast.file_resolved}
                onChange={(v) => (fast.value = v)}
              />
              {cfg.value?.fast.is_default === false ? (
                <button class="tier-reset" onClick={() => void resetTier('fast')}>
                  ↺ {t('settings.tiering.reset')}
                </button>
              ) : null}
            </div>
            <div class="tier-col">
              <ModelPicker
                label={`🎯 ${t('settings.tiering.qualityTier')}`}
                value={quality.value}
                models={models.value}
                resolved={cfg.value?.quality.file_resolved}
                onChange={(v) => (quality.value = v)}
              />
              {cfg.value?.quality.is_default === false ? (
                <button class="tier-reset" onClick={() => void resetTier('quality')}>
                  ↺ {t('settings.tiering.reset')}
                </button>
              ) : null}
            </div>
          </div>

          <div class="set-row">
            <span>
              <strong>{t('settings.tiering.maxChars')}</strong>
              <p class="set-note">{t('settings.tiering.maxCharsHint')}</p>
            </span>
            <input
              class="tier-input tier-input--num"
              type="number"
              min={1}
              value={maxChars.value}
              onInput={(e) => {
                const n = parseInt((e.target as HTMLInputElement).value, 10)
                if (!Number.isNaN(n) && n > 0) maxChars.value = n
              }}
            />
          </div>

          {/* ── Test the router (decides without loading) ────────── */}
          <div class="tier-preview">
            <div class="tier-preview__head">
              <strong>{t('settings.tiering.previewTitle')}</strong>
              <span class="set-note">{t('settings.tiering.previewNote')}</span>
            </div>
            <textarea
              class="tier-preview__input"
              rows={3}
              placeholder={t('settings.tiering.previewPlaceholder')}
              value={previewPrompt.value}
              onInput={(e) => (previewPrompt.value = (e.target as HTMLTextAreaElement).value)}
            />
            <div class="tier-preview__row">
              <Segmented
                ariaLabel={t('settings.tiering.previewReasoning')}
                size="sm"
                value={previewReasoning.value}
                onChange={(v) => (previewReasoning.value = v as 'off' | 'low' | 'medium' | 'high')}
                options={['off', 'low', 'medium', 'high'].map((v) => ({ value: v, label: v }))}
              />
              <Button
                variant="soft"
                size="sm"
                loading={previewing.value}
                onClick={() => void doPreview()}
                disabled={!previewPrompt.value.trim()}
              >
                ⚡ {t('settings.tiering.previewGo')}
              </Button>
            </div>
            {previewResult.value ? (
              <div class={`tier-preview__result tier-preview__result--${previewResult.value.tier}`}>
                <strong>
                  {previewResult.value.tier === 'fast' ? '⚡' : '🎯'} {t('settings.tiering.previewTier_' + previewResult.value.tier)}
                </strong>
                <span class="set-note">
                  {previewResult.value.reason} · {previewResult.value.model_id}
                </span>
              </div>
            ) : null}
            {previewError.value ? (
              <p class="tier-preview__error">{previewError.value}</p>
            ) : null}
          </div>

          <div class="set-actions">
            <Button variant="soft" size="sm" onClick={doScan} disabled={scanning.value}>
              {scanning.value ? t('common.loading') : t('settings.tiering.scan')}
            </Button>
            <Button variant="primary" size="sm" onClick={save}>
              {t('common.save')}
            </Button>
          </div>
        </>
      )}
    </Card>
  )
}



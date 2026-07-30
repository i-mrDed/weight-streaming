/* Parameter drawer (spec §9.2): temperature / top-p / max_tokens sliders,
   preset chips, system-prompt textarea + preset chips (4 built-in + saved
   custom), per-conversation toggle. Reuses the QA-verified Drawer. */
import { useState } from 'preact/hooks'
import { Plus, Trash2 } from 'lucide-preact'
import { Drawer } from '@/components/Drawer'
import { Button } from '@/components/Button'
import { Badge } from '@/components/Badge'
import { toast } from '@/components/Toast'
import { Segmented } from '@/components/Segmented'
import { t, fmtNumber } from '@/i18n'
import type { Conversation } from './store'
import { writeDefaults } from './store'
import { BUILTIN_PRESETS, builtinPrompt, PARAM_PRESETS, customPresets, addCustomPreset, removeCustomPreset } from './presets'

interface Props {
  open: boolean
  onClose: () => void
  conv: Conversation | null
  /** mutate + persist the conversation */
  onChange: (mutate: (c: Conversation) => void) => void
}

export function ParamDrawer({ open, onClose, conv, onChange }: Props) {
  const [presetName, setPresetName] = useState('')

  if (!conv) return null
  const p = conv.params

  const setParam = (patch: Partial<typeof p>) =>
    onChange((c) => {
      c.params = { ...c.params, ...patch }
      if (!c.perConv) writeDefaults({ params: c.params, systemPrompt: c.systemPrompt, perConv: c.perConv })
    })

  return (
    <Drawer open={open} onClose={onClose} title={t('chat.drawer.title')} width={400}>
      <div class="params">
        <label class="params__perconv">
          <input
            type="checkbox"
            checked={conv.perConv}
            onChange={(e) =>
              onChange((c) => {
                c.perConv = (e.target as HTMLInputElement).checked
                if (!c.perConv) writeDefaults({ params: c.params, systemPrompt: c.systemPrompt, perConv: c.perConv })
              })
            }
          />
          {t('chat.drawer.perConv')}
        </label>

        <div class="params__chips">
          {PARAM_PRESETS.map((pp) => (
            <button key={pp.key} class="chip" onClick={() => setParam({ ...pp.params })}>
              {t(`chat.drawer.preset.${pp.key}`)}
            </button>
          ))}
        </div>

        <div class="params__field">
          <div class="params__label">
            <span>{t('chat.drawer.temperature')}</span>
            <b class="tnum">{fmtNumber(p.temperature, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</b>
          </div>
          <input
            type="range"
            min={0}
            max={2}
            step={0.05}
            value={p.temperature}
            onInput={(e) => setParam({ temperature: Number((e.target as HTMLInputElement).value) })}
            aria-label={t('chat.drawer.temperature')}
          />
        </div>

        <div class="params__field">
          <div class="params__label">
            <span>{t('chat.drawer.topP')}</span>
            <b class="tnum">{fmtNumber(p.top_p, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</b>
          </div>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={p.top_p}
            onInput={(e) => setParam({ top_p: Number((e.target as HTMLInputElement).value) })}
            aria-label={t('chat.drawer.topP')}
          />
        </div>

        <div class="params__field">
          <div class="params__label">
            <span>{t('chat.drawer.maxTokens')}</span>
            <b class="tnum">{fmtNumber(p.max_tokens)}</b>
          </div>
          <input
            type="range"
            min={16}
            max={8192}
            step={16}
            value={p.max_tokens}
            onInput={(e) => setParam({ max_tokens: Number((e.target as HTMLInputElement).value) })}
            aria-label={t('chat.drawer.maxTokens')}
          />
        </div>

        <div class="params__sep" />

        <div class="params__label">
          <span>{t('chat.drawer.system')}</span>
        </div>
        <div class="params__chips params__chips--wrap">
          {BUILTIN_PRESETS.map((sp) => (
            <button
              key={sp.key}
              class="chip"
              title={builtinPrompt(sp.key)}
              onClick={() => onChange((c) => {
                c.systemPrompt = builtinPrompt(sp.key)
                if (!c.perConv) writeDefaults({ params: c.params, systemPrompt: c.systemPrompt, perConv: c.perConv })
              })}
            >
              <span aria-hidden="true">{sp.emoji}</span> {t(`chat.presets.${sp.key}.name`)}
            </button>
          ))}
          {customPresets.value.map((cp) => (
            <span key={cp.name} class="chip chip--custom">
              <button
                class="chip__btn"
                title={cp.text}
                onClick={() => onChange((c) => {
                  c.systemPrompt = cp.text
                  if (!c.perConv) writeDefaults({ params: c.params, systemPrompt: c.systemPrompt, perConv: c.perConv })
                })}
              >
                ⭐ {cp.name}
              </button>
              <button class="chip__x" aria-label={t('chat.drawer.presetDelete')} onClick={() => removeCustomPreset(cp.name)}>
                <Trash2 size={11} />
              </button>
            </span>
          ))}
        </div>

        <textarea
          class="md-input params__system"
          rows={6}
          placeholder={t('chat.drawer.systemPlaceholder')}
          value={conv.systemPrompt}
          onInput={(e) => {
            const v = (e.target as HTMLTextAreaElement).value
            onChange((c) => {
              c.systemPrompt = v
              if (!c.perConv) writeDefaults({ params: c.params, systemPrompt: c.systemPrompt, perConv: c.perConv })
            })
          }}
          aria-label={t('chat.drawer.system')}
        />

        <div class="params__savepreset">
          <input
            class="md-input"
            type="text"
            placeholder={t('chat.drawer.presetName')}
            value={presetName}
            onInput={(e) => setPresetName((e.target as HTMLInputElement).value)}
            aria-label={t('chat.drawer.presetName')}
          />
          <Button
            variant="soft"
            size="sm"
            disabled={!presetName.trim() || !conv.systemPrompt.trim()}
            onClick={() => {
              addCustomPreset(presetName.trim(), conv.systemPrompt)
              setPresetName('')
              toast('success', t('chat.drawer.presetSaved'))
            }}
          >
            <Plus size={13} aria-hidden="true" /> {t('chat.drawer.presetSave')}
          </Button>
        </div>

        <div class="params__foot">
          <Badge tone="neutral">{t('chat.drawer.storedLocal')}</Badge>
        </div>
      </div>
    </Drawer>
  )
}

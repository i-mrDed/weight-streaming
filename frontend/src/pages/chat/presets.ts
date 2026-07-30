/* System-prompt presets — 4 built-ins (legacy set) + custom presets saved
   to localStorage. Built-in prompt texts are i18n keys (translated). */
import { signal } from '@preact/signals'
import { t } from '@/i18n'

export const BUILTIN_PRESETS = [
  { key: 'coding', emoji: '💻' },
  { key: 'writing', emoji: '✍️' },
  { key: 'analyst', emoji: '📈' },
  { key: 'concise', emoji: '⚡' },
] as const

export type BuiltinPresetKey = (typeof BUILTIN_PRESETS)[number]['key']

export function builtinPrompt(key: BuiltinPresetKey): string {
  return t(`chat.presets.${key}.text`)
}

export interface CustomPreset {
  name: string
  text: string
}

const CUSTOM_KEY = 'ws-chat-custom-presets-v1'

export const customPresets = signal<CustomPreset[]>(read())

function read(): CustomPreset[] {
  try {
    const raw = JSON.parse(localStorage.getItem(CUSTOM_KEY) || '[]')
    return Array.isArray(raw) ? raw : []
  } catch {
    return []
  }
}

function write(list: CustomPreset[]) {
  customPresets.value = list
  try {
    localStorage.setItem(CUSTOM_KEY, JSON.stringify(list))
  } catch { /* non-fatal */ }
}

export function addCustomPreset(name: string, text: string) {
  const list = read().filter((p) => p.name !== name)
  list.push({ name, text })
  write(list)
}

export function removeCustomPreset(name: string) {
  write(read().filter((p) => p.name !== name))
}

/* Param slider chips */
export const PARAM_PRESETS = [
  { key: 'precise', params: { temperature: 0.2, top_p: 0.9, max_tokens: 512 } },
  { key: 'balanced', params: { temperature: 0.7, top_p: 0.95, max_tokens: 1024 } },
  { key: 'creative', params: { temperature: 1.1, top_p: 0.98, max_tokens: 2048 } },
] as const

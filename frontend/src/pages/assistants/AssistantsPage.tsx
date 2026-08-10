/* Assistants (P7.2) — chat personas: create/edit/delete/select.
   Local-first (JSON-backed), offline-friendly. Uses the /v1/assistants API. */
import { useSignal } from '@preact/signals'
import { useEffect } from 'preact/hooks'
import { Card } from '@/components/Card'
import { Button } from '@/components/Button'
import { EmptyState } from '@/components/EmptyState'
import { Dialog } from '@/components/Dialog'
import { toast } from '@/components/Toast'
import { t } from '@/i18n'
import {
  type Assistant,
  createAssistant,
  updateAssistant,
  deleteAssistant,
} from '@/core/api'
import { assistants, refreshAssistants } from '@/core/assistants'

interface EditorState {
  open: boolean
  editing: Assistant | null
  name: string
  description: string
  system_prompt: string
}

export function AssistantsPage() {
  // Shared with the Chat toolbar (core/assistants) — edits here are instantly
  // reflected there via the same signal; this page just triggers the refetch.
  // Direct value (NOT a function initializer — useSignal doesn't call those):
  // warm store (data already fetched by Chat) → skip the spinner on revisit.
  const loading = useSignal(assistants.value.length === 0)
  const editor = useSignal<EditorState>({
    open: false, editing: null, name: '', description: '', system_prompt: '',
  })

  async function load() {
    // Spinner only when the store is cold; a warm store refreshes in the
    // background and swaps in when the fetch lands (no flash on revisit).
    if (assistants.value.length === 0) loading.value = true
    try {
      await refreshAssistants()
    } catch (e) {
      toast('error', String(e))
    } finally {
      loading.value = false
    }
  }

  useEffect(() => { load() }, [])

  function openCreate() {
    editor.value = { open: true, editing: null, name: '', description: '', system_prompt: '' }
  }
  function openEdit(a: Assistant) {
    editor.value = {
      open: true, editing: a, name: a.name, description: a.description, system_prompt: a.system_prompt,
    }
  }

  async function save() {
    const e = editor.value
    if (!e.name.trim()) { toast('error', t('assistants.nameRequired')); return }
    try {
      if (e.editing) {
        await updateAssistant(e.editing.id, { name: e.name, description: e.description, system_prompt: e.system_prompt })
        toast('success', t('assistants.updated'))
      } else {
        await createAssistant({ name: e.name, description: e.description, system_prompt: e.system_prompt })
        toast('success', t('assistants.created'))
      }
      editor.value = { ...e, open: false }
      await load()
    } catch (err) {
      toast('error', String(err))
    }
  }

  async function remove(a: Assistant) {
    try {
      await deleteAssistant(a.id)
      toast('success', t('assistants.deleted'))
      await load()
    } catch (err) {
      toast('error', String(err))
    }
  }

  return (
    <div class="page">
      <header class="page__header">
        <div>
          <h1 class="page__title">{t('assistants.title')}</h1>
          <p class="page__sub">{t('assistants.subtitle')}</p>
        </div>
        <Button variant="primary" onClick={openCreate}>{t('assistants.new')}</Button>
      </header>

      {loading.value ? (
        <EmptyState emoji="💭" title={t('common.loading')} />
      ) : assistants.value.length === 0 ? (
        <EmptyState emoji="🤖" title={t('assistants.empty')} />
      ) : (
        <div class="assistants-grid">
          {assistants.value.map((a) => (
            <Card key={a.id} class="assistant-card">
              <div class="assistant-card__head">
                <span class="assistant-card__icon">🤖</span>
                <div>
                  <h3 class="assistant-card__name">{a.name}</h3>
                  {a.description ? <p class="assistant-card__desc">{a.description}</p> : null}
                </div>
              </div>
              <div class="assistant-card__prompt">
                <code>{a.system_prompt || '—'}</code>
              </div>
              <div class="assistant-card__actions">
                <Button size="sm" onClick={() => openEdit(a)}>{t('common.edit')}</Button>
                <Button size="sm" variant="danger" onClick={() => remove(a)}>{t('common.delete')}</Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Dialog
        open={editor.value.open}
        title={editor.value.editing ? t('assistants.edit') : t('assistants.new')}
        onClose={() => (editor.value = { ...editor.value, open: false })}
      >
        <div class="form">
          <label class="form__label">{t('assistants.name')}</label>
          <input class="form__input tnum" value={editor.value.name}
            onInput={(e) => (editor.value = { ...editor.value, name: (e.target as HTMLInputElement).value })} />
          <label class="form__label">{t('assistants.description')}</label>
          <input class="form__input tnum" value={editor.value.description}
            onInput={(e) => (editor.value = { ...editor.value, description: (e.target as HTMLInputElement).value })} />
          <label class="form__label">{t('assistants.systemPrompt')}</label>
          <textarea class="form__textarea tnum" rows={5} value={editor.value.system_prompt}
            onInput={(e) => (editor.value = { ...editor.value, system_prompt: (e.target as HTMLTextAreaElement).value })} />
          <div class="form__actions">
            <Button onClick={() => (editor.value = { ...editor.value, open: false })}>{t('common.cancel')}</Button>
            <Button variant="primary" onClick={save}>{t('common.save')}</Button>
          </div>
        </div>
      </Dialog>
    </div>
  )
}
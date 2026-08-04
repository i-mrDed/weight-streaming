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
  listAssistants,
  createAssistant,
  updateAssistant,
  deleteAssistant,
} from '@/core/api'

interface EditorState {
  open: boolean
  editing: Assistant | null
  name: string
  description: string
  system_prompt: string
}

export function AssistantsPage() {
  const assistants = useSignal<Assistant[]>([])
  const loading = useSignal(true)
  const editor = useSignal<EditorState>({
    open: false, editing: null, name: '', description: '', system_prompt: '',
  })

  async function load() {
    loading.value = true
    try {
      assistants.value = await listAssistants()
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
    <div class="page-wrap">
      <div class="page-header">
        <div>
          <h1 class="page-title">{t('assistants.title')}</h1>
          <p class="page-sub">{t('assistants.subtitle')}</p>
        </div>
        <Button tone="primary" onClick={openCreate}>{t('assistants.new')}</Button>
      </div>

      {loading.value ? (
        <EmptyState title={t('common.loading') as string} />
      ) : assistants.value.length === 0 ? (
        <EmptyState title={t('assistants.empty')} icon="🤖" />
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
                <Button size="sm" tone="danger" onClick={() => remove(a)}>{t('common.delete')}</Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {editor.value.open ? (
        <Dialog
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
              <Button tone="primary" onClick={save}>{t('common.save')}</Button>
            </div>
          </div>
        </Dialog>
      ) : null}
    </div>
  )
}
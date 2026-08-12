/* Conversation sidebar (spec §9.2): localStorage-backed list, grouped
   Today / Yesterday / Older, rename / delete(confirm) / export .md, model
   tag per conversation. */
import { useState } from 'preact/hooks'
import { Download, MessageSquarePlus, NotebookPen, Pencil, Plus, Trash2 } from 'lucide-preact'
import { Button } from '@/components/Button'
import { Dialog } from '@/components/Dialog'
import { Badge } from '@/components/Badge'
import { toast } from '@/components/Toast'
import {
  activeId,
  convIndex,
  deleteConversation,
  exportMarkdown,
  loadConversation,
  persist,
  selectConversation,
  type ConvMeta,
} from './store'
import { summarizeConversation } from '@/core/api'
import { t, fmtTime, locale } from '@/i18n'

function dayBucket(ts: number, now: number): 0 | 1 | 2 {
  const d = (t0: number) => {
    const x = new Date(t0)
    x.setHours(0, 0, 0, 0)
    return x.getTime()
  }
  const diff = Math.round((d(now) - d(ts)) / 86_400_000)
  if (diff <= 0) return 0
  if (diff === 1) return 1
  return 2
}

interface Props {
  onNew: () => void
}

export function ConversationSidebar({ onNew }: Props) {
  locale.value
  const [renaming, setRenaming] = useState<ConvMeta | null>(null)
  const [renameText, setRenameText] = useState('')
  const [deleting, setDeleting] = useState<ConvMeta | null>(null)
  const [summarizing, setSummarizing] = useState<string | null>(null)
  const now = Date.now()

  const groups: [string, ConvMeta[]][] = [
    [t('chat.group.today'), []],
    [t('chat.group.yesterday'), []],
    [t('chat.group.older'), []],
  ]
  for (const meta of [...convIndex.value].sort((a, b) => b.updatedAt - a.updatedAt)) {
    groups[dayBucket(meta.updatedAt, now)][1].push(meta)
  }

  const doRename = () => {
    if (!renaming) return
    const conv = loadConversation(renaming.id)
    if (conv && renameText.trim()) {
      conv.title = renameText.trim().slice(0, 60)
      persist(conv)
    }
    setRenaming(null)
  }

  const doSummarize = async (meta: ConvMeta) => {
    const conv = loadConversation(meta.id)
    if (!conv) return
    if (conv.messages.length === 0) {
      toast('info', t('chat.summary.empty'))
      return
    }
    setSummarizing(meta.id)
    try {
      const wire = conv.messages
        .filter((m) => m.content && !m.stopped)
        .map((m) => ({ role: m.role, content: m.content }))
      const res = await summarizeConversation(
        conv.model,
        wire,
        conv.summary,
      )
      conv.summary = res.summary || conv.summary
      persist(conv)
      toast('success', t('chat.summary.done'))
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      toast('error', t('chat.summary.failed'), { body: msg })
    } finally {
      setSummarizing(null)
    }
  }

  return (
    <div class="convside">
      <div class="convside__head">
        <Button variant="primary" size="sm" onClick={onNew} class="convside__new">
          <Plus size={14} aria-hidden="true" /> {t('chat.new')}
        </Button>
      </div>
      <nav class="convside__list" aria-label={t('chat.side.aria')}>
        {convIndex.value.length === 0 ? (
          <p class="convside__empty">{t('chat.side.empty')}</p>
        ) : (
          groups.map(([label, items]) =>
            items.length === 0 ? null : (
              <div key={label} class="convside__group">
                <div class="convside__label">{label}</div>
                {items.map((meta) => (
                  <div
                    key={meta.id}
                    class={`conv-item${meta.id === activeId.value ? ' is-active' : ''}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => selectConversation(meta.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        selectConversation(meta.id)
                      }
                    }}
                  >
                    <div class="conv-item__body">
                      <span class="conv-item__title">{meta.title}</span>
                      <span class="conv-item__meta">
                        <Badge tone="neutral" class="conv-item__tag">{meta.model || t('chat.noModel')}</Badge>
                        <span class="tnum">{fmtTime(meta.updatedAt)}</span>
                      </span>
                    </div>
                    <span class="conv-item__tools">
                      <button
                        class="icon-btn"
                        aria-label={t('chat.summary.label')}
                        title={t('chat.summary.label')}
                        disabled={summarizing === meta.id}
                        onClick={(e) => {
                          e.stopPropagation()
                          void doSummarize(meta)
                        }}
                      >
                        <NotebookPen size={13} />
                      </button>
                      <button
                        class="icon-btn"
                        aria-label={t('chat.side.rename')}
                        title={t('chat.side.rename')}
                        onClick={(e) => {
                          e.stopPropagation()
                          setRenaming(meta)
                          setRenameText(meta.title)
                        }}
                      >
                        <Pencil size={13} />
                      </button>
                      <button
                        class="icon-btn"
                        aria-label={t('chat.side.export')}
                        title={t('chat.side.export')}
                        onClick={(e) => {
                          e.stopPropagation()
                          const conv = loadConversation(meta.id)
                          if (conv) {
                            exportMarkdown(conv)
                            toast('success', t('chat.side.exported'))
                          }
                        }}
                      >
                        <Download size={13} />
                      </button>
                      <button
                        class="icon-btn"
                        aria-label={t('chat.side.delete')}
                        title={t('chat.side.delete')}
                        onClick={(e) => {
                          e.stopPropagation()
                          setDeleting(meta)
                        }}
                      >
                        <Trash2 size={13} />
                      </button>
                    </span>
                  </div>
                ))}
              </div>
            ),
          )
        )}
      </nav>
      <div class="convside__foot">
        <MessageSquarePlus size={13} aria-hidden="true" />
        <span class="tnum">{t('chat.side.count', { count: convIndex.value.length })}</span>
      </div>

      {/* rename dialog */}
      <Dialog
        open={renaming !== null}
        onClose={() => setRenaming(null)}
        title={t('chat.side.rename')}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setRenaming(null)}>{t('common.cancel')}</Button>
            <Button variant="primary" onClick={doRename}>{t('common.save')}</Button>
          </>
        }
      >
        <input
          class="md-input"
          type="text"
          value={renameText}
          maxLength={60}
          onInput={(e) => setRenameText((e.target as HTMLInputElement).value)}
          onKeyDown={(e) => e.key === 'Enter' && doRename()}
          aria-label={t('chat.side.rename')}
        />
      </Dialog>

      {/* delete confirm */}
      <Dialog
        open={deleting !== null}
        onClose={() => setDeleting(null)}
        title={t('chat.side.deleteTitle')}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleting(null)}>{t('common.cancel')}</Button>
            <Button
              variant="danger"
              onClick={() => {
                if (deleting) {
                  deleteConversation(deleting.id)
                  toast('info', t('chat.side.deleted'))
                }
                setDeleting(null)
              }}
            >
              {t('chat.side.delete')}
            </Button>
          </>
        }
      >
        <p class="dialog-text">{t('chat.side.deleteBody', { title: deleting?.title ?? '' })}</p>
      </Dialog>
    </div>
  )
}

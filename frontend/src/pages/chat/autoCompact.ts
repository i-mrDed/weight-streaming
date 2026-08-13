/* Auto-compact for long conversations (context-management, research/12).

   When a conversation grows past AUTO_COMPACT_TURNS user turns and has no
   running summary yet, summarize automatically so the user can keep
   chatting without losing context (the sidebar button re-runs manually).
   Fire-and-forget: never throws, never blocks the UI.
*/
import { summarizeConversation } from '@/core/api'
import { toast } from '@/components/Toast'
import { t } from '@/i18n'
import type { Conversation } from './store'

export const AUTO_COMPACT_TURNS = 8 // user+assistant pairs before auto-compact

export async function maybeAutoCompact(c: Conversation): Promise<boolean> {
  const turns = c.messages.filter((m) => m.role === 'user').length
  if (c.summary || turns < AUTO_COMPACT_TURNS) return false
  const wire = c.messages
    .filter((m) => m.content && !m.stopped)
    .map((m) => ({ role: m.role, content: m.content }))
  if (wire.length === 0) return false
  try {
    const res = await summarizeConversation(c.model, wire, c.summary)
    if (res.summary && res.summary !== c.summary) {
      c.summary = res.summary
      toast('success', t('chat.summary.auto'))
      return true
    }
  } catch {
    // silent: auto-compact is best-effort; manual button still available
  }
  return false
}
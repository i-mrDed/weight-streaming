/* Assistants store — shared by the Chat toolbar selector and the Assistants
   page. Both read the same signal, so a create/edit/delete on one page is
   instantly visible on the other without a reload. Rejected fetches rethrow
   so callers decide their own error UX (Chat: silent; Assistants: toast). */
import { signal } from '@preact/signals'
import { listAssistants, type Assistant } from './api'

export const assistants = signal<Assistant[]>([])

/** Refetch the assistant list into the shared signal. Rejects on failure. */
export async function refreshAssistants(): Promise<void> {
  assistants.value = await listAssistants()
}

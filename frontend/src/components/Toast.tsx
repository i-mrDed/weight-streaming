/* Toasts (spec §8.4) — success/info/warning/error, max 4 stacked,
   auto-dismiss 4s except errors (persist until closed), action button. */
import { signal } from '@preact/signals'
import { CheckCircle2, Info, AlertTriangle, XCircle, X } from 'lucide-preact'

export type ToastKind = 'success' | 'info' | 'warning' | 'error'

export interface ToastItem {
  id: number
  kind: ToastKind
  title: string
  body?: string
  actionLabel?: string
  onAction?: () => void
}

export const toasts = signal<ToastItem[]>([])
let seq = 1
const timers = new Map<number, number>()

export function dismissToast(id: number) {
  toasts.value = toasts.value.filter((t) => t.id !== id)
  const timer = timers.get(id)
  if (timer) {
    window.clearTimeout(timer)
    timers.delete(id)
  }
}

export function toast(
  kind: ToastKind,
  title: string,
  opts?: { body?: string; actionLabel?: string; onAction?: () => void },
) {
  const id = seq++
  const item: ToastItem = { id, kind, title, ...opts }
  toasts.value = [...toasts.value.slice(-3), item] // cap 4
  if (kind !== 'error') {
    timers.set(
      id,
      window.setTimeout(() => dismissToast(id), 4000),
    )
  }
  return id
}

const ICONS: Record<ToastKind, typeof Info> = {
  success: CheckCircle2,
  info: Info,
  warning: AlertTriangle,
  error: XCircle,
}

export function ToastViewport() {
  return (
    <div class="toast-viewport" aria-live="polite" role="status">
      {toasts.value.map((item) => {
        const Icon = ICONS[item.kind]
        return (
          <div key={item.id} class={`toast toast--${item.kind}`} role={item.kind === 'error' ? 'alert' : undefined}>
            <Icon size={17} class="toast__icon" aria-hidden="true" />
            <div class="toast__text">
              <div class="toast__title">{item.title}</div>
              {item.body ? <div class="toast__body">{item.body}</div> : null}
              {item.actionLabel ? (
                <button
                  class="toast__action"
                  onClick={() => {
                    item.onAction?.()
                    dismissToast(item.id)
                  }}
                >
                  {item.actionLabel}
                </button>
              ) : null}
            </div>
            <button class="toast__close" onClick={() => dismissToast(item.id)} aria-label="dismiss">
              <X size={14} />
            </button>
          </div>
        )
      })}
    </div>
  )
}

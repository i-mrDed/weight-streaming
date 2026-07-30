/* Modal dialog — portal, focus trap, Esc close, role=dialog (spec §7.2/§8.3) */
import { useEffect, useRef } from 'preact/hooks'
import { createPortal } from 'preact/compat'
import type { ComponentChildren } from 'preact'
import { X } from 'lucide-preact'
import { t } from '@/i18n'

interface Props {
  open: boolean
  onClose: () => void
  title?: string
  size?: 'sm' | 'md' | 'lg'
  children: ComponentChildren
  footer?: ComponentChildren
  /** hide the X close button (e.g. forced-choice dialogs) */
  hideClose?: boolean
}

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function Dialog({ open, onClose, title, size = 'md', children, footer, hideClose }: Props) {
  const panelRef = useRef<HTMLDivElement>(null)
  const restoreRef = useRef<Element | null>(null)

  useEffect(() => {
    if (!open) return
    restoreRef.current = document.activeElement
    const panel = panelRef.current
    const first = panel?.querySelector<HTMLElement>(FOCUSABLE)
    ;(first ?? panel)?.focus()

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
        return
      }
      if (e.key !== 'Tab' || !panel) return
      const items = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE))
      if (items.length === 0) return
      const firstEl = items[0]
      const lastEl = items[items.length - 1]
      if (e.shiftKey && document.activeElement === firstEl) {
        e.preventDefault()
        lastEl.focus()
      } else if (!e.shiftKey && document.activeElement === lastEl) {
        e.preventDefault()
        firstEl.focus()
      }
    }
    document.addEventListener('keydown', onKey, true)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey, true)
      document.body.style.overflow = prevOverflow
      ;(restoreRef.current as HTMLElement | null)?.focus?.()
    }
  }, [open, onClose])

  if (!open) return null

  return createPortal(
    <div class="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        ref={panelRef}
        class={`dialog dialog--${size}`}
        role="dialog"
        aria-modal="true"
        aria-label={title ?? 'dialog'}
        tabIndex={-1}
      >
        {title || !hideClose ? (
          <header class="dialog__header">
            {title ? <h2 class="dialog__title">{title}</h2> : <span />}
            {!hideClose ? (
              <button class="icon-btn" onClick={onClose} aria-label={t('common.a11y.closeDialog')}>
                <X size={16} />
              </button>
            ) : null}
          </header>
        ) : null}
        <div class="dialog__body">{children}</div>
        {footer ? <footer class="dialog__footer">{footer}</footer> : null}
      </div>
    </div>,
    document.body,
  )
}

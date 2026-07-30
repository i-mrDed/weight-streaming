/* Side drawer — right sheet on desktop, bottom sheet on mobile (spec §7.1) */
import { useEffect, useRef } from 'preact/hooks'
import { createPortal } from 'preact/compat'
import type { ComponentChildren } from 'preact'
import { X } from 'lucide-preact'
import { t } from '@/i18n'

interface Props {
  open: boolean
  onClose: () => void
  title?: string
  children: ComponentChildren
  width?: number
}

// Same focusable set as Dialog — kept local so the QA-verified Dialog stays untouched.
const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function Drawer({ open, onClose, title, children, width = 380 }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const restoreRef = useRef<Element | null>(null)

  // aria-modal contract (spec §7.2): trap Tab within the drawer and restore
  // focus to the trigger on close — mirrors Dialog.tsx. Initial focus goes to
  // the first control (or the dialog surface itself as a fallback).
  useEffect(() => {
    if (!open) return
    restoreRef.current = document.activeElement
    const panel = ref.current
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
    <div class="overlay overlay--drawer" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside
        ref={ref}
        class="drawer"
        role="dialog"
        aria-modal="true"
        aria-label={title ?? 'drawer'}
        tabIndex={-1}
        style={{ ['--drawer-width' as string]: `${width}px` }}
      >
        <header class="drawer__header">
          {title ? <h2 class="drawer__title">{title}</h2> : <span />}
          <button class="icon-btn" onClick={onClose} aria-label={t('common.a11y.closeDialog')}>
            <X size={16} />
          </button>
        </header>
        <div class="drawer__body">{children}</div>
      </aside>
    </div>,
    document.body,
  )
}

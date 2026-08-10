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
  /* CONVENTION (learned the hard way — this is the 2nd bug of its class):
     pick `side` to MATCH THE CORNER OF THE TRIGGER that opens this drawer.
     A trigger in the top-left (hamburger, the chat conversation-list toggle)
     must slide the sheet in from the LEFT; a trigger in the top-right (the
     chat params gear) slides from the RIGHT. Mismatching feels broken to the
     user. Default 'right' only suits right-corner triggers — set it
     explicitly for left-corner ones. (Centre-screen Dialog/Modal, anchored
     Menu dropdowns and Tip bubbles are NOT edge-sliding, so this rule does
     not apply to them.) When adding a future drawer (e.g. Hub in P5), apply
     this rule from the start. */
  side?: 'left' | 'right'
}

// Same focusable set as Dialog — kept local so the QA-verified Dialog stays untouched.
const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function Drawer({ open, onClose, title, children, width = 380, side = 'right' }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const restoreRef = useRef<Element | null>(null)
  // Latest-ref pattern (same as Dialog.tsx): inline onClose arrows are recreated
  // on every parent render — depending on onClose directly would re-run the
  // focus trap after each keystroke and steal focus back to the first control.
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

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
        onCloseRef.current()
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
  }, [open])

  if (!open) return null

  return createPortal(
    <div class={`overlay overlay--drawer overlay--drawer-${side}`} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside
        ref={ref}
        class={`drawer drawer--${side}`}
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

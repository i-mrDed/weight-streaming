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

export function Drawer({ open, onClose, title, children, width = 380 }: Props) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    ref.current?.focus()
    return () => document.removeEventListener('keydown', onKey)
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

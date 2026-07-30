/* Dropdown menu for navbar quick-switchers (theme / language / user).
   Click-outside + Esc close; full keyboard operation. */
import { useEffect, useRef, useState } from 'preact/hooks'
import type { ComponentChildren } from 'preact'
import { Check } from 'lucide-preact'

export interface MenuItem {
  key: string
  label: ComponentChildren
  icon?: ComponentChildren
  active?: boolean
  hint?: string
  onSelect: () => void
}

interface Props {
  ariaLabel: string
  trigger: ComponentChildren
  items: MenuItem[]
  header?: ComponentChildren
  align?: 'start' | 'end'
}

export function Menu({ ariaLabel, trigger, items, header, align = 'end' }: Props) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onPointerDown = (e: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div class="menu" ref={rootRef}>
      <button
        class="icon-btn menu__trigger"
        aria-label={ariaLabel}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {trigger}
      </button>
      {open ? (
        <div class={`menu__panel menu__panel--${align}`} role="menu">
          {header ? <div class="menu__header">{header}</div> : null}
          {items.map((item) => (
            <button
              key={item.key}
              class={`menu__item${item.active ? ' is-active' : ''}`}
              role="menuitem"
              onClick={() => {
                item.onSelect()
                setOpen(false)
              }}
            >
              {item.icon ? <span class="menu__item-icon">{item.icon}</span> : null}
              <span class="menu__item-label">{item.label}</span>
              {item.hint ? <span class="menu__item-hint">{item.hint}</span> : null}
              {item.active ? <Check size={14} class="menu__check" /> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}

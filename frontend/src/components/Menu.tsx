/* Dropdown menu for navbar quick-switchers (theme / language / user) and
   chat toolbars. WAI-ARIA menu-button pattern:
   - Arrow ↓/↑ rove between items (wrap), Home/End jump to first/last
   - Enter/Space activate the focused item (native <button> activation)
   - Esc closes and returns focus to the trigger
   - Tab closes the menu and continues in natural tab order
   - focus moves into the panel when it opens; roving tabindex marks the
     active item as the only tabbable member
   - typeahead (WAI-ARIA APG): typing letters/digits jumps to the first item
     whose key or plain-text label starts with the 500ms character buffer;
     repeated chars cycle from after the current focus. */
import { useEffect, useId, useRef, useState } from 'preact/hooks'
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
  const [activeIndex, setActiveIndex] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelId = useId()
  // Typeahead buffer (APG): chars accumulate for 500ms, then reset.
  const typeaheadRef = useRef<{ buffer: string; last: number; timer: number }>({
    buffer: '', last: 0, timer: 0,
  })

  /** Item <button> elements as they exist in the committed panel DOM. */
  const itemEls = () =>
    panelRef.current
      ? [...panelRef.current.querySelectorAll<HTMLElement>('.menu__item')]
      : []

  const resetTypeahead = () => {
    const ta = typeaheadRef.current
    window.clearTimeout(ta.timer)
    ta.buffer = ''
    ta.last = 0
  }

  const openMenu = (initialIndex?: number) => {
    const preferred = items.findIndex((i) => i.active)
    setActiveIndex(initialIndex ?? (preferred >= 0 ? preferred : 0))
    resetTypeahead()
    setOpen(true)
  }

  const closeMenu = (restoreFocus: boolean) => {
    resetTypeahead()
    setOpen(false)
    if (restoreFocus) triggerRef.current?.focus()
  }

  /** Move roving focus to item `idx` (clamped, wraps around). */
  const moveFocus = (idx: number) => {
    const n = items.length
    if (n === 0) return
    const next = ((idx % n) + n) % n
    setActiveIndex(next)
    itemEls()[next]?.focus()
  }

  // Focus the active item once the panel has mounted.
  useEffect(() => {
    if (!open) return
    itemEls()[activeIndex]?.focus()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  // Clear any pending typeahead timer on unmount (callback only mutates the
  // ref, but keeps the timer from lingering).
  useEffect(() => () => window.clearTimeout(typeaheadRef.current.timer), [])

  // Document-level: click-outside closes; Esc closes + restores focus;
  // Tab closes and continues natural tab order (so the browser's default
  // action is replaced by an explicit focus of the next/prev tabbable).
  useEffect(() => {
    if (!open) return
    const FOCUSABLE =
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    // Exclude the PANEL (its roving-tabindex items) but keep the trigger —
    // filtering by rootRef would drop the trigger too and Tab would jump to
    // the document's first tabbable instead of the element after it.
    const tabbable = () =>
      [...document.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
        (el) => el.offsetParent !== null && !panelRef.current?.contains(el),
      )
    const onPointerDown = (e: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) closeMenu(true)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        closeMenu(true)
      } else if (e.key === 'Tab') {
        e.preventDefault()
        closeMenu(false)
        const els = tabbable()
        const idx = els.indexOf(triggerRef.current!)
        const next = e.shiftKey ? els[idx - 1] : els[idx + 1]
        next?.focus()
      }
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKey)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const onPanelKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      moveFocus(activeIndex + 1)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      moveFocus(activeIndex - 1)
    } else if (e.key === 'Home') {
      e.preventDefault()
      moveFocus(0)
    } else if (e.key === 'End') {
      e.preventDefault()
      moveFocus(items.length - 1)
    } else if (e.isComposing || e.key === 'Process') {
      // IME composition → leave to native handling
    } else if (/^[\p{L}\p{N}]$/u.test(e.key) && !e.ctrlKey && !e.metaKey && !e.altKey) {
      // Letters/digits only (APG) — Space & punctuation fall through to
      // native button activation (Enter/Space) and are never swallowed.
      // Typeahead (WAI-ARIA APG): printable letter/digit accumulates into a
      // 500ms buffer; focus moves to the first item (from after the current
      // focus, wrapping) whose key or string label starts with the buffer.
      e.preventDefault()
      const n = items.length
      if (n === 0) return
      const ta = typeaheadRef.current
      const now = Date.now()
      ta.buffer = now - ta.last < 500 ? ta.buffer + e.key : e.key
      ta.last = now
      window.clearTimeout(ta.timer)
      ta.timer = window.setTimeout(() => {
        ta.buffer = ''
        ta.last = 0
      }, 500)
      const q = ta.buffer.toLowerCase()
      // APG repeated-char rule: 'aa'/'aaa' behave as a single 'a' so focus
      // cycles through items beginning with that character instead of
      // matching nothing (search-from-after-current gives the cycling).
      const allSame = q.length > 1 && q.split('').every((c) => c === q[0])
      const matchQ = allSame ? q[0] : q
      const starts = (i: number) => {
        const item = items[i]
        const hay = item.key + (typeof item.label === 'string' ? item.label : '')
        return hay.toLowerCase().startsWith(matchQ)
      }
      let idx = -1
      for (let k = activeIndex + 1; k < activeIndex + 1 + n; k++) {
        const m = ((k % n) + n) % n
        if (starts(m)) {
          idx = m
          break
        }
      }
      if (idx === -1) {
        for (let k = 0; k < n; k++) {
          if (starts(k)) {
            idx = k
            break
          }
        }
      }
      if (idx !== -1) moveFocus(idx)
    }
    // Enter/Space: native <button> activation of the focused item handles it.
    // Escape/Tab: handled by the document listener above.
  }

  const onTriggerKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      // already open but focus sits on the trigger (edge) → move into panel
      if (open) moveFocus(activeIndex + 1)
      else openMenu(0)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      if (open) moveFocus(activeIndex - 1)
      else openMenu(Math.max(0, items.length - 1))
    }
    // Enter/Space toggle via the trigger's native click.
  }

  return (
    <div class="menu" ref={rootRef}>
      <button
        ref={triggerRef}
        class="icon-btn menu__trigger"
        aria-label={ariaLabel}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => (open ? closeMenu(true) : openMenu())}
        onKeyDown={onTriggerKeyDown}
      >
        {trigger}
      </button>
      {open ? (
        <div class={`menu__panel menu__panel--${align}`} role="menu" id={panelId} ref={panelRef} onKeyDown={onPanelKeyDown}>
          {header ? <div class="menu__header">{header}</div> : null}
          {items.map((item, i) => (
            <button
              key={item.key}
              class={`menu__item${item.active ? ' is-active' : ''}`}
              role="menuitem"
              tabIndex={i === activeIndex ? 0 : -1}
              onClick={() => {
                item.onSelect()
                closeMenu(true)
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

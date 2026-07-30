/* Command Palette (spec §8.2, D1) — Ctrl+K / Cmd+K / "/" anywhere.
   Fuzzy over pages, themes, languages, actions. Keyboard-only operable. */
import { useEffect, useMemo, useRef, useState } from 'preact/hooks'
import { createPortal } from 'preact/compat'
import {
  LayoutDashboard,
  MessageSquare,
  Activity,
  Boxes,
  Bug,
  Globe,
  BookOpen,
  Settings,
  Palette,
  Languages,
  Sparkles,
  RotateCw,
  Search,
  CornerDownLeft,
} from 'lucide-preact'
import { t, availableLocales, LOCALE_META, setLocale, locale } from '@/i18n'
import { navigate } from '@/core/router'
import { THEMES } from '@/theme/registry'
import { autoMode, particlesActive, resolvedThemeId, setAutoMode, setTheme, toggleParticles } from '@/theme/manager'
import { toast } from './Toast'
import type { ComponentChildren } from 'preact'

interface Item {
  id: string
  group: string
  icon: ComponentChildren
  label: string
  hint?: string
  active?: boolean
  run: () => void
}

export function buildPaletteItems(): Item[] {
  const pageIcons: Record<string, ComponentChildren> = {
    overview: <LayoutDashboard size={16} />,
    chat: <MessageSquare size={16} />,
    stats: <Activity size={16} />,
    models: <Boxes size={16} />,
    issues: <Bug size={16} />,
    hub: <Globe size={16} />,
    docs: <BookOpen size={16} />,
    settings: <Settings size={16} />,
  }
  const items: Item[] = []
  for (const page of Object.keys(pageIcons)) {
    items.push({
      id: `page-${page}`,
      group: t('common.palette.pages'),
      icon: pageIcons[page],
      label: t(`nav.${page}`),
      run: () => navigate(page),
    })
  }
  items.push({
    id: 'theme-auto',
    group: t('common.palette.themes'),
    icon: <Sparkles size={16} />,
    label: t('settings.appearance.auto'),
    active: autoMode.value,
    run: () => setAutoMode(!autoMode.value),
  })
  for (const theme of THEMES) {
    items.push({
      id: `theme-${theme.id}`,
      group: t('common.palette.themes'),
      icon: <Palette size={16} />,
      label: t(theme.nameKey),
      active: resolvedThemeId.value === theme.id && !autoMode.value,
      run: () => {
        setTheme(theme.id)
        toast('info', t('common.toast.themeChanged', { name: t(theme.nameKey) }))
      },
    })
  }
  for (const code of availableLocales) {
    items.push({
      id: `lang-${code}`,
      group: t('common.palette.language'),
      icon: <Languages size={16} />,
      label: LOCALE_META[code]?.nativeName ?? code,
      active: locale.value === code,
      run: () => {
        setLocale(code)
        toast('info', t('common.toast.languageChanged', { name: LOCALE_META[code]?.nativeName ?? code }))
      },
    })
  }
  items.push({
    id: 'act-particles',
    group: t('common.palette.actions'),
    icon: <Sparkles size={16} />,
    label: t('common.palette.toggleParticles'),
    active: particlesActive.value,
    run: () => {
      toggleParticles()
      toast('info', t(particlesActive.value ? 'common.toast.particlesOn' : 'common.toast.particlesOff'))
    },
  })
  items.push({
    id: 'act-reload',
    group: t('common.palette.actions'),
    icon: <RotateCw size={16} />,
    label: t('common.palette.reload'),
    run: () => window.location.reload(),
  })
  return items
}

function fuzzy(query: string, label: string): boolean {
  const q = query.toLowerCase()
  const l = label.toLowerCase()
  if (l.includes(q)) return true
  // subsequence match
  let qi = 0
  for (let i = 0; i < l.length && qi < q.length; i++) {
    if (l[i] === q[qi]) qi++
  }
  return qi === q.length && q.length > 1
}

export function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [cursor, setCursor] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen((v) => !v)
        setQuery('')
        setCursor(0)
      } else if (e.key === '/' && document.activeElement === document.body) {
        e.preventDefault()
        setOpen(true)
        setQuery('')
        setCursor(0)
      }
    }
    const onOpenEvent = () => {
      setOpen(true)
      setQuery('')
      setCursor(0)
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('ws:palette', onOpenEvent)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('ws:palette', onOpenEvent)
    }
  }, [])

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  const items = useMemo(() => buildPaletteItems(), [open]) // eslint-disable-line react-hooks/exhaustive-deps
  const filtered = useMemo(
    () => (query.trim() ? items.filter((i) => fuzzy(query.trim(), i.label)) : items),
    [items, query],
  )

  useEffect(() => setCursor(0), [query])

  if (!open) return null

  const groups: { name: string; items: (Item & { flatIndex: number })[] }[] = []
  let flat = 0
  for (const item of filtered) {
    const g = groups.find((x) => x.name === item.group)
    const withIndex = { ...item, flatIndex: flat++ }
    if (g) g.items.push(withIndex)
    else groups.push({ name: item.group, items: [withIndex] })
  }

  const runItem = (item: Item) => {
    setOpen(false)
    item.run()
  }

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Escape') setOpen(false)
    else if (e.key === 'ArrowDown') {
      e.preventDefault()
      setCursor((c) => Math.min(c + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setCursor((c) => Math.max(c - 1, 0))
    } else if (e.key === 'Enter' && filtered[cursor]) {
      runItem(filtered[cursor])
    }
  }

  return createPortal(
    <div class="overlay overlay--palette" onMouseDown={(e) => e.target === e.currentTarget && setOpen(false)}>
      <div class="palette" role="dialog" aria-modal="true" aria-label={t('common.palette.title')}>
        <div class="palette__input-row">
          <Search size={16} aria-hidden="true" />
          <input
            ref={inputRef}
            class="palette__input"
            placeholder={t('common.palette.placeholder')}
            value={query}
            onInput={(e) => setQuery((e.target as HTMLInputElement).value)}
            onKeyDown={onKeyDown}
            aria-label={t('common.palette.title')}
          />
          <kbd class="kbd">esc</kbd>
        </div>
        <div class="palette__list" ref={listRef} role="listbox">
          {filtered.length === 0 ? (
            <div class="palette__empty">{t('common.palette.noResults')}</div>
          ) : (
            groups.map((g) => (
              <div key={g.name}>
                <div class="palette__group">{g.name}</div>
                {g.items.map((item) => (
                  <button
                    key={item.id}
                    class={`palette__item${item.flatIndex === cursor ? ' is-cursor' : ''}${item.active ? ' is-active' : ''}`}
                    role="option"
                    aria-selected={item.flatIndex === cursor}
                    onMouseEnter={() => setCursor(item.flatIndex)}
                    onClick={() => runItem(item)}
                  >
                    <span class="palette__item-icon">{item.icon}</span>
                    <span class="palette__item-label">{item.label}</span>
                    {item.flatIndex === cursor ? <CornerDownLeft size={13} class="palette__enter" /> : null}
                  </button>
                ))}
              </div>
            ))
          )}
        </div>
        <footer class="palette__footer">{t('common.palette.hint')}</footer>
      </div>
    </div>,
    document.body,
  )
}

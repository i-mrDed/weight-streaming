import type { ComponentChildren } from 'preact'
import { useEffect } from 'preact/hooks'
import { useSignal } from '@preact/signals'
import {
  LayoutDashboard,
  MessageSquare,
  Activity,
  Boxes,
  Bug,
  Globe,
  BookOpen,
  Settings,
  Cpu,
  House,
  ChevronDown,
} from 'lucide-preact'
import { route, navigate, type PageId } from '@/core/router'
import { t } from '@/i18n'
import { openIssueCount, primaryModel, extraModelCount } from '@/core/store'

interface NavDef {
  id: PageId
  icon: ComponentChildren
  emoji: string
}

const WORKSPACE: NavDef[] = [
  { id: 'overview', icon: <LayoutDashboard size={17} />, emoji: '🏠' },
  { id: 'chat', icon: <MessageSquare size={17} />, emoji: '💬' },
  { id: 'stats', icon: <Activity size={17} />, emoji: '📊' },
  { id: 'models', icon: <Boxes size={17} />, emoji: '🧠' },
]
const SYSTEM: NavDef[] = [
  { id: 'issues', icon: <Bug size={17} />, emoji: '🐛' },
  { id: 'hub', icon: <Globe size={17} />, emoji: '🌐' },
  { id: 'docs', icon: <BookOpen size={17} />, emoji: '📖' },
  { id: 'settings', icon: <Settings size={17} />, emoji: '⚙️' },
]

/** Settings page sections — surfaced as a sidebar submenu (P5.2). Each key
    maps to `<section id="settings-<key>">` on SettingsPage and a
    `settings.<key>.title` label. */
const SETTING_SECTIONS = [
  'appearance',
  'language',
  'chatDefaults',
  'server',
  'data',
  'diagnostics',
  'about',
] as const
export type SettingSection = (typeof SETTING_SECTIONS)[number]

export function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const current = route.value.path
  const issues = openIssueCount.value
  const activeSection = useSignal<SettingSection>('appearance')

  // Scroll-spy: while on Settings, keep the sidebar submenu in sync with the
  // section currently in view inside the page-area scroll container.
  useEffect(() => {
    if (current !== 'settings') return
    const area = document.querySelector<HTMLElement>('.page-area')
    if (!area) return
    const pick = () => {
      const top = area.scrollTop + 96
      let cur: SettingSection = SETTING_SECTIONS[0]
      for (const k of SETTING_SECTIONS) {
        const el = document.getElementById(`settings-${k}`)
        if (el && el.offsetTop <= top) cur = k
      }
      activeSection.value = cur
    }
    pick()
    area.addEventListener('scroll', pick, { passive: true })
    return () => area.removeEventListener('scroll', pick)
  }, [current])

  const goSection = (key: SettingSection) => {
    if (current !== 'settings') navigate('settings')
    // Let the Settings page mount before scrolling (a late rAF is enough).
    window.setTimeout(() => {
      document
        .getElementById(`settings-${key}`)
        ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, current !== 'settings' ? 90 : 40)
    onNavigate?.()
  }

  const item = (def: NavDef) => {
    const active = current === def.id
    const isSettings = def.id === 'settings'
    return (
      <div key={def.id} class={`nav-group${active && isSettings ? ' nav-group--open' : ''}`}>
        <button
          class={`nav-item${active ? ' is-active' : ''}`}
          aria-current={active ? 'page' : undefined}
          aria-expanded={isSettings ? active : undefined}
          title={t(`nav.${def.id}`)}
          onClick={() => {
            navigate(def.id)
            onNavigate?.()
          }}
        >
          <span class="nav-item__icon" aria-hidden="true">{def.icon}</span>
          <span class="nav-item__label">{t(`nav.${def.id}`)}</span>
          {def.id === 'issues' && issues > 0 ? <span class="nav-badge">{issues}</span> : null}
          {isSettings ? <ChevronDown size={15} class="nav-group__caret" aria-hidden="true" /> : null}
        </button>
        {isSettings && active ? (
          <div class="nav-sub" role="group" aria-label={t('nav.settings')}>
            {SETTING_SECTIONS.map((key) => (
              <button
                key={key}
                class={`nav-sub__item${activeSection.value === key ? ' is-active' : ''}`}
                aria-current={activeSection.value === key ? 'true' : undefined}
                onClick={() => goSection(key)}
              >
                {t(`settings.${key}.title`)}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    )
  }

  const model = primaryModel.value

  return (
    <div class="sidebar__inner">
      <nav class="sidebar__nav" aria-label={t('common.a11y.mainNav')}>
        <div class="sidebar__section">{t('nav.section.main')}</div>
        {WORKSPACE.map(item)}
        <div class="sidebar__section">{t('nav.section.system')}</div>
        {SYSTEM.map(item)}
      </nav>
      <div class="sidebar__footer">
        <button class="model-chip" onClick={() => { navigate('models'); onNavigate?.() }}>
          <Cpu size={14} aria-hidden="true" />
          {model ? (
            <>
              <span class="model-chip__id">{model.id}</span>
              {extraModelCount.value > 0 ? (
                <span class="model-chip__more">+{extraModelCount.value}</span>
              ) : null}
            </>
          ) : (
            <span class="model-chip__id model-chip__id--empty">{t('nav.noModelLoaded')}</span>
          )}
        </button>
      </div>
    </div>
  )
}

export function Sidebar() {
  return (
    <aside class="sidebar">
      <SidebarContent />
    </aside>
  )
}

const MOBILE_ITEMS: NavDef[] = [
  { id: 'overview', icon: <House size={19} />, emoji: '🏠' },
  { id: 'chat', icon: <MessageSquare size={19} />, emoji: '💬' },
  { id: 'stats', icon: <Activity size={19} />, emoji: '📊' },
  { id: 'models', icon: <Boxes size={19} />, emoji: '🧠' },
]

export function MobileNav({ onMore }: { onMore: () => void }) {
  const current = route.value.path
  return (
    <nav class="bottomnav" aria-label={t('common.a11y.mainNav')}>
      {MOBILE_ITEMS.map((def) => {
        const active = current === def.id
        return (
          <button
            key={def.id}
            class={`bottomnav__item${active ? ' is-active' : ''}`}
            aria-current={active ? 'page' : undefined}
            onClick={() => navigate(def.id)}
          >
            {def.icon}
            <span>{t(`nav.${def.id}`)}</span>
          </button>
        )
      })}
      <button class={`bottomnav__item${['issues', 'hub', 'docs', 'settings'].includes(current) ? ' is-active' : ''}`} onClick={onMore}>
        <Settings size={19} />
        <span>{t('nav.section.system')}</span>
      </button>
    </nav>
  )
}

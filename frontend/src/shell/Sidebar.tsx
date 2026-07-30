import type { ComponentChildren } from 'preact'
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
} from 'lucide-preact'
import { route, navigate, type PageId } from '@/core/router'
import { t, tPlural } from '@/i18n'
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

export function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const current = route.value.path
  const issues = openIssueCount.value

  const item = (def: NavDef) => {
    const active = current === def.id
    return (
      <button
        key={def.id}
        class={`nav-item${active ? ' is-active' : ''}`}
        aria-current={active ? 'page' : undefined}
        title={t(`nav.${def.id}`)}
        onClick={() => {
          navigate(def.id)
          onNavigate?.()
        }}
      >
        <span class="nav-item__icon" aria-hidden="true">{def.icon}</span>
        <span class="nav-item__label">{t(`nav.${def.id}`)}</span>
        {def.id === 'issues' && issues > 0 ? <span class="nav-badge">{issues}</span> : null}
      </button>
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

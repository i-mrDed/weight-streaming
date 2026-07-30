import { Search, Palette as PaletteIcon, Sparkles, Menu as MenuIcon } from 'lucide-preact'
import { Menu } from '@/components/Menu'
import { LogoLockup } from '@/components/Logo'
import { toast } from '@/components/Toast'
import { t, availableLocales, LOCALE_META, locale, setLocale } from '@/i18n'
import { health, serverVersion, serverHostPort, displayName } from '@/core/store'
import { navigate } from '@/core/router'
import { autoMode, resolvedThemeId, setAutoMode, setTheme } from '@/theme/manager'
import { THEMES } from '@/theme/registry'

export function Navbar({ onOpenSidebar }: { onOpenSidebar: () => void }) {
  const h = health.value
  const statusLabel =
    h === 'online'
      ? t('common.health.online')
      : h === 'offline'
        ? t('common.health.offline')
        : t('common.health.checking')
  const version = serverVersion.value

  const themeItems = [
    {
      key: 'auto',
      label: t('settings.appearance.auto'),
      icon: <Sparkles size={15} />,
      active: autoMode.value,
      hint: 'OS',
      onSelect: () => setAutoMode(!autoMode.value),
    },
    ...THEMES.map((th) => ({
      key: th.id,
      label: t(th.nameKey),
      icon: <span class="swatch" style={{ background: th.preview.accent }} />,
      active: !autoMode.value && resolvedThemeId.value === th.id,
      onSelect: () => {
        setTheme(th.id)
        toast('info', t('common.toast.themeChanged', { name: t(th.nameKey) }))
      },
    })),
  ]

  const langItems = availableLocales.map((code) => ({
    key: code,
    label: LOCALE_META[code]?.nativeName ?? code,
    active: locale.value === code,
    onSelect: () => {
      setLocale(code)
      toast('info', t('common.toast.languageChanged', { name: LOCALE_META[code]?.nativeName ?? code }))
    },
  }))

  const initial = (displayName.value || 'Y').trim().charAt(0).toUpperCase() || 'Y'

  return (
    <header class="navbar">
      <button class="icon-btn navbar__burger" onClick={onOpenSidebar} aria-label={t('common.a11y.mainNav')}>
        <MenuIcon size={18} />
      </button>
      <button class="navbar__brand" onClick={() => navigate('overview')} aria-label={t('common.appName')}>
        <LogoLockup markSize={24} />
      </button>
      <div class="navbar__spacer" />
      <button
        class="navbar__search"
        onClick={() => window.dispatchEvent(new Event('ws:palette'))}
        aria-label={t('common.a11y.openPalette')}
      >
        <Search size={15} />
        <span class="navbar__search-text">{t('common.search')}</span>
        <kbd class="kbd">Ctrl K</kbd>
      </button>
      <span
        class={`status-dot status-dot--${h}`}
        role="status"
        title={`${statusLabel}${version ? ` · v${version}` : ''} · ${serverHostPort.value}`}
        aria-label={`${t('common.a11y.statusDot')}: ${statusLabel}`}
      />
      <Menu
        ariaLabel={t('common.a11y.themeMenu')}
        trigger={<PaletteIcon size={17} />}
        header={t('settings.appearance.theme')}
        items={themeItems}
      />
      <Menu
        ariaLabel={t('common.a11y.languageMenu')}
        trigger={<span class="navbar__lang">{locale.value.toUpperCase()}</span>}
        items={langItems}
      />
      <button class="avatar" aria-label={t('common.a11y.userMenu')} onClick={() => navigate('settings')}>
        {initial}
      </button>
    </header>
  )
}

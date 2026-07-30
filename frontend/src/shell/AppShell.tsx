import { useState } from 'preact/hooks'
import { Navbar } from './Navbar'
import { Sidebar, SidebarContent, MobileNav } from './Sidebar'
import { RouterView } from '@/pages/RouterView'
import { Drawer } from '@/components/Drawer'
import { ToastViewport } from '@/components/Toast'
import { CommandPalette } from '@/components/CommandPalette'
import { ParticleCanvas } from '@/components/ParticleCanvas'
import { t } from '@/i18n'

export function AppShell() {
  const [drawer, setDrawer] = useState(false)
  return (
    <div class="layout">
      <ParticleCanvas />
      <Navbar onOpenSidebar={() => setDrawer(true)} />
      <Sidebar />
      <main class="page-area" id="main">
        <RouterView />
      </main>
      <MobileNav onMore={() => setDrawer(true)} />
      <Drawer open={drawer} onClose={() => setDrawer(false)} title={t('common.appName')} width={300} side="left">
        <SidebarContent onNavigate={() => setDrawer(false)} />
      </Drawer>
      <ToastViewport />
      <CommandPalette />
    </div>
  )
}

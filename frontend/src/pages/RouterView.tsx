import { lazy, Suspense } from 'preact/compat'
import type { ComponentChild } from 'preact'
import { route, type PageId } from '@/core/router'
import { Placeholder } from './Placeholder'

/* Code-split: each page ships as its own chunk, loaded on first visit, so
   the entry bundle stays small (P5 gate 6: < 150 kB gzip on the entry). */
const Overview = lazy(() => import('./overview/Overview').then((m) => ({ default: m.Overview })))
const ChatPage = lazy(() => import('./chat/ChatPage').then((m) => ({ default: m.ChatPage })))
const StatsPage = lazy(() => import('./stats/StatsPage').then((m) => ({ default: m.StatsPage })))
const ModelsPage = lazy(() => import('./models/ModelsPage').then((m) => ({ default: m.ModelsPage })))
const IssuesPage = lazy(() => import('./issues/IssuesPage').then((m) => ({ default: m.IssuesPage })))
const HubPage = lazy(() => import('./hub/HubPage').then((m) => ({ default: m.HubPage })))
const DocsPage = lazy(() => import('./docs/DocsPage').then((m) => ({ default: m.DocsPage })))
const SettingsPage = lazy(() => import('./settings/SettingsPage').then((m) => ({ default: m.SettingsPage })))
const AssistantsPage = lazy(() => import('./assistants/AssistantsPage').then((m) => ({ default: m.AssistantsPage })))

/* P2: Overview / Chat / Live Stats / Models. P3: Issues / API Docs / Settings.
   P5: Hub (search-first GGUF discovery + real-progress downloads). */
export function RouterView() {
  const r = route.value
  return <Suspense fallback={<PageLoading />}>{renderPage(r.path)}</Suspense>
}

function renderPage(path: string): ComponentChild {
  switch (path) {
    case 'overview':
      return <Overview />
    case 'chat':
      return <ChatPage />
    case 'stats':
      return <StatsPage />
    case 'models':
      return <ModelsPage />
    case 'issues':
      return <IssuesPage />
    case 'hub':
      return <HubPage />
    case 'docs':
      return <DocsPage />
    case 'settings':
      return <SettingsPage />
    case 'assistants':
      return <AssistantsPage />
    default:
      return <Placeholder page={path as PageId} />
  }
}

function PageLoading() {
  return <div className="page-loading" aria-busy="true" role="status">…</div>
}

import { route, type PageId } from '@/core/router'
import { Placeholder } from './Placeholder'
import { Overview } from './overview/Overview'
import { ChatPage } from './chat/ChatPage'
import { StatsPage } from './stats/StatsPage'
import { ModelsPage } from './models/ModelsPage'
import { IssuesPage } from './issues/IssuesPage'
import { DocsPage } from './docs/DocsPage'
import { SettingsPage } from './settings/SettingsPage'

/* P2: Overview / Chat / Live Stats / Models. P3: Issues / API Docs / Settings.
   Hub (P5) keeps an honest placeholder. */
export function RouterView() {
  const r = route.value
  switch (r.path) {
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
    case 'docs':
      return <DocsPage />
    case 'settings':
      return <SettingsPage />
    default:
      return <Placeholder page={r.path as PageId} />
  }
}

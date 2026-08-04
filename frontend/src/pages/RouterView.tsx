import { route, type PageId } from '@/core/router'
import { Placeholder } from './Placeholder'
import { Overview } from './overview/Overview'
import { ChatPage } from './chat/ChatPage'
import { StatsPage } from './stats/StatsPage'
import { ModelsPage } from './models/ModelsPage'
import { IssuesPage } from './issues/IssuesPage'
import { HubPage } from './hub/HubPage'
import { DocsPage } from './docs/DocsPage'
import { SettingsPage } from './settings/SettingsPage'
import { AssistantsPage } from './assistants/AssistantsPage'

/* P2: Overview / Chat / Live Stats / Models. P3: Issues / API Docs / Settings.
   P5: Hub (search-first GGUF discovery + real-progress downloads). */
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
    case 'hub':
      return <HubPage />
    case 'docs':
      return <DocsPage />
    case 'settings':
      return <SettingsPage />
    case 'assistants':
      return <AssistantsPage />
    default:
      return <Placeholder page={r.path as PageId} />
  }
}

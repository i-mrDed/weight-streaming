import { route, type PageId } from '@/core/router'
import { Placeholder } from './Placeholder'
import { Overview } from './overview/Overview'
import { ChatPage } from './chat/ChatPage'
import { StatsPage } from './stats/StatsPage'
import { ModelsPage } from './models/ModelsPage'

/* P2: Overview / Chat / Live Stats / Models are real pages.
   Issues / API Docs / Settings (P3) and Hub (P5) keep honest placeholders. */
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
    default:
      return <Placeholder page={r.path as PageId} />
  }
}

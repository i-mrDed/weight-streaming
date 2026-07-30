import { route, type PageId } from '@/core/router'
import { Placeholder } from './Placeholder'

/* P1: every route renders its honest placeholder; real pages land P2–P5.
   The switch here grows per phase. */
export function RouterView() {
  const r = route.value
  // router.parse() guarantees a valid PageId
  return <Placeholder page={r.path as PageId} />
}

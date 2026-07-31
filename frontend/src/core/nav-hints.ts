/* Cross-page navigation hints — "view stats" / "use in chat" from the Models
   page carry a model id to the target page's selector. In-memory only
   (deliberate: not history state, consumed once on arrival). */
import { signal } from '@preact/signals'

/** '' = all / no preference */
export const statsFocusModel = signal<string>('')
export const chatFocusModel = signal<string>('')
/** '' = no preference (Hub shows its curated shelves); consumed once on arrival */
export const hubFocusQuery = signal<string>('')

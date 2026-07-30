/* highlight.js v11 exposes ./languages/* in its exports map but ships no
   per-path type declarations — declare the default-exported LanguageFn. */
declare module 'highlight.js/lib/languages/*' {
  import type { LanguageFn } from 'highlight.js'
  const lang: LanguageFn
  export default lang
}

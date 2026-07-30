/* XSS-safe markdown pipeline (spec §9.2 hard rule).
   marked → custom code-block renderer (highlight.js CORE build, registered
   languages only) → DOMPurify (html profile — no svg/math namespace).
   Model output NEVER reaches innerHTML without passing through sanitize(). */
import { Marked } from 'marked'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js/lib/core'
import python from 'highlight.js/lib/languages/python'
import javascript from 'highlight.js/lib/languages/javascript'
import typescript from 'highlight.js/lib/languages/typescript'
import bash from 'highlight.js/lib/languages/bash'
import json from 'highlight.js/lib/languages/json'
import yaml from 'highlight.js/lib/languages/yaml'
import sql from 'highlight.js/lib/languages/sql'
import xml from 'highlight.js/lib/languages/xml'
import diff from 'highlight.js/lib/languages/diff'
import { t } from '@/i18n'

hljs.registerLanguage('python', python)
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('js', javascript)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('ts', typescript)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('sh', bash)
hljs.registerLanguage('shell', bash)
hljs.registerLanguage('json', json)
hljs.registerLanguage('yaml', yaml)
hljs.registerLanguage('sql', sql)
hljs.registerLanguage('xml', xml)
hljs.registerLanguage('html', xml)
hljs.registerLanguage('diff', diff)

function esc(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

const marked = new Marked({
  gfm: true,
  breaks: true,
  renderer: {
    // Wrap code blocks with a lang label + copy button (delegated in Chat).
    // The raw code stays in <code> text content only — never in an attribute.
    code({ text, lang }: { text: string; lang?: string }) {
      const known = lang && hljs.getLanguage(lang) ? lang : ''
      const body = known
        ? hljs.highlight(text, { language: known }).value
        : esc(text)
      const label = esc(known || 'text')
      const copy = esc(t('common.copy'))
      return (
        `<div class="codeblock">` +
        `<div class="codeblock__bar"><span class="codeblock__lang">${label}</span>` +
        `<button type="button" class="codeblock__copy">${copy}</button></div>` +
        `<pre class="codeblock__pre"><code class="hljs">${body}</code></pre>` +
        `</div>`
      )
    },
    // External links open safely; hash links stay in-app.
    link({ href, title, tokens }: { href: string; title?: string | null; tokens: unknown[] }) {
      const text = this.parser.parseInline(tokens as never)
      const tAttr = title ? ` title="${esc(title)}"` : ''
      if (/^https?:\/\//i.test(href)) {
        return `<a href="${esc(href)}"${tAttr} target="_blank" rel="noopener noreferrer">${text}</a>`
      }
      return `<a href="${esc(href)}"${tAttr}>${text}</a>`
    },
  },
})

// Open external links in a new tab even when authored as raw HTML.
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    const href = node.getAttribute('href') ?? ''
    if (/^https?:\/\//i.test(href)) {
      node.setAttribute('target', '_blank')
      node.setAttribute('rel', 'noopener noreferrer')
    }
  }
})

/** Render markdown to SANITIZED html. Safe for innerHTML by contract. */
export function renderMarkdown(src: string): string {
  const raw = marked.parse(src, { async: false }) as string
  return DOMPurify.sanitize(raw, {
    USE_PROFILES: { html: true }, // no svg / math namespaces
    // img forbidden too: local-first chat needs no remote images, and a
    // broken <img src> would spam the console / fire network requests.
    FORBID_TAGS: ['style', 'form', 'input', 'iframe', 'embed', 'object', 'img'],
    FORBID_ATTR: ['style'],
  })
}

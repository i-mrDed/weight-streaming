/* 📖 API Docs (spec §9.7) — in-app, markdown-driven. Section prose lives in
   i18n (docs.sections.*); code samples live in ./content/*.md and are imported
   RAW at build time (so they're editable without touching this component).
   Each section renders honest prose + tabbed code (curl/Python/JS) with copy,
   an anchor-linked TOC with scroll-spy, in-page search, and HONEST notes
   (params accepted-but-not-executed, the Anthropic stream quirk, the WS route
   not being in the OpenAPI schema). A link opens the full Swagger UI. */
import { useEffect, useMemo, useRef } from 'preact/hooks'
import { useSignal } from '@preact/signals'
import { ExternalLink, Search } from 'lucide-preact'
import hljs from 'highlight.js/lib/core'
import python from 'highlight.js/lib/languages/python'
import javascript from 'highlight.js/lib/languages/javascript'
import bash from 'highlight.js/lib/languages/bash'
import json from 'highlight.js/lib/languages/json'
import { Card } from '@/components/Card'
import { Tip } from '@/components/Tip'
import { toast } from '@/components/Toast'
import { renderMarkdown } from '@/core/markdown'
import { locale, t } from '@/i18n'

hljs.registerLanguage('python', python)
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('js', javascript)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('sh', bash)
hljs.registerLanguage('json', json)

type Lang = 'curl' | 'python' | 'js'
const LANG_LABEL: Record<Lang, string> = { curl: 'cURL', python: 'Python', js: 'JavaScript' }

interface SectionDef {
  key: string
  tabs?: Lang[]
  /** honest-note keys (docs.honestNotes.*) shown under the section */
  notes?: string[]
}

/* Order = display order. Sections without tabs are prose-only. */
const SECTIONS: SectionDef[] = [
  { key: 'quickstart', tabs: ['curl', 'python', 'js'] },
  { key: 'openai', tabs: ['curl', 'python', 'js'], notes: ['reasoningEffort', 'tools'] },
  { key: 'anthropic', tabs: ['curl', 'python', 'js'], notes: ['anthropicStream'] },
  { key: 'native', tabs: ['curl', 'python'] },
  { key: 'websocket', notes: ['websocket'] },
  { key: 'ide', tabs: ['curl', 'python', 'js'] },
  { key: 'models', tabs: ['curl'] },
  { key: 'issues', tabs: ['curl'] },
  { key: 'server' },
]

// import.meta.glob with ?raw → { './content/quickstart.curl.md': '```bash\n…```' }
const rawMods = import.meta.glob('./content/*.md', { query: '?raw', import: 'default', eager: true }) as Record<
  string,
  string
>
const rawByFile: Record<string, string> = {}
for (const [path, content] of Object.entries(rawMods)) {
  const file = path.split('/').pop() ?? path
  rawByFile[file] = content
}

/** Pull the code body out of a single ```lang fence; highlight known langs.
 *  The result is safe to drop into <code> because hljs escapes text and our
 *  input is authored, not user/LLM-generated. */
function codeBlock(section: string, lang: Lang): { highlighted: string; raw: string } {
  const src = rawByFile[`${section}.${lang}.md`] ?? ''
  const m = src.match(/```(\w+)?\n([\s\S]*?)```/)
  const raw = m ? m[2].replace(/\n$/, '') : src
  const fenceLang = m?.[1] ?? lang
  const known = hljs.getLanguage(fenceLang) ? fenceLang : ''
  const highlighted = known ? hljs.highlight(raw, { language: known }).value : escapeHtml(raw)
  return { highlighted, raw }
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/** crude markdown→text for search indexing (drops fences/links/markup). */
function stripMd(s: string): string {
  return s
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/[*_#>]/g, ' ')
    .toLowerCase()
}

export function DocsPage() {
  locale.value
  const query = useSignal('')
  const activeTab = useSignal<Record<string, Lang>>({})
  const activeSection = useSignal<string>(SECTIONS[0]?.key ?? '')
  const contentRef = useRef<HTMLDivElement>(null)

  const tabFor = (key: string, def: Lang): Lang => activeTab.value[key] ?? def

  const setTab = (key: string, lang: Lang) => {
    activeTab.value = { ...activeTab.value, [key]: lang }
  }

  // search index: section key → searchable text
  const index = useMemo(() => {
    const out: Record<string, string> = {}
    for (const s of SECTIONS) {
      const title = t(`docs.sections.${s.key}.title`)
      const body = t(`docs.sections.${s.key}.body`)
      out[s.key] = stripMd(`${title} ${body}`)
    }
    return out
  }, [locale.value])

  const q = query.value.trim().toLowerCase()
  const visibleSections = q ? SECTIONS.filter((s) => index[s.key].includes(q)) : SECTIONS

  // scroll-spy: highlight the TOC entry of the section in view.
  useEffect(() => {
    const root = contentRef.current
    if (!root) return
    const heads = Array.from(root.querySelectorAll<HTMLElement>('[data-doc-section]'))
    if (!heads.length) return
    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            const id = (e.target as HTMLElement).getAttribute('data-doc-section')
            if (id) activeSection.value = id
          }
        }
      },
      { rootMargin: '-20% 0px -70% 0px', threshold: 0 },
    )
    heads.forEach((h) => obs.observe(h))
    return () => obs.disconnect()
  }, [q])

  const copy = async (text: string) => {
    try {
      await navigator.clipboard?.writeText(text)
      toast('success', t('common.copied'))
    } catch {
      toast('error', t('chat.copyFailed'))
    }
  }

  const goSection = (key: string) => {
    const el = contentRef.current?.querySelector<HTMLElement>(`[data-doc-section="${key}"]`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div class="page">
      <header class="page__header">
        <h1 class="page__title">
          <span aria-hidden="true">📖</span> {t('nav.docs')}
        </h1>
        <a class="docs__swagger" href="/docs" target="_blank" rel="noopener noreferrer">
          <ExternalLink size={14} aria-hidden="true" /> {t('docs.openSwagger')}
        </a>
      </header>

      <p class="docs__subtitle">{t('docs.subtitle')}</p>

      <div class="docs__layout">
        {/* TOC */}
        <nav class="docs__toc" aria-label={t('docs.toc')}>
          <div class="docs__search">
            <Search size={14} aria-hidden="true" />
            <input
              class="md-input"
              type="search"
              placeholder={t('docs.search')}
              value={query.value}
              onInput={(e) => (query.value = (e.target as HTMLInputElement).value)}
              aria-label={t('docs.search')}
            />
          </div>
          <ul>
            {SECTIONS.map((s) => {
              const hidden = q ? !visibleSections.some((v) => v.key === s.key) : false
              return (
                <li key={s.key} hidden={hidden}>
                  <button
                    type="button"
                    class={`docs__toc-link${activeSection.value === s.key ? ' is-on' : ''}`}
                    onClick={() => goSection(s.key)}
                  >
                    {t(`docs.sections.${s.key}.title`)}
                  </button>
                </li>
              )
            })}
          </ul>
        </nav>

        {/* content */}
        <div class="docs__content" ref={contentRef}>
          {visibleSections.length === 0 ? (
            <p class="dialog-text--dim">{t('docs.searchNoMatch')}</p>
          ) : (
            visibleSections.map((s) => {
              const tabs = s.tabs ?? []
              const cur = tabFor(s.key, tabs[0])
              const block = tabs.length ? codeBlock(s.key, cur) : null
              return (
                <section key={s.key} class="docs__section" id={`docs-${s.key}`} data-doc-section={s.key}>
                  <h2>
                    <a class="docs__anchor" href={`#docs-${s.key}`} aria-hidden="true">
                      #
                    </a>{' '}
                    {t(`docs.sections.${s.key}.title`)}
                  </h2>
                  <div class="docs__md" dangerouslySetInnerHTML={{ __html: renderMarkdown(t(`docs.sections.${s.key}.body`)) }} />

                  {tabs.length ? (
                    <div class="docs__code">
                      <div class="docs__tabs" role="tablist" aria-label={t(`docs.sections.${s.key}.title`)}>
                        {tabs.map((lang) => (
                          <button
                            key={lang}
                            type="button"
                            role="tab"
                            aria-selected={cur === lang}
                            class={`docs__tab${cur === lang ? ' is-on' : ''}`}
                            onClick={() => setTab(s.key, lang)}
                          >
                            {LANG_LABEL[lang]}
                          </button>
                        ))}
                        <button type="button" class="docs__copy" onClick={() => block && void copy(block.raw)}>
                          {t('docs.copyBlock')}
                        </button>
                      </div>
                      <pre class="codeblock__pre docs__pre">
                        <code class="hljs" dangerouslySetInnerHTML={{ __html: block?.highlighted ?? '' }} />
                      </pre>
                    </div>
                  ) : null}

                  {s.notes?.length ? (
                    <div class="docs__notes">
                      {s.notes.map((n) => (
                        <p key={n} class="docs__note">
                          <Tip label={t('docs.honest')} /> {t(`docs.honestNotes.${n}`)}
                        </p>
                      ))}
                    </div>
                  ) : null}

                  {s.key === 'issues' ? (
                    <Card class="docs__lifecycle">
                      <h4>{t('docs.lifecycle.title')}</h4>
                      <p class="dialog-text">{t('docs.lifecycle.body')}</p>
                    </Card>
                  ) : null}
                </section>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}

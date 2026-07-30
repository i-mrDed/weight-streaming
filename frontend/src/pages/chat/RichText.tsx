/* Message content renderer: <think> accordions + sanitized markdown.
   Everything goes through renderMarkdown() (marked → DOMPurify) — raw
   model/user text never touches innerHTML unsanitized (spec §9.2). */
import { parseThinks } from './thinks'
import { renderMarkdown } from '@/core/markdown'
import { t } from '@/i18n'

interface Props {
  text: string
  streaming?: boolean
}

export function RichText({ text, streaming }: Props) {
  const { main, thinks, partial } = parseThinks(text, !!streaming)

  return (
    <div class="rich">
      {thinks.map((th, i) => (
        <details key={i} class="think">
          <summary>💭 {t('chat.thinking')}</summary>
          <div class="msg__md" dangerouslySetInnerHTML={{ __html: renderMarkdown(th) }} />
        </details>
      ))}
      {partial !== null ? (
        <details class="think think--live" open>
          <summary>
            💭 {t('chat.thinkingLive')}
            <span class="think__spin" aria-hidden="true" />
          </summary>
          {partial ? (
            <div class="msg__md" dangerouslySetInnerHTML={{ __html: renderMarkdown(partial) }} />
          ) : null}
        </details>
      ) : null}
      {main ? (
        <div class="msg__md" dangerouslySetInnerHTML={{ __html: renderMarkdown(main) }} />
      ) : null}
    </div>
  )
}

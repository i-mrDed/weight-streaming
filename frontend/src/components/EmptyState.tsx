import type { ComponentChildren } from 'preact'

interface Props {
  emoji: string
  title: string
  body?: string
  children?: ComponentChildren // actions
  class?: string
}

export function EmptyState({ emoji, title, body, children, class: cls }: Props) {
  return (
    <div class={`empty${cls ? ` ${cls}` : ''}`}>
      <div class="empty__art" aria-hidden="true">
        <span class="empty__emoji">{emoji}</span>
      </div>
      <h3 class="empty__title">{title}</h3>
      {body ? <p class="empty__body">{body}</p> : null}
      {children ? <div class="empty__actions">{children}</div> : null}
    </div>
  )
}

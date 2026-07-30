import type { ComponentChildren } from 'preact'

export type BadgeTone = 'neutral' | 'ok' | 'warn' | 'error' | 'info' | 'brand'

interface Props {
  tone?: BadgeTone
  /** emoji/icon accent — decorative; text must carry meaning (a11y §7.2) */
  icon?: string
  children: ComponentChildren
  class?: string
}

export function Badge({ tone = 'neutral', icon, children, class: cls }: Props) {
  return (
    <span class={`badge badge--${tone}${cls ? ` ${cls}` : ''}`}>
      {icon ? <span aria-hidden="true">{icon}</span> : null}
      <span>{children}</span>
    </span>
  )
}

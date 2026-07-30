import type { ComponentChildren, JSX } from 'preact'

interface Props extends JSX.HTMLAttributes<HTMLDivElement> {
  /** raised = popover tier, base = default glass */
  tier?: 'base' | 'raised' | 'inset'
  hoverable?: boolean
  children: ComponentChildren
}

export function Card({ tier = 'base', hoverable = false, children, class: cls, ...rest }: Props) {
  return (
    <div
      class={`card card--${tier}${hoverable ? ' card--hoverable' : ''}${cls ? ` ${cls}` : ''}`}
      {...rest}
    >
      {children}
    </div>
  )
}

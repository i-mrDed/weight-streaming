import type { ComponentChildren, JSX } from 'preact'

export type ButtonVariant = 'primary' | 'soft' | 'ghost' | 'outline' | 'danger'
export type ButtonSize = 'sm' | 'md' | 'lg'

interface Props extends JSX.HTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  disabled?: boolean
  type?: 'button' | 'submit' | 'reset'
  children: ComponentChildren
}

export function Button({
  variant = 'ghost',
  size = 'md',
  loading = false,
  children,
  class: cls,
  disabled,
  ...rest
}: Props) {
  return (
    <button
      class={`btn btn--${variant} btn--${size}${loading ? ' is-loading' : ''}${cls ? ` ${cls}` : ''}`}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <span class="btn__spinner" aria-hidden="true" /> : null}
      {children}
    </button>
  )
}

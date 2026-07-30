/* Segmented control (reasoning effort etc.) — radio-group semantics. */
interface Option {
  value: string
  label: string
}

interface Props {
  options: Option[]
  value: string
  onChange: (v: string) => void
  ariaLabel: string
  size?: 'sm' | 'md'
}

export function Segmented({ options, value, onChange, ariaLabel, size = 'md' }: Props) {
  return (
    <div class={`segmented segmented--${size}`} role="radiogroup" aria-label={ariaLabel}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          class={`segmented__opt${value === o.value ? ' is-on' : ''}`}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

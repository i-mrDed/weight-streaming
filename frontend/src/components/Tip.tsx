/* Honest-tooltip info marker (spec §9.3 tooltips). Hover OR keyboard focus
   reveals the bubble; the trigger carries aria-label so screen readers get
   the text without the visual bubble. */
import { Info } from 'lucide-preact'

export function Tip({ label, size = 13 }: { label: string; size?: number }) {
  return (
    <span class="tip">
      <button type="button" class="tip__trigger" aria-label={label}>
        <Info size={size} aria-hidden="true" />
      </button>
      <span class="tip__bubble" role="tooltip">
        {label}
      </span>
    </span>
  )
}

/* Honest-tooltip info marker (spec §9.3 tooltips). Hover OR keyboard focus
   reveals the bubble; the trigger carries aria-label so screen readers get
   the text without the visual bubble.

   Placement is adaptive: the bubble prefers to open ABOVE the trigger, but
   when there is not enough room above (e.g. the chat toolbar, pinned under
   the top bar) it flips BELOW — measured from real layout so it never gets
   clipped off the top edge of the viewport. */
import { useRef, useState } from 'preact/hooks'
import { Info } from 'lucide-preact'

export function Tip({ label, size = 13 }: { label: string; size?: number }) {
  const wrapRef = useRef<HTMLSpanElement>(null)
  const [place, setPlace] = useState<'top' | 'bottom'>('top')

  // Decide top/bottom from the live rects. Safe to call while hidden: the
  // bubble is always in the DOM (opacity:0) so it has a measurable box.
  const placeForRoom = () => {
    const wrap = wrapRef.current
    if (!wrap) return
    const trigger = wrap.querySelector<HTMLElement>('.tip__trigger')
    const bubble = wrap.querySelector<HTMLElement>('.tip__bubble')
    if (!trigger || !bubble) return
    const r = trigger.getBoundingClientRect()
    const bh = bubble.offsetHeight || 64
    const roomAbove = r.top
    const roomBelow = window.innerHeight - r.bottom
    setPlace(roomAbove < bh + 12 && roomBelow >= roomAbove ? 'bottom' : 'top')
  }

  return (
    <span
      ref={wrapRef}
      class={`tip tip--${place}`}
      onPointerEnter={placeForRoom}
      onFocusIn={placeForRoom}
    >
      <button type="button" class="tip__trigger" aria-label={label}>
        <Info size={size} aria-hidden="true" />
      </button>
      <span class="tip__bubble" role="tooltip">
        {label}
      </span>
    </span>
  )
}

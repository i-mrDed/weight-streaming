/* Honest-tooltip info marker (spec §9.3 tooltips). Hover OR keyboard focus
   reveals the bubble; the trigger carries a SHORT localized accessible name
   (e.g. "More info") and links the bubble as its description via
   aria-describedby, so screen readers get the tooltip text exactly once —
   the bubble itself is aria-hidden until shown, so the long label text never
   becomes the button's name and never appears twice in the a11y tree.

   Placement is adaptive: the bubble prefers to open ABOVE the trigger, but
   when there is not enough room above (e.g. the chat toolbar, pinned under
   the top bar) it flips BELOW — measured from real layout so it never gets
   clipped off the top edge of the viewport. */
import { useId, useRef, useState } from 'preact/hooks'
import { Info } from 'lucide-preact'
import { t } from '@/i18n'

export function Tip({ label, size = 13 }: { label: string; size?: number }) {
  const wrapRef = useRef<HTMLSpanElement>(null)
  const tipId = useId()
  const [place, setPlace] = useState<'top' | 'bottom'>('top')
  const [open, setOpen] = useState(false)

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

  const show = () => {
    setOpen(true)
    placeForRoom()
  }
  const hide = () => setOpen(false)

  return (
    <span
      ref={wrapRef}
      class={`tip tip--${place}`}
      onPointerEnter={show}
      onPointerLeave={hide}
      onFocusIn={show}
      onFocusOut={hide}
    >
      <button
        type="button"
        class="tip__trigger"
        aria-label={t('common.a11y.moreInfo')}
        aria-describedby={tipId}
      >
        <Info size={size} aria-hidden="true" />
      </button>
      <span
        id={tipId}
        class="tip__bubble"
        role="tooltip"
        aria-hidden={open ? undefined : 'true'}
      >
        {label}
      </span>
    </span>
  )
}

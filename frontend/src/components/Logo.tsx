/* "Streamline W" brand mark (spec §5.4, D6)
   Three parallel flow streams forming a W — weights streaming
   NVMe → page cache → compute. Middle stream brightest (hot shard),
   tail stream dissolving into particles (paging in). */

let gradSeq = 0

interface MarkProps {
  size?: number
  /** stroke draw-in animation (boot splash) */
  animated?: boolean
  class?: string
}

export function LogoMark({ size = 28, animated = false, class: cls }: MarkProps) {
  const uid = `wsg${gradSeq++}`
  const W_PATH = 'M8 16 C11 32 14.5 44 19 50 C23.5 43 28 33 32 26 C36 33 40.5 43 45 50 C49.5 44 53 32 56 16'
  return (
    <svg
      class={`ws-logo${animated ? ' ws-logo--anim' : ''}${cls ? ` ${cls}` : ''}`}
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id={`${uid}-flow`} x1="6" y1="14" x2="58" y2="52" gradientUnits="userSpaceOnUse">
          <stop offset="0" stop-color="#8b5cf6" />
          <stop offset="0.38" stop-color="#6366f1" />
          <stop offset="0.72" stop-color="#06b6d4" />
          <stop offset="1" stop-color="#14b8a6" />
        </linearGradient>
        <linearGradient id={`${uid}-back`} x1="6" y1="14" x2="58" y2="52" gradientUnits="userSpaceOnUse">
          <stop offset="0" stop-color="#8b5cf6" />
          <stop offset="1" stop-color="#6366f1" />
        </linearGradient>
        <linearGradient id={`${uid}-front`} x1="6" y1="14" x2="58" y2="52" gradientUnits="userSpaceOnUse">
          <stop offset="0" stop-color="#06b6d4" />
          <stop offset="1" stop-color="#14b8a6" />
        </linearGradient>
      </defs>
      {/* back stream — violet, offset up */}
      <path
        d={W_PATH}
        transform="translate(0 -3.4)"
        stroke={`url(#${uid}-back)`}
        stroke-width="3"
        stroke-linecap="round"
        stroke-linejoin="round"
        opacity="0.48"
      />
      {/* middle stream — the hot shard, full spectrum, brightest */}
      <path
        d={W_PATH}
        stroke={`url(#${uid}-flow)`}
        stroke-width="4.4"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
      {/* front stream — cyan→teal, offset down, dissolving */}
      <path
        d={W_PATH}
        transform="translate(0 3.4)"
        stroke={`url(#${uid}-front)`}
        stroke-width="3"
        stroke-linecap="round"
        stroke-linejoin="round"
        opacity="0.5"
        stroke-dasharray="0.5 0"
      />
      {/* paging-in particles: growing spacing, shrinking size */}
      <circle cx="58.6" cy="16.4" r="1.5" fill="#14b8a6" opacity="0.65" />
      <circle cx="61.4" cy="12.6" r="1.15" fill="#14b8a6" opacity="0.45" />
      <circle cx="63.4" cy="8.6" r="0.85" fill="#14b8a6" opacity="0.3" />
    </svg>
  )
}

interface LockupProps {
  markSize?: number
  compact?: boolean
}

/** Mark + wordmark for navbar / splash. Wordmark is live text (translated
    nowhere — brand name) in the app font; standalone SVG files for docs
    live in public/. */
export function LogoLockup({ markSize = 26, compact = false }: LockupProps) {
  return (
    <span class="brand">
      <LogoMark size={markSize} />
      {!compact ? (
        <span class="brand__name">
          Weight<span class="brand__name-accent">Streaming</span>
        </span>
      ) : null}
    </span>
  )
}

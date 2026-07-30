/* Gauge card (spec §9.3): SVG arc + big tabular value + delta vs previous
   poll + honest tooltip + optional caveat slot. `fraction` null = idle/no
   data → renders the idle label, never a fake zero. */
import type { ComponentChildren } from 'preact'
import { Tip } from './Tip'
import { useAnimatedNumber } from './NumberTick'

export type GaugeTone = 'brand' | 'ok' | 'warn' | 'error' | 'info'

export interface GaugeDelta {
  /** absolute delta in the gauge's own unit (pre-formatted for display) */
  label: string
  dir: 'up' | 'down' | 'flat'
}

interface Props {
  label: string
  /** formats the (animated) numeric value */
  format: (n: number) => string
  /** raw numeric value to tick between (null = no data → idle look) */
  value: number | null
  /** 0..1 arc fill; null leaves the arc empty (honest idle) */
  fraction: number | null
  tone?: GaugeTone
  unit?: string
  tip?: string
  delta?: GaugeDelta | null
  caveat?: ComponentChildren
  idle?: string
  /** footer slot under the caveat */
  children?: ComponentChildren
}

const R = 40
const ARC = Math.PI * R // semicircle length

export function Gauge({
  label,
  format,
  value,
  fraction,
  tone = 'brand',
  unit,
  tip,
  delta,
  caveat,
  idle,
  children,
}: Props) {
  const shown = useAnimatedNumber(value)
  const frac = fraction === null ? 0 : Math.max(0, Math.min(1, fraction))
  const hasData = fraction !== null

  return (
    <div class={`gauge gauge--${tone}${hasData ? '' : ' gauge--idle'}`}>
      <div class="gauge__head">
        <span class="gauge__label">{label}</span>
        {tip ? <Tip label={tip} /> : null}
      </div>
      <div class="gauge__body">
        <svg class="gauge__arc" viewBox="0 0 100 54" aria-hidden="true">
          <path
            class="gauge__track"
            d="M 10 50 A 40 40 0 0 1 90 50"
            fill="none"
            stroke-width="7"
            stroke-linecap="round"
          />
          {hasData ? (
            <path
              class="gauge__fill"
              d="M 10 50 A 40 40 0 0 1 90 50"
              fill="none"
              stroke-width="7"
              stroke-linecap="round"
              stroke-dasharray={`${Math.max(frac * ARC, frac > 0 ? 2 : 0)} ${ARC}`}
            />
          ) : null}
        </svg>
        <div class="gauge__value">
          {hasData && shown !== null ? (
            <>
              <span class="gauge__num tnum">{format(shown)}</span>
              {unit ? <span class="gauge__unit">{unit}</span> : null}
            </>
          ) : (
            <span class="gauge__idle">{idle ?? '—'}</span>
          )}
        </div>
      </div>
      <div class="gauge__foot">
        {delta && hasData ? (
          <span
            class={`gauge__delta gauge__delta--${delta.dir}`}
            title={delta.label}
            aria-label={`delta ${delta.label}`}
          >
            {delta.dir === 'up' ? '↑' : delta.dir === 'down' ? '↓' : '→'} {delta.label}
          </span>
        ) : (
          <span />
        )}
        {caveat ? <div class="gauge__caveat">{caveat}</div> : null}
      </div>
      {children}
    </div>
  )
}

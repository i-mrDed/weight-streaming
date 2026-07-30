/* MoE expert heatmap (spec §9.3). Cells light up ONLY from real telemetry
   (`active_experts` — the server does not provide it today; stock llama.cpp
   keeps routing opaque), so the grid stays dark with an honest status line
   instead of animating fake firing. Dense models (n_experts = 0) get a
   designed degrade, not an empty grid. */
import { fmtNumber } from '@/i18n'
import { t } from '@/i18n'

const CELLS_MAX = 256

interface Props {
  nExperts: number
  activeExperts: number[] | null
}

export function Heatmap({ nExperts, activeExperts }: Props) {
  if (nExperts <= 0) {
    return (
      <div class="heat heat--dense">
        <div class="heat__dense-art" aria-hidden="true">🧩</div>
        <p class="heat__dense-title">{t('stats.heatmap.notMoe')}</p>
        <p class="heat__dense-body">{t('stats.heatmap.notMoeBody')}</p>
      </div>
    )
  }

  const cells = Math.min(nExperts, CELLS_MAX)
  const firing = new Set((activeExperts ?? []).map((i) => ((i % cells) + cells) % cells))

  return (
    <div class="heat">
      <div class="heat__grid" role="img" aria-label={t('stats.heatmap.aria', { count: fmtNumber(cells) })}>
        {Array.from({ length: cells }, (_, i) => (
          <span key={i} class={`heat__cell${firing.has(i) ? ' is-firing' : ''}`} title={`#${i}`} />
        ))}
      </div>
      <div class="heat__status">
        {activeExperts && activeExperts.length > 0 ? (
          <span class="heat__live">{t('stats.heatmap.firing', { count: activeExperts.length })}</span>
        ) : (
          <span>{t('stats.heatmap.total', { count: fmtNumber(nExperts) })}</span>
        )}
      </div>
    </div>
  )
}

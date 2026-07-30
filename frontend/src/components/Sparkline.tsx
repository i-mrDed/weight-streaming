/* Hand-rolled canvas time-series (spec §9.3 / §11 — leaner than uPlot).
   DPR-aware, ResizeObserver-driven, theme-aware (reads CSS custom props,
   redraws on theme change). Data = session-window ring buffer, labelled
   honestly by the caller. */
import { useEffect, useRef } from 'preact/hooks'
import { resolvedThemeId } from '@/theme/manager'
import { t, fmtNumber } from '@/i18n'

interface Props {
  data: number[]
  /** semantic css var name used for the line, e.g. '--ws-accent-brand' */
  cssVar?: string
  unit: string
  height?: number
  /** format for min/max/current labels */
  format?: (n: number) => string
}

function cssColor(name: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || '#6366f1'
}

export function Sparkline({ data, cssVar = '--ws-accent-brand', unit, height = 120, format }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const theme = resolvedThemeId.value // re-render (and redraw) on theme switch
  const fmt = format ?? ((n: number) => fmtNumber(n, { maximumFractionDigits: 1 }))

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const parent = canvas.parentElement
    if (!parent) return

    const draw = () => {
      const dpr = window.devicePixelRatio || 1
      const w = parent.clientWidth
      const h = height
      if (w === 0) return
      canvas.width = Math.round(w * dpr)
      canvas.height = Math.round(h * dpr)
      canvas.style.width = `${w}px`
      canvas.style.height = `${h}px`
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      ctx.scale(dpr, dpr)
      ctx.clearRect(0, 0, w, h)

      const pts = data
      if (pts.length < 2) return

      const line = cssColor(cssVar)
      const grid = cssColor('--ws-border-subtle')
      const padY = 10
      const min = Math.min(...pts)
      const max = Math.max(...pts)
      const span = max - min || 1
      const x = (i: number) => (i / (pts.length - 1)) * (w - 2) + 1
      const y = (v: number) => h - padY - ((v - min) / span) * (h - padY * 2)

      // quarter gridlines
      ctx.strokeStyle = grid
      ctx.lineWidth = 1
      for (let g = 1; g < 4; g++) {
        const gy = Math.round(padY + ((h - padY * 2) * g) / 4) + 0.5
        ctx.beginPath()
        ctx.moveTo(0, gy)
        ctx.lineTo(w, gy)
        ctx.stroke()
      }

      // area fill
      const grad = ctx.createLinearGradient(0, 0, 0, h)
      grad.addColorStop(0, line + '44')
      grad.addColorStop(1, line + '00')
      ctx.beginPath()
      ctx.moveTo(x(0), y(pts[0]))
      for (let i = 1; i < pts.length; i++) ctx.lineTo(x(i), y(pts[i]))
      ctx.lineTo(x(pts.length - 1), h)
      ctx.lineTo(x(0), h)
      ctx.closePath()
      ctx.fillStyle = grad
      ctx.fill()

      // line
      ctx.beginPath()
      ctx.moveTo(x(0), y(pts[0]))
      for (let i = 1; i < pts.length; i++) ctx.lineTo(x(i), y(pts[i]))
      ctx.strokeStyle = line
      ctx.lineWidth = 1.6
      ctx.lineJoin = 'round'
      ctx.stroke()

      // current-point dot
      const lx = x(pts.length - 1)
      const ly = y(pts[pts.length - 1])
      ctx.beginPath()
      ctx.arc(lx, ly, 2.6, 0, Math.PI * 2)
      ctx.fillStyle = line
      ctx.fill()
    }

    draw()
    const ro = new ResizeObserver(draw)
    ro.observe(parent)
    return () => ro.disconnect()
  }, [data, data.length, data[data.length - 1], theme, cssVar, height])

  const pts = data
  const has = pts.length >= 2
  const min = has ? Math.min(...pts) : 0
  const max = has ? Math.max(...pts) : 0
  const cur = has ? pts[pts.length - 1] : 0

  return (
    <div class="spark">
      <div class="spark__meta">
        {has ? (
          <>
            <span class="spark__stat">
              <em>{t('stats.chart.current')}</em>
              <b class="tnum">{fmt(cur)} {unit}</b>
            </span>
            <span class="spark__stat">
              <em>{t('stats.chart.min')}</em>
              <b class="tnum">{fmt(min)}</b>
            </span>
            <span class="spark__stat">
              <em>{t('stats.chart.max')}</em>
              <b class="tnum">{fmt(max)} {unit}</b>
            </span>
          </>
        ) : null}
        <span class="spark__count tnum">
          {t('stats.chart.points', { count: pts.length })}
        </span>
      </div>
      <div class="spark__canvas" style={{ height: `${height}px` }}>
        {has ? null : <div class="spark__empty">{t('stats.chart.waiting')}</div>}
        <canvas ref={canvasRef} role="img" aria-label={`${unit} · ${t('stats.chart.window')}`} />
      </div>
    </div>
  )
}

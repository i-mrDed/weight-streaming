/* Constellation particle field (spec §5.2)
   - slow drift (~12px/s), links <140px, cursor links + gentle attraction 180px
   - density by viewport area (24–60 nodes)
   - colors from theme tokens (--ws-particle-node/line)
   - hard gates: particlesActive signal (theme+switch+reduced-motion),
     tab visibility, Battery API low-power
   - aria-hidden, pointer-events none — pure ambience */
import { useEffect, useRef } from 'preact/hooks'
import { particlesActive } from '@/theme/manager'
import { resolvedThemeId } from '@/theme/manager'

interface Node {
  x: number
  y: number
  vx: number
  vy: number
}

const LINK_DIST = 140
const CURSOR_DIST = 180
const MIN_NODES = 24
const MAX_NODES = 60

export function ParticleCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let nodes: Node[] = []
    let raf = 0
    let last = 0
    let running = false
    let hidden = document.hidden
    let lowBattery = false
    let nodeColor = 'rgba(129,140,248,0.55)'
    let lineColor = 'rgba(129,140,248,0.16)'
    let dpr = 1
    let W = 0
    let H = 0
    const mouse = { x: -9999, y: -9999, active: false }

    const readColors = () => {
      const cs = getComputedStyle(document.documentElement)
      nodeColor = cs.getPropertyValue('--ws-particle-node').trim() || nodeColor
      lineColor = cs.getPropertyValue('--ws-particle-line').trim() || lineColor
    }

    const seed = () => {
      const area = W * H
      const count = Math.max(MIN_NODES, Math.min(MAX_NODES, Math.round(area / 22_000)))
      nodes = Array.from({ length: count }, () => {
        const angle = Math.random() * Math.PI * 2
        const speed = 6 + Math.random() * 12 // 6–18 px/s
        return {
          x: Math.random() * W,
          y: Math.random() * H,
          vx: Math.cos(angle) * speed,
          vy: Math.sin(angle) * speed,
        }
      })
    }

    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2)
      W = window.innerWidth
      H = window.innerHeight
      canvas.width = Math.round(W * dpr)
      canvas.height = Math.round(H * dpr)
      canvas.style.width = `${W}px`
      canvas.style.height = `${H}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      seed()
    }

    const draw = (dt: number) => {
      ctx.clearRect(0, 0, W, H)
      // integrate + cursor attraction
      for (const n of nodes) {
        if (mouse.active) {
          const dx = mouse.x - n.x
          const dy = mouse.y - n.y
          const d = Math.hypot(dx, dy)
          if (d < CURSOR_DIST && d > 1) {
            const pull = 10 * (1 - d / CURSOR_DIST) // gentle, px/s
            n.vx += (dx / d) * pull * dt
            n.vy += (dy / d) * pull * dt
          }
        }
        n.x += n.vx * dt
        n.y += n.vy * dt
        // wrap edges
        if (n.x < -20) n.x = W + 20
        if (n.x > W + 20) n.x = -20
        if (n.y < -20) n.y = H + 20
        if (n.y > H + 20) n.y = -20
        // clamp speed back toward drift range
        const sp = Math.hypot(n.vx, n.vy)
        if (sp > 24) {
          n.vx = (n.vx / sp) * 24
          n.vy = (n.vy / sp) * 24
        }
      }
      // links
      ctx.lineWidth = 1
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i]
        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j]
          const dx = a.x - b.x
          const dy = a.y - b.y
          const d2 = dx * dx + dy * dy
          if (d2 < LINK_DIST * LINK_DIST) {
            const d = Math.sqrt(d2)
            ctx.strokeStyle = withAlpha(lineColor, 1 - d / LINK_DIST)
            ctx.beginPath()
            ctx.moveTo(a.x, a.y)
            ctx.lineTo(b.x, b.y)
            ctx.stroke()
          }
        }
        // cursor link
        if (mouse.active) {
          const dx = a.x - mouse.x
          const dy = a.y - mouse.y
          const d = Math.hypot(dx, dy)
          if (d < CURSOR_DIST) {
            ctx.strokeStyle = withAlpha(nodeColor, (1 - d / CURSOR_DIST) * 0.7)
            ctx.beginPath()
            ctx.moveTo(a.x, a.y)
            ctx.lineTo(mouse.x, mouse.y)
            ctx.stroke()
          }
        }
      }
      // nodes (brighter near cursor)
      for (const n of nodes) {
        let boost = 0
        if (mouse.active) {
          const d = Math.hypot(n.x - mouse.x, n.y - mouse.y)
          if (d < CURSOR_DIST) boost = 1 - d / CURSOR_DIST
        }
        ctx.fillStyle = withAlpha(nodeColor, 0.55 + boost * 0.45)
        ctx.beginPath()
        ctx.arc(n.x, n.y, 1.5 + boost * 1.4, 0, Math.PI * 2)
        ctx.fill()
      }
    }

    const loop = (now: number) => {
      if (!running) return
      const dt = Math.min((now - last) / 1000, 0.05)
      last = now
      draw(dt)
      raf = requestAnimationFrame(loop)
    }

    const recompute = () => {
      const should = particlesActive.value && !hidden && !lowBattery
      if (should && !running) {
        running = true
        readColors()
        last = performance.now()
        raf = requestAnimationFrame(loop)
        canvas.style.opacity = '1'
      } else if (!should && running) {
        running = false
        cancelAnimationFrame(raf)
        ctx.clearRect(0, 0, W, H)
        canvas.style.opacity = '0'
      }
    }

    const onVisibility = () => {
      hidden = document.hidden
      recompute()
    }
    const onMouseMove = (e: MouseEvent) => {
      mouse.x = e.clientX
      mouse.y = e.clientY
      mouse.active = true
    }
    const onMouseLeave = () => {
      mouse.active = false
    }

    resize()
    readColors()
    window.addEventListener('resize', resize)
    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener('mousemove', onMouseMove, { passive: true })
    document.addEventListener('mouseleave', onMouseLeave)

    // Battery saver gate (best effort — API absent on some browsers)
    const nav = navigator as Navigator & { getBattery?: () => Promise<{ low: boolean; addEventListener: (t: string, cb: () => void) => void }> }
    nav.getBattery?.().then((bat) => {
      const update = () => {
        lowBattery = bat.low
        recompute()
      }
      bat.addEventListener('levelchange', update)
      bat.addEventListener('chargingchange', update)
      update()
    }).catch(() => {})

    // react to theme / kill-switch / OS-motion changes
    const disposeTheme = resolvedThemeId.subscribe(() => {
      readColors()
      recompute()
    })
    const disposeActive = particlesActive.subscribe(recompute)
    recompute()

    return () => {
      running = false
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseleave', onMouseLeave)
      disposeTheme()
      disposeActive()
    }
  }, [])

  return <canvas ref={canvasRef} class="particles" aria-hidden="true" />
}

/** Apply an alpha multiplier to an rgba()/rgb() color token */
function withAlpha(color: string, factor: number): string {
  const m = color.match(/rgba?\(([^)]+)\)/)
  if (!m) return color
  const parts = m[1].split(',').map((p) => p.trim())
  const base = parts[3] !== undefined ? parseFloat(parts[3]) : 1
  return `rgba(${parts[0]}, ${parts[1]}, ${parts[2]}, ${(base * factor).toFixed(3)})`
}

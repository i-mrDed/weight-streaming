/* Numeric tick animation on stat change (spec §5.2 motion). Tweens toward
   the target with rAF; jumps instantly under prefers-reduced-motion. */
import { useEffect, useRef, useState } from 'preact/hooks'

const REDUCED =
  typeof window !== 'undefined' &&
  !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

export function useAnimatedNumber(target: number | null, duration = 380): number | null {
  const [display, setDisplay] = useState<number | null>(target)
  const fromRef = useRef<number | null>(target)
  const rafRef = useRef(0)

  useEffect(() => {
    if (target === null) {
      cancelAnimationFrame(rafRef.current)
      fromRef.current = null
      setDisplay(null)
      return
    }
    const from = fromRef.current ?? target
    if (REDUCED || from === target) {
      fromRef.current = target
      setDisplay(target)
      return
    }
    const start = performance.now()
    const step = (now: number) => {
      const p = Math.min(1, (now - start) / duration)
      const eased = 1 - (1 - p) ** 3
      setDisplay(from + (target - from) * eased)
      if (p < 1) {
        rafRef.current = requestAnimationFrame(step)
      } else {
        fromRef.current = target
      }
    }
    cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(step)
    return () => cancelAnimationFrame(rafRef.current)
  }, [target, duration])

  return display
}

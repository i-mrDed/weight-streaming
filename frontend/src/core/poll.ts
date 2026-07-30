/* Poll manager (spec §11) — visibility-aware, single-flight, backoff on
   failure, jitter on start. Stops entirely when the tab is hidden. */

export interface Poller {
  start: () => void
  stop: () => void
  /** force one immediate tick (e.g. on tab re-focus) */
  kick: () => void
}

export function createPoller(
  tick: () => Promise<void>,
  intervalMs: number,
  opts?: { onErrorBackoffCap?: number },
): Poller {
  let timer: number | null = null
  let running = false // single-flight guard
  let failures = 0
  let started = false
  const cap = opts?.onErrorBackoffCap ?? intervalMs * 8

  const schedule = (delay: number) => {
    if (timer !== null) window.clearTimeout(timer)
    timer = window.setTimeout(run, delay)
  }

  const nextDelay = () => {
    if (failures === 0) return intervalMs
    return Math.min(cap, intervalMs * 2 ** failures)
  }

  async function run() {
    timer = null
    if (document.hidden || !started) return
    if (running) {
      schedule(intervalMs)
      return
    }
    running = true
    try {
      await tick()
      failures = 0
    } catch {
      failures += 1
    } finally {
      running = false
    }
    if (started && !document.hidden) schedule(nextDelay())
  }

  const onVisibility = () => {
    if (document.hidden) {
      if (timer !== null) {
        window.clearTimeout(timer)
        timer = null
      }
    } else if (started) {
      schedule(200 + Math.random() * 400) // quick catch-up with jitter
    }
  }

  return {
    start() {
      if (started) return
      started = true
      document.addEventListener('visibilitychange', onVisibility)
      schedule(Math.random() * intervalMs * 0.3) // jitter first hit
    },
    stop() {
      started = false
      if (timer !== null) window.clearTimeout(timer)
      timer = null
      document.removeEventListener('visibilitychange', onVisibility)
    },
    kick() {
      if (started && !document.hidden) schedule(0)
    },
  }
}

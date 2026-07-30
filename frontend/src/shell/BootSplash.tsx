/* Boot splash (spec §5.4) — brand moment with REAL connection status.
   Never fakes: checking → connected (host + version) | failed + hint + retry.
   Auto-recovers because the shell poller keeps probing /health. */
import { LogoMark } from '@/components/Logo'
import { Button } from '@/components/Button'
import { t } from '@/i18n'
import { health, serverVersion, serverHostPort, probeHealth } from '@/core/store'

export function BootSplash() {
  const h = health.value
  return (
    <div class="splash">
      <div class="splash__inner">
        <LogoMark size={96} animated />
        <div class="splash__word" aria-label="Weight Streaming">
          WEIGHT<span>STREAMING</span>
        </div>
        <div class="splash__sub">CONSOLE</div>
        <div class={`splash__status splash__status--${h}`} role="status">
          {h === 'checking' ? (
            <>
              <span class="splash__spin" aria-hidden="true" />
              {t('common.splash.checking')}
            </>
          ) : h === 'online' ? (
            <>
              <span class="splash__dot splash__dot--ok" aria-hidden="true" />
              {t('common.splash.connected', { host: serverHostPort.value })}
              {serverVersion.value ? ` · ${t('common.splash.version', { version: serverVersion.value })}` : ''}
            </>
          ) : (
            <div class="splash__fail">
              <div class="splash__fail-line">
                <span class="splash__dot splash__dot--err" aria-hidden="true" />
                {t('common.splash.failed')}
              </div>
              <code class="splash__hint">{t('common.splash.failedHint')}</code>
              <Button variant="primary" onClick={() => void probeHealth()}>
                {t('common.retry')}
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

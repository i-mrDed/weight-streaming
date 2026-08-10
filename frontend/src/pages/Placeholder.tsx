/* P1 honest placeholder for pages built in later phases (spec §13).
   Not an error page — a designed waiting state that tells the truth
   about which phase delivers the page. */
import { Button } from '@/components/Button'
import { navigate, type PageId } from '@/core/router'
import { t } from '@/i18n'

const PHASE: Record<PageId, string> = {
  overview: 'P2',
  chat: 'P2',
  stats: 'P2',
  models: 'P2',
  issues: 'P3',
  docs: 'P3',
  settings: 'P3',
  hub: 'P5',
  assistants: 'P7',
}

const EMOJI: Record<PageId, string> = {
  overview: '🏠',
  chat: '💬',
  stats: '📊',
  models: '🧠',
  issues: '🐛',
  hub: '🌐',
  docs: '📖',
  settings: '⚙️',
  assistants: '🤖',
}

export function Placeholder({ page }: { page: PageId }) {
  return (
    <div class="page">
      <header class="page__header">
        <h1 class="page__title">
          <span aria-hidden="true">{EMOJI[page]}</span> {t(`nav.${page}`)}
        </h1>
      </header>
      <div class="placeholder">
        <div class="placeholder__art" aria-hidden="true">
          <span>{EMOJI[page]}</span>
        </div>
        <h2 class="placeholder__title">{t('common.placeholder.title', { page: t(`nav.${page}`) })}</h2>
        <p class="placeholder__body">{t('common.placeholder.body')}</p>
        <p class="placeholder__phase">{t('common.placeholder.phase', { phase: PHASE[page] })}</p>
        <div class="placeholder__actions">
          <Button variant="primary" onClick={() => navigate('overview')}>
            {t('common.placeholder.backHome')}
          </Button>
        </div>
      </div>
    </div>
  )
}

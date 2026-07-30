/* 🏠 Overview (spec §9.1) — system status at a glance + shortcuts.
   Sources: /health + /v1/stats (polled 5s, visibility-aware), /v1/models,
   /v1/issues?status=open (via shell store). Activity feed is an HONEST
   empty state — usage history needs the P4 backend (/v1/usage/history). */
import { useEffect, useRef } from 'preact/hooks'
import { useSignal } from '@preact/signals'
import {
  Bug,
  FolderSearch,
  HardDriveDownload,
  MessageSquare,
  Plus,
  Server,
  XCircle,
} from 'lucide-preact'
import { Card } from '@/components/Card'
import { Button } from '@/components/Button'
import { Badge } from '@/components/Badge'
import { EmptyState } from '@/components/EmptyState'
import { Dialog } from '@/components/Dialog'
import { Tip } from '@/components/Tip'
import { toast } from '@/components/Toast'
import { ApiError } from '@/core/api'
import { navigate } from '@/core/router'
import { t, fmtNumber, relativeDay, locale } from '@/i18n'
import { createPoller } from '@/core/poll'
import { fetchStats, type StatsPayload, type ModelStats } from '@/core/stats'
import { guessQuant, unloadModel } from '@/core/models'
import { health, models, openIssueCount, serverVersion } from '@/core/store'

function fmtDuration(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${sec}s`
  return `${sec}s`
}

/** First model that recorded paging telemetry this session — honest "latest". */
function pickPaging(stats: StatsPayload | null): { id: string; ms: ModelStats } | null {
  if (!stats) return null
  for (const [id, ms] of Object.entries(stats.models)) {
    if (ms.generation?.paging) return { id, ms }
  }
  return null
}

export function Overview() {
  locale.value // subscribe: relative labels re-render on language switch
  const stats = useSignal<StatsPayload | null>(null)
  const unreachable = useSignal(false)
  const onlineSince = useRef<number | null>(null)
  const tick = useSignal(0) // 1s heartbeat for the uptime label
  const unloadTarget = useSignal<string | null>(null)
  const unloading = useSignal(false)

  if (health.value === 'online' && onlineSince.current === null) {
    onlineSince.current = Date.now()
  }

  useEffect(() => {
    const poller = createPoller(async () => {
      try {
        stats.value = await fetchStats()
        unreachable.value = false
      } catch {
        unreachable.value = true
      }
    }, 5000)
    poller.start()
    poller.kick()
    const beat = window.setInterval(() => (tick.value += 1), 1000)
    return () => {
      poller.stop()
      window.clearInterval(beat)
    }
  }, [])

  const loaded = models.value
  const srv = stats.value?.server ?? null
  const hostPort = srv ? `${srv.host}:${srv.port}` : window.location.host
  const paging = pickPaging(stats.value)
  const pagingVal = paging?.ms.generation.paging
  const residency = (() => {
    for (const ms of Object.values(stats.value?.models ?? {})) {
      if (typeof ms.page_cache?.resident_ratio === 'number' && Object.keys(ms.page_cache).length > 0) {
        return ms.page_cache
      }
    }
    return null
  })()
  const issues = openIssueCount.value
  // heartbeat read → re-render every second so the uptime label ticks
  void tick.value
  const uptime = onlineSince.current !== null ? fmtDuration(Date.now() - onlineSince.current) : null

  const doUnload = async () => {
    const id = unloadTarget.value
    if (!id) return
    unloading.value = true
    try {
      await unloadModel(id)
      models.value = models.value.filter((m) => m.id !== id)
      toast('success', t('overview.models.unloaded', { id }))
      unloadTarget.value = null
    } catch (e) {
      toast('error', t('overview.models.unloadFailed'), {
        body: e instanceof ApiError && e.detail ? e.detail : undefined,
      })
    } finally {
      unloading.value = false
    }
  }

  return (
    <div class="page">
      <header class="page__header">
        <h1 class="page__title">
          <span aria-hidden="true">🏠</span> {t('nav.overview')}
        </h1>
      </header>

      {/* ── Hero status strip ─────────────────────────────────── */}
      <Card tier="raised" class="ov-hero">
        <div class="ov-hero__main">
          <span class={`status-dot status-dot--${health.value}`} aria-hidden="true" />
          <div class="ov-hero__texts">
            <div class="ov-hero__state">
              {health.value === 'online'
                ? t('overview.hero.online')
                : health.value === 'offline'
                  ? t('overview.hero.offline')
                  : t('common.health.checking')}
            </div>
            <div class="ov-hero__sub tnum">
              {hostPort}
              {uptime ? (
                <>
                  {' · '}
                  <span class="ov-hero__uptime">
                    {t('overview.hero.uptime', { duration: uptime })}
                    <Tip label={t('overview.hero.uptimeTip')} />
                  </span>
                </>
              ) : null}
            </div>
          </div>
        </div>
        <div class="ov-hero__badges">
          {srv?.priority ? (
            <Badge tone={srv.priority.lowered ? 'info' : 'neutral'} icon={srv.priority.lowered ? '🪶' : undefined}>
              {srv.priority.lowered
                ? t('overview.hero.priorityLow')
                : t('overview.hero.priorityNormal')}
              <Tip
                label={`${srv.priority.mechanism ?? srv.priority.priority_class ?? ''} · ${srv.priority.platform}`}
              />
            </Badge>
          ) : null}
          {serverVersion.value ? (
            <Badge tone="brand">
              <Server size={12} aria-hidden="true" /> v{serverVersion.value}
            </Badge>
          ) : null}
          {srv ? (
            <Badge tone="neutral" icon="🧠">
              {t('nav.modelsLoaded_' + (srv.models_loaded === 1 ? 'one' : 'other'), { count: srv.models_loaded })}
              /{srv.max_models}
            </Badge>
          ) : null}
        </div>
      </Card>

      {/* ── Quick actions ─────────────────────────────────────── */}
      <div class="ov-quick">
        <Button variant="ghost" onClick={() => navigate('models')}>
          <FolderSearch size={15} aria-hidden="true" /> {t('overview.quick.scan')}
        </Button>
        <Button variant="ghost" onClick={() => navigate('models')}>
          <HardDriveDownload size={15} aria-hidden="true" /> {t('overview.quick.load')}
        </Button>
        <Button variant="primary" onClick={() => navigate('chat')}>
          <MessageSquare size={15} aria-hidden="true" /> {t('overview.quick.chat')}
        </Button>
        <Button variant="ghost" onClick={() => navigate('issues')}>
          <Bug size={15} aria-hidden="true" /> {t('overview.quick.report')}
        </Button>
      </div>

      {/* ── Loaded models row ─────────────────────────────────── */}
      <section class="ov-section">
        <h2 class="ov-section__title">{t('overview.models.title')}</h2>
        {loaded.length === 0 ? (
          <Card>
            <EmptyState
              emoji="🧠"
              title={t('overview.models.emptyTitle')}
              body={t('overview.models.emptyBody')}
            >
              <Button variant="primary" onClick={() => navigate('models')}>
                <FolderSearch size={15} aria-hidden="true" /> {t('overview.models.emptyScan')}
              </Button>
              <Button variant="ghost" onClick={() => navigate('hub')} disabled title={t('common.comingSoon')}>
                {t('overview.models.emptyHub')}
              </Button>
            </EmptyState>
          </Card>
        ) : (
          <div class="ov-models">
            {loaded.map((m) => {
              const quant = guessQuant(m.path || m.id)
              return (
                <Card key={m.id} hoverable class="ov-model">
                  <div class="ov-model__top">
                    <span class="ov-model__id" title={m.path}>{m.id}</span>
                    <button
                      class="icon-btn ov-model__unload"
                      aria-label={t('overview.models.unload')}
                      title={t('overview.models.unload')}
                      onClick={() => (unloadTarget.value = m.id)}
                    >
                      <XCircle size={15} />
                    </button>
                  </div>
                  <div class="ov-model__badges">
                    <Badge tone="neutral">{m.arch ?? 'unknown'}</Badge>
                    {quant ? <Badge tone="brand">{quant}</Badge> : null}
                    {m.n_experts > 0 ? <Badge tone="info">MoE · {fmtNumber(m.n_experts)}</Badge> : null}
                  </div>
                  <div class="ov-model__meta tnum">
                    <span>{t('overview.models.buffer', { mb: fmtNumber(m.buffer_mb) })}</span>
                    <span>
                      {m.last_used
                        ? t('overview.models.lastUsed', { when: relativeDay(new Date(m.last_used).getTime()) })
                        : t('overview.models.neverUsed')}
                    </span>
                  </div>
                </Card>
              )
            })}
            <button class="ov-model-add" onClick={() => navigate('models')}>
              <Plus size={18} aria-hidden="true" />
              <span>{t('overview.models.loadMore')}</span>
            </button>
          </div>
        )}
      </section>

      <div class="ov-grid">
        {/* ── Activity (HONEST empty — usage history is P4) ─────── */}
        <section class="ov-section">
          <h2 class="ov-section__title">
            {t('overview.activity.title')}
            <Tip label={t('overview.activity.tip')} />
          </h2>
          <Card>
            <EmptyState emoji="📈" title={t('overview.activity.emptyTitle')} body={t('overview.activity.emptyBody')}>
              <Button variant="soft" onClick={() => navigate('chat')}>
                <MessageSquare size={15} aria-hidden="true" /> {t('overview.quick.chat')}
              </Button>
            </EmptyState>
          </Card>
        </section>

        {/* ── Health widgets ────────────────────────────────────── */}
        <section class="ov-section">
          <h2 class="ov-section__title">{t('overview.widgets.title')}</h2>
          <div class="ov-widgets">
            <Card class="ov-widget">
              <div class="ov-widget__head">
                <span>{t('overview.widgets.paging.title')}</span>
                <Tip label={t('overview.widgets.paging.tip')} />
              </div>
              {pagingVal ? (
                <>
                  <div class="ov-widget__value tnum">
                    {fmtNumber(pagingVal.faults_per_token, { maximumFractionDigits: 1 })}
                    <small>{t('overview.widgets.paging.unit')}</small>
                  </div>
                  {typeof pagingVal.disk_mb_per_token === 'number' ? (
                    <div class="ov-widget__sub tnum">
                      {t('overview.widgets.paging.disk', {
                        mb: fmtNumber(pagingVal.disk_mb_per_token, { maximumFractionDigits: 3 }),
                      })}
                    </div>
                  ) : null}
                </>
              ) : (
                <div class="ov-widget__na">{t('overview.widgets.paging.idle')}</div>
              )}
            </Card>

            <Card class="ov-widget">
              <div class="ov-widget__head">
                <span>{t('overview.widgets.residency.title')}</span>
                <Tip label={t('overview.widgets.residency.tip')} />
              </div>
              {residency ? (
                <>
                  <div class="ov-widget__value tnum">
                    {fmtNumber((residency.resident_ratio ?? 0) * 100, { maximumFractionDigits: 0 })}
                    <small>%</small>
                  </div>
                  <div class="ov-widget__sub tnum">
                    {fmtNumber(residency.resident_gb ?? 0, { maximumFractionDigits: 1 })} /{' '}
                    {fmtNumber(residency.total_gb ?? 0, { maximumFractionDigits: 1 })} GB
                  </div>
                </>
              ) : (
                <div class="ov-widget__na">
                  {loaded.length === 0
                    ? t('overview.widgets.residency.noModel')
                    : t('overview.widgets.residency.unavailable')}
                </div>
              )}
            </Card>

            <Card class="ov-widget">
              <div class="ov-widget__head">
                <span>{t('overview.widgets.issues.title')}</span>
                <Tip label={t('overview.widgets.issues.tip')} />
              </div>
              <div class="ov-widget__value tnum">
                {fmtNumber(issues)}
                <small> {t('overview.widgets.issues.open')}</small>
              </div>
              <button class="ov-widget__link" onClick={() => navigate('issues')}>
                {t('overview.widgets.issues.viewAll')} →
              </button>
            </Card>
          </div>
        </section>
      </div>

      {/* ── Unload confirm ────────────────────────────────────── */}
      <Dialog
        open={unloadTarget.value !== null}
        onClose={() => (unloading.value ? undefined : (unloadTarget.value = null))}
        title={t('overview.models.unloadTitle')}
        size="sm"
        footer={
          <>
            <Button variant="ghost" disabled={unloading.value} onClick={() => (unloadTarget.value = null)}>
              {t('common.cancel')}
            </Button>
            <Button variant="danger" loading={unloading.value} onClick={doUnload}>
              {t('overview.models.unload')}
            </Button>
          </>
        }
      >
        <p class="dialog-text">{t('overview.models.unloadBody', { id: unloadTarget.value ?? '' })}</p>
      </Dialog>
    </div>
  )
}

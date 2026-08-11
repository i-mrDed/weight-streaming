/* 🏠 Overview (spec §9.1) — system status at a glance + shortcuts.
   Sources: /health + /v1/stats (polled 5s, visibility-aware), /v1/models,
   /v1/issues?status=open (via shell store). P5: the Activity feed now shows
   the five most recent generations from /v1/usage/history — real per-run
   telemetry (tok/s renders "–" when a path had no measurement, never a
   fabricated number), with an honest empty state before the first run. */
import { useEffect, useRef } from 'preact/hooks'
import { useSignal } from '@preact/signals'
import {
  Bug,
  FolderSearch,
  Gauge as GaugeIcon,
  HardDriveDownload,
  MemoryStick,
  MessageSquare,
  Plus,
  Server,
  XCircle,
  Zap,
} from 'lucide-preact'
import { Card } from '@/components/Card'
import { Button } from '@/components/Button'
import { Badge } from '@/components/Badge'
import { Drawer } from '@/components/Drawer'
import { EmptyState } from '@/components/EmptyState'
import { Dialog } from '@/components/Dialog'
import { Segmented } from '@/components/Segmented'
import { Tip } from '@/components/Tip'
import { Gauge } from '@/components/Gauge'
import { toast } from '@/components/Toast'
import { ApiError } from '@/core/api'
import { navigate } from '@/core/router'
import { t, fmtNumber, fmtRelative, relativeDay, locale } from '@/i18n'
import { createPoller, refreshOnFocus } from '@/core/poll'
import { fetchStats, type StatsPayload, type ModelStats } from '@/core/stats'
import { fetchUsageHistory, type UsageRecord } from '@/core/config'
import { fetchTieringStats, type TieringStats } from '@/core/tiering'
import { guessQuant, unloadModel } from '@/core/models'
import { health, models, serverVersion } from '@/core/store'
import { openIssueCount } from '@/core/issues'

function fmtDuration(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${sec}s`
  return `${sec}s`
}

function downloadBlob(name: string, content: string, type: string) {
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
}

/** Route history → Markdown table (evidence-export, same data as the JSON). */
function routesToMarkdown(st: TieringStats): string {
  const rows = st.recent
    .slice()
    .reverse()
    .map((e) => {
      const when = new Date(e.ts).toISOString()
      const meta = [
        e.model_id,
        e.prompt_chars != null ? `${e.prompt_chars} chars` : '',
        e.reused ? 'reused' : '',
      ].filter(Boolean).join(' · ')
      return `| ${e.tier} | ${when} | ${e.reason.replace(/\|/g, '\\|')} | ${meta} |`
    })
    .join('\n')
  return [
    '# Auto-tiering route history',
    '',
    `Exported: ${new Date().toISOString()} — ${st.total_routes} routes total`,
    '',
    '| tier | time (UTC) | reason | model · chars · reused |',
    '|---|---|---|---|',
    rows,
    '',
  ].join('\n')
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
  const activity = useSignal<UsageRecord[] | null>(null) // null = not fetched yet
  const tierStats = useSignal<TieringStats | null>(null) // null = not fetched yet
  const unreachable = useSignal(false)
  // Auto-tiering detail drawer — the card shows a summary; the drawer lists
  // every recorded route with a fast/quality filter.
  const tierDrawerOpen = useSignal(false)
  const tierFilter = useSignal<'all' | 'fast' | 'quality'>('all')
  const tierAll = useSignal<TieringStats | null>(null)
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
        // Independent fetches: a usage-history hiccup must not blank the
        // stats, and vice versa (both stay honest — last good value or empty).
        const [st, usage, tiers] = await Promise.allSettled([
          fetchStats(), fetchUsageHistory(5), fetchTieringStats(),
        ])
        if (st.status === 'fulfilled') stats.value = st.value
        if (usage.status === 'fulfilled') activity.value = usage.value.history.slice().reverse()
        if (tiers.status === 'fulfilled') tierStats.value = tiers.value
        unreachable.value = st.status === 'rejected'
      } catch {
        unreachable.value = true
      }
    }, 5000)
    poller.start()
    poller.kick()
    const beat = window.setInterval(() => (tick.value += 1), 1000)
    // Focus-refresh: the poller already catches up on visibility change, but
    // this guarantees stats+activity are fresh the moment the tab regains
    // focus instead of waiting for the next 5s tick.
    const offFocus = refreshOnFocus(async () => poller.kick())
    return () => {
      poller.stop()
      window.clearInterval(beat)
      offFocus()
    }
  }, [])

  const loaded = models.value
  const srv = stats.value?.server ?? null
  const hostPort = srv ? `${srv.host}:${srv.port}` : window.location.host
  const paging = pickPaging(stats.value)
  const pagingVal = paging?.ms.generation.paging
  // Latest generation speed (tok/s) across loaded models — honest "latest".
  const genSpeed = (() => {
    let latest: number | null = null
    let latestTs = 0
    for (const ms of Object.values(stats.value?.models ?? {})) {
      const g = ms.generation
      if (g && typeof g.tokens_per_sec === 'number') {
        const ts = g.elapsed ? Date.now() - g.elapsed * 1000 : 0
        if (ts >= latestTs) {
          latestTs = ts
          latest = g.tokens_per_sec
        }
      }
    }
    return latest
  })()
  const residency = (() => {
    for (const ms of Object.values(stats.value?.models ?? {})) {
      const pc = ms.page_cache
      // LlamaServerBackend sends page_cache:null — skip those models honestly
      if (pc != null && typeof pc.resident_ratio === 'number' && Object.keys(pc).length > 0) {
        return pc
      }
    }
    return null
  })()
  const issues = openIssueCount.value
  // heartbeat read → re-render every second so the uptime label ticks
  void tick.value

  const openTierDrawer = async () => {
    tierDrawerOpen.value = true
    tierFilter.value = 'all'
    try {
      tierAll.value = await fetchTieringStats(200)
    } catch {
      tierAll.value = tierStats.value // honest fallback: whatever the card has
    }
  }
  const tAll = tierAll.value // local capture — TS narrowing across signals
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
              <Button variant="ghost" onClick={() => navigate('hub')}>
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
        {/* ── Activity (P5: real usage history, newest 5) ───────── */}
        <section class="ov-section">
          <h2 class="ov-section__title">
            {t('overview.activity.title')}
            <Tip label={t('overview.activity.tip')} />
          </h2>
          <Card>
            {!activity.value || activity.value.length === 0 ? (
              <EmptyState emoji="📈" title={t('overview.activity.emptyTitle')} body={t('overview.activity.emptyBody')}>
                <Button variant="soft" onClick={() => navigate('chat')}>
                  <MessageSquare size={15} aria-hidden="true" /> {t('overview.quick.chat')}
                </Button>
              </EmptyState>
            ) : (
              <table class="ov-activity">
                <thead>
                  <tr>
                    <th>{t('overview.activity.colModel')}</th>
                    <th class="tnum">{t('overview.activity.colTokens')}</th>
                    <th class="tnum">{t('overview.activity.colSpeed')}</th>
                    <th>{t('overview.activity.colWhen')}</th>
                  </tr>
                </thead>
                <tbody>
                  {activity.value.map((rec) => (
                    <tr key={`${rec.ts}-${rec.model}`}>
                      <td class="ov-activity__model" title={rec.model}>
                        {rec.model}
                      </td>
                      <td class="tnum">{rec.tokens != null ? fmtNumber(rec.tokens) : '–'}</td>
                      {/* tok_s = null → honest "–", never a fabricated number */}
                      <td class="tnum">
                        {rec.tok_s != null ? fmtNumber(rec.tok_s, { maximumFractionDigits: 1 }) : '–'}
                      </td>
                      <td title={fmtRelative(rec.ts)}>{fmtRelative(rec.ts)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </section>

        {/* ── Auto-tiering stats (real route telemetry) ────────── */}
        <section class="ov-section">
          <h2 class="ov-section__title">
            ⚡ {t('overview.tiering.title')}
            <Tip label={t('overview.tiering.tip')} />
          </h2>
          <Card class="ov-tiering">
            {!tierStats.value ? (
              <p class="set-note">{t('common.loading')}</p>
            ) : !tierStats.value.enabled ? (
              <div class="ov-tiering__state">
                <Badge tone="neutral">{t('common.off')}</Badge>
                <span class="ov-tiering__note">{t('overview.tiering.disabled')}</span>
                <Button variant="soft" size="sm" onClick={() => navigate('settings')}>
                  {t('overview.tiering.openSettings')}
                </Button>
              </div>
            ) : tierStats.value.total_routes === 0 ? (
              <EmptyState
                emoji="⚡"
                title={t('overview.tiering.emptyTitle')}
                body={t('overview.tiering.emptyBody')}
              >
                <Button variant="soft" size="sm" onClick={() => navigate('chat')}>
                  <MessageSquare size={14} aria-hidden="true" /> {t('overview.quick.chat')}
                </Button>
              </EmptyState>
            ) : (
              <>
                <div class="ov-tiering__nums tnum">
                  <span class="ov-tiering__total">
                    {fmtNumber(tierStats.value.total_routes)}
                    <small> {t('overview.tiering.routes')}</small>
                  </span>
                  <span>⚡ {fmtNumber(tierStats.value.by_tier.fast ?? 0)}</span>
                  <span>🎯 {fmtNumber(tierStats.value.by_tier.quality ?? 0)}</span>
                </div>
                {tierStats.value.recent.length > 0 ? (
                  <ul class="ov-tiering__recent">
                    {tierStats.value.recent.slice(-3).reverse().map((e, i) => (
                      <li key={`${e.ts}-${i}`}>
                        <span class={`ov-tiering__tier ov-tiering__tier--${e.tier}`}>
                          {e.tier === 'fast' ? '⚡' : '🎯'}
                        </span>
                        <span class="ov-tiering__reason" title={e.reason}>{e.reason}</span>
                        {e.reused ? <Badge tone="info">{t('overview.tiering.reused')}</Badge> : null}
                        <span class="ov-tiering__when">{fmtRelative(e.ts)}</span>
                      </li>
                    ))}
                  </ul>
                ) : null}
                <Button variant="ghost" size="sm" onClick={() => void openTierDrawer()}>
                  {t('overview.tiering.viewAll')} →
                </Button>
              </>
            )}
          </Card>
        </section>

        {/* ── Health widgets ────────────────────────────────────── */}
        <section class="ov-section">
          <h2 class="ov-section__title">
            <GaugeIcon size={14} aria-hidden="true" /> {t('overview.widgets.title')}
          </h2>
          <div class="ov-widgets">
            <Gauge
              label={t('overview.widgets.genSpeed.title')}
              tip={t('overview.widgets.genSpeed.tip')}
              value={genSpeed}
              fraction={genSpeed != null ? Math.min(1, genSpeed / 20) : null}
              format={(n) => fmtNumber(n, { maximumFractionDigits: 1 })}
              unit="tok/s"
              tone="brand"
              idle={t('overview.widgets.genSpeed.idle')}
            />
            <Gauge
              label={t('overview.widgets.paging.title')}
              tip={t('overview.widgets.paging.tip')}
              value={pagingVal ? pagingVal.faults_per_token : null}
              fraction={pagingVal ? Math.min(1, pagingVal.faults_per_token / 1000) : null}
              format={(n) => fmtNumber(n, { maximumFractionDigits: 1 })}
              unit={t('overview.widgets.paging.unit')}
              tone="warn"
              idle={t('overview.widgets.paging.idle')}
            >
              {pagingVal && typeof pagingVal.disk_mb_per_token === 'number' ? (
                <div class="ov-widget__sub tnum">
                  {t('overview.widgets.paging.disk', {
                    mb: fmtNumber(pagingVal.disk_mb_per_token, { maximumFractionDigits: 3 }),
                  })}
                </div>
              ) : null}
            </Gauge>
            <Gauge
              label={t('overview.widgets.residency.title')}
              tip={t('overview.widgets.residency.tip')}
              value={residency ? (residency.resident_ratio ?? 0) * 100 : null}
              fraction={residency?.resident_ratio ?? null}
              format={(n) => fmtNumber(n, { maximumFractionDigits: 0 })}
              unit="%"
              tone="ok"
              idle={
                loaded.length === 0
                  ? t('overview.widgets.residency.noModel')
                  : t('overview.widgets.residency.unavailable')
              }
            >
              {residency ? (
                <div class="ov-widget__sub tnum">
                  {fmtNumber(residency.resident_gb ?? 0, { maximumFractionDigits: 1 })} /{' '}
                  {fmtNumber(residency.total_gb ?? 0, { maximumFractionDigits: 1 })} GB
                </div>
              ) : null}
            </Gauge>
            <Card class="ov-widget ov-widget--issues">
              <div class="ov-widget__head">
                <Bug size={13} aria-hidden="true" /> {t('overview.widgets.issues.title')}
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

      {/* ── Auto-tiering detail drawer ────────────────────────── */}
      <Drawer
        open={tierDrawerOpen.value}
        onClose={() => (tierDrawerOpen.value = false)}
        title={t('overview.tiering.drawerTitle')}
        side="right"
        width={520}
      >
        {!tAll ? (
          <p class="set-note">{t('common.loading')}</p>
        ) : (
          <>
            <div class="ov-tiering-drawer__toolbar">
              <Segmented
                ariaLabel={t('overview.tiering.drawerFilter')}
                size="sm"
                value={tierFilter.value}
                onChange={(v) => (tierFilter.value = v as 'all' | 'fast' | 'quality')}
                options={[
                  { value: 'all', label: t('overview.tiering.filterAll') },
                  { value: 'fast', label: `⚡ ${t('overview.tiering.filterFast')}` },
                  { value: 'quality', label: `🎯 ${t('overview.tiering.filterQuality')}` },
                ]}
              />
              <div class="ov-tiering-drawer__side">
                <span class="ov-tiering-drawer__count tnum">
                  {fmtNumber(tAll.total_routes)} {t('overview.tiering.routes')}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    downloadBlob(
                      `tiering-routes-${new Date().toISOString().slice(0, 10)}.json`,
                      JSON.stringify(
                        {
                          exported_at: new Date().toISOString(),
                          total_routes: tAll.total_routes,
                          by_tier: tAll.by_tier,
                          by_reason: tAll.by_reason,
                          events: tAll.recent,
                        },
                        null,
                        2,
                      ),
                      'application/json',
                    )
                  }
                >
                  {t('overview.tiering.exportJson')}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => downloadBlob(
                    `tiering-routes-${new Date().toISOString().slice(0, 10)}.md`,
                    routesToMarkdown(tAll),
                    'text/markdown',
                  )}
                >
                  {t('overview.tiering.exportMd')}
                </Button>
              </div>
            </div>
            {tAll.recent.length === 0 ? (
              <EmptyState emoji="⚡" title={t('overview.tiering.emptyTitle')} body={t('overview.tiering.emptyBody')} />
            ) : (
              <ul class="ov-tiering-drawer__list">
                {tAll.recent
                  .slice()
                  .reverse()
                  .filter((e) => tierFilter.value === 'all' || e.tier === tierFilter.value)
                  .map((e, i) => (
                    <li key={`${e.ts}-${i}`}>
                      <span class={`ov-tiering__tier ov-tiering__tier--${e.tier}`}>
                        {e.tier === 'fast' ? '⚡' : '🎯'}
                      </span>
                      <div class="ov-tiering-drawer__body">
                        <span class="ov-tiering__reason" title={e.reason}>{e.reason}</span>
                        <span class="ov-tiering-drawer__meta tnum">
                          {e.model_id}
                          {e.prompt_chars != null ? ` · ${fmtNumber(e.prompt_chars)} chars` : ''}
                          {e.reused ? ` · ${t('overview.tiering.reused')}` : ''}
                        </span>
                      </div>
                      <span class="ov-tiering__when">{fmtRelative(e.ts)}</span>
                    </li>
                  ))}
              </ul>
            )}
          </>
        )}
      </Drawer>

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

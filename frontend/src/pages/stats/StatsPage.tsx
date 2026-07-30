/* 📊 Live Stats (spec §9.3) — poll /v1/stats every 2s (visibility-aware,
   backoff via createPoller). 5 gauge cards with poll-over-poll deltas,
   two session-window charts (client ring buffer — NOT persistent history),
   paging detail, MoE heatmap with dense-model degrade, server block.
   Honest states everywhere: hit-rate stays its real 0 with a caveat
   (ADR-003), idle cards before the first generation. */
import { useEffect, useRef } from 'preact/hooks'
import { useSignal } from '@preact/signals'
import { ArrowRight, Gauge as GaugeIcon } from 'lucide-preact'
import { Card } from '@/components/Card'
import { Badge } from '@/components/Badge'
import { Button } from '@/components/Button'
import { EmptyState } from '@/components/EmptyState'
import { Gauge, type GaugeDelta } from '@/components/Gauge'
import { Sparkline } from '@/components/Sparkline'
import { Tip } from '@/components/Tip'
import { navigate } from '@/core/router'
import { createPoller } from '@/core/poll'
import { fetchStats, hasGeneration, type ModelStats, type StatsPayload } from '@/core/stats'
import { RingBuffer } from '@/core/ring'
import { statsFocusModel } from '@/core/nav-hints'
import { t, fmtNumber, locale } from '@/i18n'
import { Heatmap } from './Heatmap'

interface Snapshot {
  hitRate: number
  residency: number | null
  tokS: number | null
  prefetchAcc: number | null
  faults: number | null
}

function snapshotOf(ms: ModelStats | null): Snapshot | null {
  if (!ms) return null
  const pf = ms.prefetcher
  return {
    hitRate: ms.buffer.hit_rate,
    residency: Object.keys(ms.page_cache).length > 0 ? (ms.page_cache.resident_ratio ?? 0) : null,
    tokS: typeof ms.generation.tokens_per_sec === 'number' ? ms.generation.tokens_per_sec : null,
    prefetchAcc: pf.prefetched > 0 ? pf.useful / pf.prefetched : null,
    faults: typeof ms.generation.paging?.faults_per_token === 'number'
      ? ms.generation.paging.faults_per_token
      : null,
  }
}

function delta(cur: number | null, prev: number | null, digits: number, unit: string): GaugeDelta | null {
  if (cur === null || prev === null) return null
  const d = cur - prev
  if (Math.abs(d) < 10 ** -digits) return { label: `0 ${unit}`, dir: 'flat' }
  return {
    label: `${d > 0 ? '+' : ''}${fmtNumber(d, { maximumFractionDigits: digits })} ${unit}`,
    dir: d > 0 ? 'up' : 'down',
  }
}

const pct = (n: number) => fmtNumber(n, { maximumFractionDigits: 1 })

export function StatsPage() {
  locale.value // resubscribe on language switch
  const payload = useSignal<StatsPayload | null>(null)
  const selected = useSignal<string>('')
  const ringTick = useSignal(0) // bump to redraw charts
  const prevRef = useRef<Snapshot | null>(null)
  const chartModelRef = useRef<string>('')
  const faultSourceRef = useRef<'faults' | 'disk'>('faults')
  const tokRing = useRef(new RingBuffer<number>(300))
  const faultRing = useRef(new RingBuffer<number>(300))

  // Consume the "view stats" hint from the Models page once.
  if (statsFocusModel.value && selected.value === '') {
    selected.value = statsFocusModel.value
    statsFocusModel.value = ''
  }

  useEffect(() => {
    const poller = createPoller(async () => {
      payload.value = await fetchStats()
    }, 2000)
    poller.start()
    poller.kick()
    return () => poller.stop()
  }, [])

  const modelIds = Object.keys(payload.value?.models ?? {})
  const effective: string =
    (selected.value && modelIds.includes(selected.value) ? selected.value : '') ||
    modelIds.find((id) => hasGeneration(payload.value?.models[id])) ||
    modelIds[0] ||
    ''
  const ms: ModelStats | null = payload.value?.models[effective] ?? null
  const srv = payload.value?.server ?? null

  // Feed the ring buffers + delta baseline after each poll.
  useEffect(() => {
    if (!ms) return
    if (chartModelRef.current !== effective) {
      chartModelRef.current = effective
      tokRing.current.clear()
      faultRing.current.clear()
      prevRef.current = null
      faultSourceRef.current = 'faults'
    }
    const snap = snapshotOf(ms)
    if (snap?.tokS != null) tokRing.current.push(snap.tokS)
    const paging = ms.generation.paging
    if (paging) {
      const source: 'faults' | 'disk' =
        typeof paging.faults_per_token === 'number' && paging.faults_per_token > 0 ? 'faults' : 'disk'
      if (source !== faultSourceRef.current) {
        faultSourceRef.current = source
        faultRing.current.clear()
      }
      const v = source === 'faults' ? paging.faults_per_token : (paging.disk_mb_per_token ?? null)
      if (v !== null) faultRing.current.push(v)
    }
    prevRef.current = snap
    ringTick.value += 1
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [payload.value, effective])

  // ── No models at all → designed empty state ────────────────────
  if (payload.value && modelIds.length === 0) {
    return (
      <div class="page">
        <PageTitle />
        <Card>
          <EmptyState emoji="🧠" title={t('stats.empty.title')} body={t('stats.empty.body')}>
            <Button variant="primary" onClick={() => navigate('models')}>
              {t('stats.empty.goModels')}
            </Button>
          </EmptyState>
        </Card>
      </div>
    )
  }

  const prev = prevRef.current
  const cur = snapshotOf(ms)
  const idle = !hasGeneration(ms ?? undefined)
  const tokMax = Math.max(10, ...tokRing.current.items())
  const faultMax = Math.max(1, ...faultRing.current.items())
  const paging = ms?.generation.paging
  const anyEver = modelIds.some((id) => hasGeneration(payload.value?.models[id]))

  return (
    <div class="page">
      <PageTitle />

      {/* model selector strip */}
      <div class="st-picker" role="radiogroup" aria-label={t('stats.pickModel')}>
        {modelIds.map((id) => (
          <button
            key={id}
            role="radio"
            aria-checked={id === effective}
            class={`st-picker__opt${id === effective ? ' is-on' : ''}`}
            onClick={() => (selected.value = id)}
          >
            {id}
          </button>
        ))}
      </div>

      {/* first-generation idle banner */}
      {idle ? (
        <Card tier="raised" class="st-idle">
          <GaugeIcon size={17} aria-hidden="true" />
          <div>
            <div class="st-idle__title">{t('stats.idle.title')}</div>
            <div class="st-idle__body">{t('stats.idle.body')}</div>
          </div>
          <Button variant="soft" size="sm" onClick={() => navigate('chat')}>
            {t('stats.idle.goChat')} <ArrowRight size={14} aria-hidden="true" />
          </Button>
        </Card>
      ) : null}

      {/* ── Gauge cards ─────────────────────────────────────────── */}
      <div class="st-gauges">
        <Gauge
          label={t('stats.gauge.hitRate')}
          tip={t('stats.gauge.hitRateTip')}
          value={cur ? cur.hitRate * 100 : null}
          fraction={cur ? cur.hitRate : null}
          format={pct}
          unit="%"
          tone="info"
          delta={delta(cur?.hitRate != null ? cur.hitRate * 100 : null, prev?.hitRate != null ? prev.hitRate * 100 : null, 1, 'pp')}
          caveat={<span class="st-caveat">{t('stats.gauge.hitRateCaveat')}</span>}
          idle={t('common.notAvailable')}
        />
        <Gauge
          label={t('stats.gauge.residency')}
          tip={t('stats.gauge.residencyTip')}
          value={cur?.residency != null ? cur.residency * 100 : null}
          fraction={cur?.residency ?? null}
          format={pct}
          unit="%"
          tone="ok"
          delta={delta(cur?.residency != null ? cur.residency * 100 : null, prev?.residency != null ? prev.residency * 100 : null, 1, 'pp')}
          idle={t('stats.gauge.residencyNa')}
        />
        <Gauge
          label={t('stats.gauge.speed')}
          tip={t('stats.gauge.speedTip')}
          value={cur?.tokS ?? null}
          fraction={cur?.tokS != null ? Math.min(1, cur.tokS / tokMax) : null}
          format={(n) => fmtNumber(n, { maximumFractionDigits: 1 })}
          unit="tok/s"
          tone="brand"
          delta={delta(cur?.tokS ?? null, prev?.tokS ?? null, 1, 'tok/s')}
          idle={t('stats.gauge.noGeneration')}
        />
        <Gauge
          label={t('stats.gauge.prefetch')}
          tip={t('stats.gauge.prefetchTip')}
          value={cur?.prefetchAcc != null ? cur.prefetchAcc * 100 : null}
          fraction={cur?.prefetchAcc ?? null}
          format={pct}
          unit="%"
          tone="warn"
          delta={delta(
            cur?.prefetchAcc != null ? cur.prefetchAcc * 100 : null,
            prev?.prefetchAcc != null ? prev.prefetchAcc * 100 : null,
            1,
            'pp',
          )}
          idle={t('stats.gauge.prefetchNa')}
        />
        <Gauge
          label={t('stats.gauge.paging')}
          tip={t('stats.gauge.pagingTip')}
          value={cur?.faults ?? null}
          fraction={cur?.faults != null ? Math.min(1, cur.faults / faultMax) : null}
          format={(n) => fmtNumber(n, { maximumFractionDigits: 1 })}
          unit={t('stats.gauge.pagingUnit')}
          tone="error"
          delta={delta(cur?.faults ?? null, prev?.faults ?? null, 1, '')}
          idle={t('stats.gauge.noGeneration')}
        />
      </div>

      {/* ── Charts (client ring buffer — session window) ────────── */}
      <div class="st-charts">
        <Card>
          <div class="st-chart-head">
            <h2>{t('stats.chart.tokTitle')}</h2>
            <span class="st-window">{t('stats.chart.window')}</span>
          </div>
          <Sparkline data={tokRing.current.items()} unit="tok/s" cssVar="--ws-accent-brand" />
        </Card>
        <Card>
          <div class="st-chart-head">
            <h2>
              {faultSourceRef.current === 'faults' ? t('stats.chart.faultTitle') : t('stats.chart.diskTitle')}
            </h2>
            <span class="st-window">{t('stats.chart.window')}</span>
          </div>
          <Sparkline
            data={faultRing.current.items()}
            unit={faultSourceRef.current === 'faults' ? t('stats.gauge.pagingUnit') : 'MB/tok'}
            cssVar="--ws-status-warn"
            format={(n) => fmtNumber(n, { maximumFractionDigits: 2 })}
          />
        </Card>
      </div>

      <div class="st-bottom">
        {/* ── Paging demand detail ──────────────────────────────── */}
        <Card class="st-paging">
          <div class="st-card-head">
            <h2>{t('stats.paging.title')}</h2>
            <Tip label={t('stats.paging.tip')} />
          </div>
          {paging ? (
            <dl class="st-paging__list">
              <div>
                <dt>{t('stats.paging.faults')}</dt>
                <dd class="tnum">{fmtNumber(paging.faults)}</dd>
              </div>
              <div>
                <dt>{t('stats.paging.perToken')}</dt>
                <dd class="tnum">{fmtNumber(paging.faults_per_token, { maximumFractionDigits: 1 })}</dd>
              </div>
              <div>
                <dt>{t('stats.paging.hard')}</dt>
                <dd class="tnum">
                  {typeof paging.hard_faults === 'number' ? (
                    fmtNumber(paging.hard_faults)
                  ) : (
                    <span class="st-na">{t('stats.paging.hardNa')}</span>
                  )}
                </dd>
              </div>
              <div>
                <dt>{t('stats.paging.disk')}</dt>
                <dd class="tnum">
                  {typeof paging.disk_mb_per_token === 'number' ? (
                    <>
                      {fmtNumber(paging.disk_mb_per_token, { maximumFractionDigits: 3 })} MB/tok
                      {paging.disk_demand_source ? (
                        <Badge tone={paging.disk_demand_source === 'major_faults' ? 'info' : 'neutral'} class="st-paging__src">
                          {paging.disk_demand_source === 'major_faults'
                            ? t('stats.paging.srcFaults')
                            : t('stats.paging.srcResidency')}
                        </Badge>
                      ) : null}
                    </>
                  ) : (
                    <span class="st-na">{t('common.notAvailable')}</span>
                  )}
                </dd>
              </div>
            </dl>
          ) : (
            <p class="st-paging__none">{idle ? t('stats.paging.idle') : t('stats.paging.unavailable')}</p>
          )}
          {paging?.note ? <p class="st-paging__note">{paging.note}</p> : null}
        </Card>

        {/* ── MoE heatmap ───────────────────────────────────────── */}
        <Card class="st-heat">
          <div class="st-card-head">
            <h2>{t('stats.heatmap.title')}</h2>
            <Tip label={t('stats.heatmap.tip')} />
          </div>
          <Heatmap
            nExperts={ms?.model.n_experts ?? 0}
            activeExperts={Array.isArray((ms as unknown as Record<string, unknown>)?.active_experts)
              ? ((ms as unknown as Record<string, unknown>).active_experts as number[])
              : null}
          />
        </Card>

        {/* ── Server block ──────────────────────────────────────── */}
        <Card class="st-server">
          <div class="st-card-head">
            <h2>{t('stats.server.title')}</h2>
          </div>
          {srv ? (
            <dl class="st-paging__list">
              <div>
                <dt>{t('stats.server.models')}</dt>
                <dd class="tnum">{srv.models_loaded}/{srv.max_models}</dd>
              </div>
              <div>
                <dt>{t('stats.server.host')}</dt>
                <dd class="tnum">{srv.host}:{srv.port}</dd>
              </div>
              <div>
                <dt>{t('stats.server.priority')}</dt>
                <dd>
                  <Badge tone={srv.priority?.lowered ? 'info' : 'neutral'}>
                    {srv.priority?.lowered ? t('overview.hero.priorityLow') : t('overview.hero.priorityNormal')}
                  </Badge>
                </dd>
              </div>
              <div>
                <dt>{t('stats.server.queue')}</dt>
                <dd class="tnum">{srv.queue_depth}</dd>
              </div>
            </dl>
          ) : (
            <p class="st-paging__none">{t('common.loading')}</p>
          )}
          {!anyEver ? <p class="st-server__hint">{t('stats.idle.body')}</p> : null}
        </Card>
      </div>
    </div>
  )
}

function PageTitle() {
  return (
    <header class="page__header">
      <h1 class="page__title">
        <span aria-hidden="true">📊</span> {t('nav.stats')}
      </h1>
    </header>
  )
}

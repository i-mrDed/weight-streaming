/* 🌐 Hub — Model detail drawer (P5.1, feedback #2).
   A decision-making guide in two tiers:
     • Quick guide — category, real published/updated dates, downloads,
       parameter size, approx RAM per quant COMPUTED FROM REAL bytes,
       context length (only when HF truly gives it), feature hints from tags,
       short description.
     • Full detail — every tag, base model, every file with its byte size and
       shard info.
   Honest telemetry (ADR-003): HF does NOT publish benchmarks / strengths /
   weaknesses, so we never invent them — a truthful note says exactly that.
   Any missing datum renders as n/a with a short reason.

   Drawer side = RIGHT: its trigger (the card "details" action) sits on the
   right edge of a card, so per the Drawer CONVENTION it slides from the right. */
import {
  Calendar,
  Cpu,
  Download,
  ExternalLink,
  FileBox,
  HardDrive,
  Heart,
  Layers,
  RefreshCw,
} from 'lucide-preact'
import { ApiError } from '@/core/api'
import {
  fmtBytes,
  hfRepoUrl,
  isUnquantized,
  modelCategory,
  modelFeatures,
  repoAuthor,
  repoName,
  type HubModelDetail,
} from '@/core/hub'
import { Badge } from '@/components/Badge'
import { Button } from '@/components/Button'
import { Drawer } from '@/components/Drawer'
import { Tip } from '@/components/Tip'
import { fmtDateTime, fmtNumber, t } from '@/i18n'

interface DetailError {
  status?: number
  detail: string
}

interface Props {
  open: boolean
  onClose: () => void
  detail: HubModelDetail | null
  loading: boolean
  error: DetailError | null
  onRetry: () => void
}

function toMs(iso: string | null): number | null {
  if (!iso) return null
  const ms = new Date(iso).getTime()
  return Number.isFinite(ms) ? ms : null
}

export function ModelDetailDrawer({ open, onClose, detail, loading, error, onRetry }: Props) {
  const title = detail ? repoName(detail.repo_id) : t('hub.detailTitle')
  const offline = error?.status === 502 || error?.status === 503

  return (
    <Drawer open={open} onClose={onClose} title={title} side="right" width={440}>
      {loading && !detail ? (
        <div class="hd-state">
          <span class="btn__spinner" aria-hidden="true" />
          <p class="dialog-text--dim">{t('hub.detailLoading')}</p>
        </div>
      ) : error && !detail ? (
        <div class="hd-state">
          <p class="hd-state__title">{offline ? t('hub.detailOffline') : t('hub.detailError')}</p>
          <p class="dialog-text--dim">{error.detail}</p>
          <Button variant="soft" size="sm" onClick={onRetry}>
            <RefreshCw size={13} aria-hidden="true" /> {t('common.retry')}
          </Button>
        </div>
      ) : detail ? (
        <DetailBody detail={detail} />
      ) : null}
    </Drawer>
  )
}

function DetailBody({ detail }: { detail: HubModelDetail }) {
  const cat = modelCategory(detail.pipeline_tag, detail.tags)
  const features = modelFeatures(detail.tags)
  const author = detail.author ?? repoAuthor(detail.repo_id)
  const published = toMs(detail.published_at)
  const updated = toMs(detail.updated_at)
  const paramSize = detail.files.find((f) => f.size_label)?.size_label ?? null
  const baseModel = Array.isArray(detail.base_model)
    ? detail.base_model.join(', ')
    : detail.base_model

  return (
    <div class="hd">
      {/* header: name · author · category chip · link */}
      <div class="hd__head">
        <span class={`hub-cat hub-cat--${cat.id}`} title={t(cat.labelKey)}>
          <span aria-hidden="true">{cat.emoji}</span> {t(cat.labelKey)}
        </span>
        <a
          class="hd__ext"
          href={hfRepoUrl(detail.repo_id)}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`${detail.repo_id} — huggingface.co`}
        >
          <ExternalLink size={13} aria-hidden="true" /> huggingface.co
        </a>
      </div>
      {author ? <div class="hd__author dialog-text--dim">{author}</div> : null}

      {/* ── Quick guide ─────────────────────────────────────── */}
      <section class="hd__section">
        <h3 class="hd__section-title">{t('hub.quickGuide')}</h3>

        <dl class="hd-stats">
          <div class="hd-stat">
            <dt>
              <Calendar size={13} aria-hidden="true" /> {t('hub.published')}
            </dt>
            <dd class="tnum">{published ? fmtDateTime(published) : t('hub.na')}</dd>
          </div>
          <div class="hd-stat">
            <dt>
              <Calendar size={13} aria-hidden="true" /> {t('hub.updatedLabel')}
            </dt>
            <dd class="tnum">{updated ? fmtDateTime(updated) : t('hub.na')}</dd>
          </div>
          <div class="hd-stat">
            <dt>
              <Download size={13} aria-hidden="true" /> {t('hub.downloads')}
            </dt>
            <dd class="tnum">{detail.downloads != null ? fmtNumber(detail.downloads) : t('hub.na')}</dd>
          </div>
          {detail.likes != null ? (
            <div class="hd-stat">
              <dt>
                <Heart size={13} aria-hidden="true" /> {t('hub.likes')}
              </dt>
              <dd class="tnum">{fmtNumber(detail.likes)}</dd>
            </div>
          ) : null}
          <div class="hd-stat">
            <dt>
              <Cpu size={13} aria-hidden="true" /> {t('hub.paramSize')}
            </dt>
            <dd>{paramSize ?? t('hub.na')}</dd>
          </div>
          <div class="hd-stat">
            <dt>
              <Layers size={13} aria-hidden="true" /> {t('hub.contextLen')}
            </dt>
            <dd class="tnum">
              {detail.context_length != null ? (
                fmtNumber(detail.context_length)
              ) : (
                <span class="hd-na" title={t('hub.contextNaHint')}>
                  {t('hub.contextNa')}
                </span>
              )}
            </dd>
          </div>
        </dl>

        {/* Approx RAM per quant — computed from REAL file bytes (honest) */}
        {detail.quants.length > 0 ? (
          <div class="hd-field">
            <div class="hd-field__label">
              <HardDrive size={13} aria-hidden="true" /> {t('hub.ramPerQuant')}
              <Tip label={t('hub.ramHint')} />
            </div>
            <ul class="hd-ram">
              {detail.quants.map((q) => (
                <li key={q.quant ?? 'unknown'} class="hd-ram__row">
                  <Badge tone={isUnquantized(q.quant) ? 'warn' : 'brand'}>
                    {q.quant ?? t('hub.noQuant')}
                  </Badge>
                  <span class="hd-ram__size tnum">{fmtBytes(q.total_bytes)}</span>
                  {q.sharded ? (
                    <span class="hd-ram__shard">{t('hub.shardCount', { n: q.files.length })}</span>
                  ) : null}
                  {isUnquantized(q.quant) ? (
                    <span class="hd-ram__fp16">{t('hub.fp16Label')}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {/* feature hints from tags */}
        {features.length > 0 ? (
          <div class="hd-field">
            <div class="hd-field__label">{t('hub.features')}</div>
            <div class="hd-badges">
              {features.map((key) => (
                <Badge key={key} tone="info">
                  {t(key)}
                </Badge>
              ))}
            </div>
          </div>
        ) : null}

        {/* short description — from cardData only, never invented */}
        <div class="hd-field">
          <div class="hd-field__label">{t('hub.description')}</div>
          {detail.description ? (
            <p class="hd-desc">{detail.description}</p>
          ) : (
            <p class="hd-desc hd-desc--empty">{t('hub.noDescription')}</p>
          )}
        </div>

        {/* honest anti-hallucination note */}
        <p class="hd-bench-note">
          <Tip label={t('hub.perfNa')} /> {t('hub.perfNa')}
        </p>
      </section>

      {/* ── Full detail ─────────────────────────────────────── */}
      <section class="hd__section">
        <h3 class="hd__section-title">{t('hub.fullDetail')}</h3>

        {baseModel ? (
          <div class="hd-field">
            <div class="hd-field__label">{t('hub.baseModel')}</div>
            <p class="hd-base">{baseModel}</p>
          </div>
        ) : null}

        <div class="hd-field">
          <div class="hd-field__label">
            <FileBox size={13} aria-hidden="true" /> {t('hub.allTags')}
          </div>
          {detail.tags.length > 0 ? (
            <div class="hd-badges">
              {detail.tags.map((tag) => (
                <Badge key={tag} tone="neutral">
                  {tag}
                </Badge>
              ))}
            </div>
          ) : (
            <p class="hd-desc hd-desc--empty">{t('hub.na')}</p>
          )}
        </div>

        <div class="hd-field">
          <div class="hd-field__label">
            {t('hub.fileList', { count: detail.files.length + detail.non_gguf.length })}
          </div>
          <ul class="hd-filelist">
            {detail.files.map((f) => (
              <li key={f.filename} class="hd-file">
                <span class="hd-file__name" title={f.filename}>
                  {f.filename}
                </span>
                <span class="hd-file__right">
                  {f.shard ? (
                    <span class="hd-file__shard">
                      {f.shard.index}/{f.shard.total}
                    </span>
                  ) : null}
                  <span class="tnum">{fmtBytes(f.bytes)}</span>
                </span>
              </li>
            ))}
            {detail.non_gguf.map((f) => (
              <li key={f.filename} class="hd-file hd-file--other">
                <span class="hd-file__name" title={f.filename}>
                  {f.filename}
                </span>
                <span class="hd-file__right tnum">{fmtBytes(f.bytes)}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  )
}

// re-export for callers that want to type their error state consistently
export type { DetailError as HubDetailError }
export function detailErrorMessage(e: unknown): DetailError {
  return {
    status: e instanceof ApiError ? e.status : undefined,
    detail: e instanceof ApiError && e.detail ? e.detail : String(e),
  }
}

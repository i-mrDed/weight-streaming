/* 🌐 Hub — File picker drawer, rebuilt (P5.1, feedback #4 + #5).
   Now fed by the on-demand detail endpoint (lazy-fetched on open), so every
   file shows its REAL byte size and files are grouped BY QUANT:
     • a sharded quant reads as one unit — "ต้องใช้พร้อมกัน N ส่วน", each
       part's size, the total, and a single "download all N" action that
       queues every shard sequentially;
     • a single-file quant gets one download button;
     • F16/BF16/F32 are labelled as unquantized (very large);
     • non-GGUF files (README/imatrix) are listed separately with sizes but
       no download (the server only accepts .gguf).
   Downloads are repo-level only — HF gives no per-file counts, so we never
   show any. A caption explains card-groups-by-quant vs sidebar-lists-all.

   Drawer side = RIGHT (trigger sits on the right of each card). */
import { Download, ExternalLink, FolderOpen, Layers, RefreshCw } from 'lucide-preact'
import {
  fmtBytes,
  hfRepoUrl,
  isUnquantized,
  type HubDetailFile,
  type HubModelDetail,
} from '@/core/hub'
import { Badge } from '@/components/Badge'
import { Button } from '@/components/Button'
import { Drawer } from '@/components/Drawer'
import { Tip } from '@/components/Tip'
import { fmtNumber, t } from '@/i18n'

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
  modelsDirs: string[]
  targetDir: string
  onTargetDir: (v: string) => void
  onBrowse: () => void
  onDownloadFile: (repoId: string, filename: string) => void
  onDownloadGroup: (repoId: string, files: HubDetailFile[]) => void
}

export function FilesDrawer({
  open,
  onClose,
  detail,
  loading,
  error,
  onRetry,
  modelsDirs,
  targetDir,
  onTargetDir,
  onBrowse,
  onDownloadFile,
  onDownloadGroup,
}: Props) {
  const offline = error?.status === 502 || error?.status === 503

  return (
    <Drawer open={open} onClose={onClose} title={t('hub.filesTitle')} side="right" width={440}>
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
        <div class="hub-files">
          <div class="hf-repohead">
            <a href={hfRepoUrl(detail.repo_id)} target="_blank" rel="noopener noreferrer">
              {detail.repo_id} <ExternalLink size={11} aria-hidden="true" />
            </a>
            <span class="hf-repohead__dl tnum" title={t('hub.repoDownloads')}>
              <Download size={12} aria-hidden="true" />{' '}
              {detail.downloads != null ? fmtNumber(detail.downloads) : t('hub.na')}
            </span>
          </div>

          {/* card vs sidebar — honest explanation of the two views */}
          <p class="hf-caption">
            {t('hub.filesSummary', {
              files: detail.files.length + detail.non_gguf.length,
              quants: detail.quants.length,
            })}
            <Tip label={t('hub.filesGroupHint')} />
          </p>
          <p class="dialog-text--dim hf-perfile">{t('hub.perFileNa')}</p>

          {/* target dir (unchanged server guard — allowed folders only) */}
          <label class="set-field hub-files__dir">
            <span>
              {t('hub.targetDir')} <Tip label={t('hub.targetDirHint')} />
            </span>
            <select
              class="md-input md-select"
              value={targetDir}
              onChange={(e) => onTargetDir((e.target as HTMLSelectElement).value)}
            >
              <option value="">{t('hub.targetDefault')}</option>
              {modelsDirs.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
          <Button variant="ghost" size="sm" onClick={onBrowse}>
            <FolderOpen size={13} aria-hidden="true" /> {t('hub.targetBrowse')}
          </Button>

          {/* quant groups */}
          <div class="hf-groups">
            {detail.quants.map((q) => {
              const fp16 = isUnquantized(q.quant)
              return (
                <div key={q.quant ?? 'unknown'} class={`hf-quant${fp16 ? ' hf-quant--fp16' : ''}`}>
                  <div class="hf-quant__head">
                    <Badge tone={fp16 ? 'warn' : 'brand'}>{q.quant ?? t('hub.noQuant')}</Badge>
                    <span class="hf-quant__total tnum">{fmtBytes(q.total_bytes)}</span>
                    {fp16 ? <span class="hf-fp16">{t('hub.fp16Label')}</span> : null}
                  </div>
                  {q.sharded ? (
                    <p class="hf-shard-note">
                      <Layers size={12} aria-hidden="true" />{' '}
                      {t('hub.shardNeedsAll', { n: q.files.length })}
                    </p>
                  ) : null}
                  <ul class="hf-filelist">
                    {q.files.map((f) => (
                      <li key={f.filename} class="hf-file">
                        <span class="hf-file__name" title={f.filename}>
                          {f.filename}
                        </span>
                        <span class="hf-file__meta">
                          {f.shard ? (
                            <span class="hf-file__shard">
                              {f.shard.index}/{f.shard.total}
                            </span>
                          ) : null}
                          <span class="tnum">{fmtBytes(f.bytes)}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                  <div class="hf-quant__actions">
                    {q.sharded ? (
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={() => onDownloadGroup(detail.repo_id, q.files)}
                      >
                        <Download size={13} aria-hidden="true" />{' '}
                        {t('hub.downloadAll', { n: q.files.length })}
                      </Button>
                    ) : (
                      q.files.map((f) => (
                        <Button
                          key={f.filename}
                          variant="soft"
                          size="sm"
                          aria-label={`${t('hub.download')} ${f.filename}`}
                          onClick={() => onDownloadFile(detail.repo_id, f.filename)}
                        >
                          <Download size={13} aria-hidden="true" /> {t('hub.download')}
                        </Button>
                      ))
                    )}
                  </div>
                </div>
              )
            })}
          </div>

          {/* non-GGUF files — sizes shown, no download (server accepts .gguf only) */}
          {detail.non_gguf.length > 0 ? (
            <div class="hf-other">
              <div class="hf-other__label">{t('hub.nonGguf')}</div>
              <ul class="hf-filelist">
                {detail.non_gguf.map((f) => (
                  <li key={f.filename} class="hf-file hf-file--other">
                    <span class="hf-file__name" title={f.filename}>
                      {f.filename}
                    </span>
                    <span class="hf-file__meta tnum">{fmtBytes(f.bytes)}</span>
                  </li>
                ))}
              </ul>
              <p class="dialog-text--dim hf-other__note">{t('hub.nonGgufNote')}</p>
            </div>
          ) : null}
        </div>
      ) : null}
    </Drawer>
  )
}

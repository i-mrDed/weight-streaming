/* 🐛 Issues (spec §9.5) — full report lifecycle on the PRE-EXISTING issues
   backend (no new endpoints in P3). Toolbar (search + status/severity filter
   + sort + export + new report), severity summary chips, card list, detail
   drawer (maintainer matrix + verify flow) and the report modal. Empty state
   is honest; markdown is rendered through the XSS-safe pipeline. */
import { useEffect } from 'preact/hooks'
import { useSignal } from '@preact/signals'
import { Bug, Download, FileJson, FileText, Plus, Search } from 'lucide-preact'
import { Badge } from '@/components/Badge'
import { Button } from '@/components/Button'
import { Card } from '@/components/Card'
import { EmptyState } from '@/components/EmptyState'
import { Menu } from '@/components/Menu'
import { toast } from '@/components/Toast'
import {
  downloadText,
  exportIssues,
  ISSUE_STATUSES,
  listIssues,
  SEVERITIES,
  SEVERITY_TONE,
  STATUS_EMOJI,
  STATUS_TONE,
  type Issue,
  type IssueStatus,
  type Severity,
} from '@/core/issues'
import { locale, relativeDay, t } from '@/i18n'
import { IssueDrawer } from './IssueDrawer'
import { ReportModal } from './ReportModal'

type SortKey = 'newest' | 'oldest' | 'severity'
const SEV_RANK: Record<Severity, number> = { critical: 3, high: 2, medium: 1, low: 0 }

function ts(s: string): number {
  const n = Date.parse(s)
  return Number.isNaN(n) ? 0 : n
}

export function IssuesPage() {
  locale.value // re-render on language change
  const issues = useSignal<Issue[]>([])
  const loading = useSignal(false)
  const error = useSignal('')

  const search = useSignal('')
  const statusFilter = useSignal<IssueStatus | ''>('')
  const sevFilter = useSignal<Severity | ''>('')
  const sort = useSignal<SortKey>('newest')

  const reportOpen = useSignal(false)
  const openId = useSignal<string | null>(null)

  const load = async () => {
    loading.value = true
    error.value = ''
    try {
      const list = await listIssues({
        status: (statusFilter.value || undefined) as IssueStatus | undefined,
        severity: (sevFilter.value || undefined) as Severity | undefined,
      })
      issues.value = Array.isArray(list) ? list : []
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      issues.value = []
    } finally {
      loading.value = false
    }
  }

  useEffect(() => {
    void load()
  }, [statusFilter.value, sevFilter.value])

  // severity counts over the (server-filtered) list — honest zeros included.
  const sevCounts = SEVERITIES.map((s) => ({ s, n: issues.value.filter((i) => i.severity === s).length }))

  const visible = issues.value
    .filter((i) => {
      const q = search.value.trim().toLowerCase()
      if (!q) return true
      return (i.title + ' ' + i.id + ' ' + i.description).toLowerCase().includes(q)
    })
    .slice()
    .sort((a, b) => {
      if (sort.value === 'severity') return SEV_RANK[b.severity] - SEV_RANK[a.severity] || ts(b.created_at) - ts(a.created_at)
      if (sort.value === 'oldest') return ts(a.created_at) - ts(b.created_at)
      return ts(b.created_at) - ts(a.created_at)
    })

  const onExport = async (format: 'md' | 'json') => {
    try {
      const content = await exportIssues(format)
      const filename = format === 'json' ? 'issues.json' : 'issues.md'
      downloadText(filename, content, format === 'json' ? 'application/json' : 'text/markdown')
      const count = format === 'json' ? JSON.parse(content || '[]').length : issues.value.length
      toast('success', t('issues.toast.exported', { count }))
    } catch (e) {
      toast('error', t('issues.toast.exportFailed'), { body: e instanceof Error ? e.message : String(e) })
    }
  }

  const toggleSev = (s: Severity) => (sevFilter.value = sevFilter.value === s ? '' : s)

  return (
    <div class="page">
      <header class="page__header">
        <h1 class="page__title">
          <span aria-hidden="true">🐛</span> {t('nav.issues')}
        </h1>
      </header>

      {/* toolbar */}
      <div class="iss-toolbar">
        <div class="iss-toolbar__search">
          <Search size={14} aria-hidden="true" />
          <input
            class="md-input"
            type="search"
            placeholder={t('issues.toolbar.search')}
            value={search.value}
            onInput={(e) => (search.value = (e.target as HTMLInputElement).value)}
            aria-label={t('issues.toolbar.search')}
          />
        </div>

        <label class="iss-filter">
          <span class="sr-only">{t('issues.toolbar.filterStatus')}</span>
          <select
            class="md-input md-select"
            value={statusFilter.value}
            onChange={(e) => (statusFilter.value = (e.target as HTMLSelectElement).value as IssueStatus | '')}
            aria-label={t('issues.toolbar.filterStatus')}
          >
            <option value="">{t('issues.toolbar.allStatus')}</option>
            {ISSUE_STATUSES.map((s) => (
              <option key={s} value={s}>
                {STATUS_EMOJI[s]} {t(`issues.status.${s}`)}
              </option>
            ))}
          </select>
        </label>

        <label class="iss-filter">
          <span class="sr-only">{t('issues.toolbar.filterSeverity')}</span>
          <select
            class="md-input md-select"
            value={sevFilter.value}
            onChange={(e) => (sevFilter.value = (e.target as HTMLSelectElement).value as Severity | '')}
            aria-label={t('issues.toolbar.filterSeverity')}
          >
            <option value="">{t('issues.toolbar.allSeverity')}</option>
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {t(`issues.severity.${s}`)}
              </option>
            ))}
          </select>
        </label>

        <label class="iss-filter">
          <span class="sr-only">{t('issues.toolbar.sort')}</span>
          <select
            class="md-input md-select"
            value={sort.value}
            onChange={(e) => (sort.value = (e.target as HTMLSelectElement).value as SortKey)}
            aria-label={t('issues.toolbar.sort')}
          >
            <option value="newest">{t('issues.toolbar.sortNewest')}</option>
            <option value="oldest">{t('issues.toolbar.sortOldest')}</option>
            <option value="severity">{t('issues.toolbar.sortSeverity')}</option>
          </select>
        </label>

        <Menu
          ariaLabel={t('issues.toolbar.export')}
          align="end"
          trigger={
            <span class="chat__model-trigger">
              <Download size={14} aria-hidden="true" /> {t('issues.toolbar.export')}
            </span>
          }
          header={t('issues.toolbar.export')}
          items={[
            {
              key: 'md',
              label: (
                <>
                  <FileText size={14} aria-hidden="true" /> {t('issues.toolbar.exportMd')}
                </>
              ),
              onSelect: () => void onExport('md'),
            },
            {
              key: 'json',
              label: (
                <>
                  <FileJson size={14} aria-hidden="true" /> {t('issues.toolbar.exportJson')}
                </>
              ),
              onSelect: () => void onExport('json'),
            },
          ]}
        />

        <Button variant="primary" onClick={() => (reportOpen.value = true)}>
          <Plus size={15} aria-hidden="true" /> {t('issues.toolbar.newReport')}
        </Button>
      </div>

      {/* summary chips (honest counts) */}
      <div class="iss-summary" role="group" aria-label={t('issues.summary.bySeverity')}>
        <span class="iss-summary__total tnum">{t('issues.summary.total', { count: issues.value.length })}</span>
        {sevCounts.map(({ s, n }) => (
          <button
            key={s}
            type="button"
            class={`iss-chip${sevFilter.value === s ? ' is-on' : ''}`}
            onClick={() => toggleSev(s)}
            aria-pressed={sevFilter.value === s}
          >
            <Badge tone={SEVERITY_TONE[s]}>{t(`issues.severity.${s}`)}</Badge>
            <span class="tnum">{n}</span>
          </button>
        ))}
      </div>

      {error.value ? <p class="md-error">{error.value}</p> : null}

      {/* list / empty */}
      {loading.value && issues.value.length === 0 ? (
        <Card>
          <p class="dialog-text">{t('common.loading')}</p>
        </Card>
      ) : issues.value.length === 0 ? (
        <Card>
          <EmptyState emoji="🎉" title={t('issues.empty.title')} body={t('issues.empty.body')}>
            <Button variant="primary" onClick={() => (reportOpen.value = true)}>
              <Bug size={15} aria-hidden="true" /> {t('issues.toolbar.newReport')}
            </Button>
          </EmptyState>
        </Card>
      ) : visible.length === 0 ? (
        <Card>
          <EmptyState emoji="🔍" title={t('models.scan.noneTitle')} body={t('models.scan.noneBody')} />
        </Card>
      ) : (
        <div class="iss-list">
          {visible.map((i) => (
            <Card key={i.id} class="iss-card" hoverable onClick={() => (openId.value = i.id)}>
              <div class="iss-card__top">
                <code class="iss-card__id">{i.id}</code>
                <Badge tone={STATUS_TONE[i.status]} icon={STATUS_EMOJI[i.status]}>
                  {t(`issues.status.${i.status}`)}
                </Badge>
                <Badge tone={SEVERITY_TONE[i.severity]}>{t(`issues.severity.${i.severity}`)}</Badge>
              </div>
              <h3 class="iss-card__title">{i.title}</h3>
              <div class="iss-card__meta tnum">
                <span>{t('issues.card.created', { when: relativeDay(ts(i.created_at)) })}</span>
                <span>·</span>
                <span>{t('issues.card.timelineCount', { count: i.timeline.length })}</span>
              </div>
            </Card>
          ))}
        </div>
      )}

      <ReportModal
        open={reportOpen.value}
        onClose={() => (reportOpen.value = false)}
        onCreated={() => {
          void load()
        }}
      />

      <IssueDrawer
        issueId={openId.value}
        onClose={() => (openId.value = null)}
        onChanged={() => void load()}
      />
    </div>
  )
}

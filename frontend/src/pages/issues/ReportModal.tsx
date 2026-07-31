/* New-issue report modal (spec §9.5). Client-side validation mirrors the
   server (IssueCreate: title 5–200, description 10–10000). The redacted debug
   context is fetched on open and merged server-side on POST — we surface an
   honest note about what it contains (privacy transparency), never the raw
   snapshot here. created_by = display name (store). */
import { useEffect } from 'preact/hooks'
import { useSignal } from '@preact/signals'
import { Bug } from 'lucide-preact'
import { Button } from '@/components/Button'
import { Dialog } from '@/components/Dialog'
import { toast } from '@/components/Toast'
import { displayName } from '@/core/store'
import {
  createIssue,
  fetchDebugContext,
  SEVERITIES,
  type Issue,
  type Severity,
} from '@/core/issues'
import { t } from '@/i18n'

interface Props {
  open: boolean
  onClose: () => void
  onCreated: (issue: Issue) => void
}

export function ReportModal({ open, onClose, onCreated }: Props) {
  const title = useSignal('')
  const desc = useSignal('')
  const steps = useSignal('')
  const expected = useSignal('')
  const actual = useSignal('')
  const severity = useSignal<Severity>('medium')
  const submitting = useSignal(false)
  const ctxReady = useSignal(false)

  // Reset + probe debug context each time the modal opens.
  useEffect(() => {
    if (!open) return
    title.value = ''
    desc.value = ''
    steps.value = ''
    expected.value = ''
    actual.value = ''
    severity.value = 'medium'
    ctxReady.value = false
    void fetchDebugContext().then((c) => {
      ctxReady.value = c !== null
    })
  }, [open])

  const titleErr = title.value.trim().length !== 0 && (title.value.trim().length < 5 || title.value.trim().length > 200)
  const descErr = desc.value.trim().length !== 0 && (desc.value.trim().length < 10 || desc.value.trim().length > 10000)

  const submit = async () => {
    const tTrim = title.value.trim()
    const dTrim = desc.value.trim()
    if (tTrim.length < 5 || tTrim.length > 200) {
      toast('error', t('issues.report.titleError'))
      return
    }
    if (dTrim.length < 10 || dTrim.length > 10000) {
      toast('error', t('issues.report.descError'))
      return
    }
    submitting.value = true
    try {
      const issue = await createIssue({
        title: tTrim,
        description: dTrim,
        steps_to_reproduce: steps.value
          .split('\n')
          .map((s) => s.trim())
          .filter(Boolean),
        expected: expected.value.trim(),
        actual: actual.value.trim(),
        severity: severity.value,
        created_by: displayName.value.trim() || 'local-user',
      })
      onCreated(issue)
      onClose()
      toast('success', t('issues.toast.created'))
    } catch (e) {
      toast('error', t('issues.toast.saveFailed'), { body: e instanceof Error ? e.message : String(e) })
    } finally {
      submitting.value = false
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={t('issues.report.title')}
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting.value}>
            {t('common.cancel')}
          </Button>
          <Button variant="primary" loading={submitting.value} onClick={() => void submit()}>
            <Bug size={15} aria-hidden="true" /> {t('issues.report.submit')}
          </Button>
        </>
      }
    >
      <div class="iss-form">
        <label class="iss-field">
          <span>{t('issues.report.titleLabel')}</span>
          <input
            class="md-input"
            type="text"
            maxlength={200}
            placeholder={t('issues.report.titlePlaceholder')}
            value={title.value}
            onInput={(e) => (title.value = (e.target as HTMLInputElement).value)}
          />
          {titleErr ? <span class="iss-field__err">{t('issues.report.titleError')}</span> : null}
        </label>

        <label class="iss-field">
          <span>{t('issues.report.descLabel')}</span>
          <textarea
            class="md-input iss-textarea"
            rows={4}
            maxlength={10000}
            placeholder={t('issues.report.descPlaceholder')}
            value={desc.value}
            onInput={(e) => (desc.value = (e.target as HTMLInputElement).value)}
          />
          {descErr ? <span class="iss-field__err">{t('issues.report.descError')}</span> : null}
        </label>

        <label class="iss-field">
          <span>{t('issues.report.stepsLabel')}</span>
          <textarea
            class="md-input iss-textarea"
            rows={3}
            placeholder={t('issues.report.stepsPlaceholder')}
            value={steps.value}
            onInput={(e) => (steps.value = (e.target as HTMLInputElement).value)}
          />
        </label>

        <div class="iss-row">
          <label class="iss-field">
            <span>{t('issues.report.expectedLabel')}</span>
            <input
              class="md-input"
              type="text"
              value={expected.value}
              onInput={(e) => (expected.value = (e.target as HTMLInputElement).value)}
            />
          </label>
          <label class="iss-field">
            <span>{t('issues.report.actualLabel')}</span>
            <input
              class="md-input"
              type="text"
              value={actual.value}
              onInput={(e) => (actual.value = (e.target as HTMLInputElement).value)}
            />
          </label>
        </div>

        <label class="iss-field iss-field--inline">
          <span>{t('issues.report.severityLabel')}</span>
          <select
            class="md-input md-select"
            value={severity.value}
            onChange={(e) => (severity.value = (e.target as HTMLSelectElement).value as Severity)}
          >
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {t(`issues.severity.${s}`)}
              </option>
            ))}
          </select>
        </label>

        <p class="iss-attach">
          🔒 {t('issues.report.attachHint')}{' '}
          <span class="iss-attach__state" aria-hidden="true">
            {ctxReady.value ? '· ✓' : '· …'}
          </span>
        </p>
      </div>
    </Dialog>
  )
}

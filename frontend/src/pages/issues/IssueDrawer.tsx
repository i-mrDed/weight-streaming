/* Issue detail drawer (spec §9.5). Renders description/steps/expected/actual
   via the XSS-safe markdown pipeline, the redacted debug-context snapshot as
   a JSON code block, and the timeline. Maintainer mode (localStorage toggle)
   reveals status + triage controls that mirror the SERVER transition matrix
   (illegal moves disabled; "mark fixed" gated on root_cause/fix_summary/
   verify_steps). The verify_pending state shows the user verify flow
   (✅ fixed / ❌ still broken). Every mutation re-reads the issue. */
import { useEffect } from 'preact/hooks'
import { useSignal } from '@preact/signals'
import { CheckCircle2, ShieldCheck, Wrench, XOctagon } from 'lucide-preact'
import { Badge } from '@/components/Badge'
import { Button } from '@/components/Button'
import { Drawer } from '@/components/Drawer'
import { Tip } from '@/components/Tip'
import { toast } from '@/components/Toast'
import { displayName } from '@/core/store'
import { renderMarkdown } from '@/core/markdown'
import {
  canTransition,
  FIXED_REQUIRED_FIELDS,
  getIssue,
  maintainerActions,
  SEVERITIES,
  SEVERITY_TONE,
  STATUS_EMOJI,
  STATUS_TONE,
  updateIssue,
  verifyIssue,
  type Issue,
  type IssueStatus,
  type Severity,
} from '@/core/issues'
import { fmtDateTime, relativeDay, t } from '@/i18n'

const LS_MAINTAINER = 'ws-maintainer-mode'

interface Props {
  issueId: string | null
  onClose: () => void
  onChanged: () => void
}

function ts(s: string): number {
  const n = Date.parse(s)
  return Number.isNaN(n) ? Date.now() : n
}

export function IssueDrawer({ issueId, onClose, onChanged }: Props) {
  const issue = useSignal<Issue | null>(null)
  const loading = useSignal(false)
  const maintainer = useSignal<boolean>((() => {
    try {
      return localStorage.getItem(LS_MAINTAINER) === '1'
    } catch {
      return false
    }
  })())

  // maintainer draft fields
  const rootCause = useSignal('')
  const fixSummary = useSignal('')
  const commit = useSignal('')
  const verifySteps = useSignal('')
  const testNotes = useSignal('')
  const note = useSignal('')
  const sevDraft = useSignal<Severity>('medium')
  const busy = useSignal(false)
  const verifyNote = useSignal('')

  const open = issueId !== null

  const load = async (id: string) => {
    loading.value = true
    try {
      const it = await getIssue(id)
      issue.value = it
      rootCause.value = it.root_cause ?? ''
      fixSummary.value = it.fix_summary ?? ''
      commit.value = it.commit ?? ''
      verifySteps.value = it.verify_steps ?? ''
      testNotes.value = it.test_notes ?? ''
      sevDraft.value = it.severity
    } catch (e) {
      toast('error', t('issues.toast.loadFailed'), { body: e instanceof Error ? e.message : String(e) })
    } finally {
      loading.value = false
    }
  }

  useEffect(() => {
    if (issueId) void load(issueId)
    else issue.value = null
  }, [issueId])

  const setMaintainer = (v: boolean) => {
    maintainer.value = v
    try {
      if (v) localStorage.setItem(LS_MAINTAINER, '1')
      else localStorage.removeItem(LS_MAINTAINER)
    } catch {
      /* non-fatal */
    }
  }

  const it = issue.value
  const status: IssueStatus | null = it?.status ?? null

  const refresh = async () => {
    if (issueId) {
      await load(issueId)
      onChanged()
    }
  }

  const saveFields = async () => {
    if (!it) return
    busy.value = true
    try {
      await updateIssue(it.id, {
        root_cause: rootCause.value.trim(),
        fix_summary: fixSummary.value.trim(),
        commit: commit.value.trim(),
        verify_steps: verifySteps.value.trim(),
        test_notes: testNotes.value.trim(),
        updated_by: displayName.value.trim() || 'maintainer',
      })
      toast('success', t('issues.toast.updated'))
      await refresh()
    } catch (e) {
      toast('error', t('issues.toast.saveFailed'), { body: e instanceof Error ? e.message : String(e) })
    } finally {
      busy.value = false
    }
  }

  const changeSeverity = async (s: Severity) => {
    if (!it) return
    sevDraft.value = s
    busy.value = true
    try {
      await updateIssue(it.id, { severity: s, updated_by: displayName.value.trim() || 'maintainer' })
      await refresh()
    } catch (e) {
      toast('error', t('issues.toast.saveFailed'), { body: e instanceof Error ? e.message : String(e) })
    } finally {
      busy.value = false
    }
  }

  const changeStatus = async (to: IssueStatus) => {
    if (!it || !status) return
    if (!canTransition(status, to)) {
      toast('error', t('issues.maintainer.illegalTransition'))
      return
    }
    busy.value = true
    try {
      const body: Record<string, unknown> = {
        status: to,
        updated_by: displayName.value.trim() || 'maintainer',
      }
      // carry the maintainer fields on a "mark fixed" so a single click works
      if (to === 'fixed') {
        body.root_cause = rootCause.value.trim()
        body.fix_summary = fixSummary.value.trim()
        body.verify_steps = verifySteps.value.trim()
      }
      if (note.value.trim()) body.note = note.value.trim()
      await updateIssue(it.id, body)
      toast('success', t('issues.toast.updated'))
      note.value = ''
      await refresh()
    } catch (e) {
      toast('error', t('issues.toast.saveFailed'), { body: e instanceof Error ? e.message : String(e) })
    } finally {
      busy.value = false
    }
  }

  const doVerify = async (verified: boolean) => {
    if (!it) return
    busy.value = true
    try {
      await verifyIssue(it.id, {
        verified,
        note: verifyNote.value.trim(),
        verified_by: displayName.value.trim() || 'local-user',
      })
      toast('success', verified ? t('issues.toast.verified') : t('issues.toast.reopened'))
      verifyNote.value = ''
      await refresh()
    } catch (e) {
      toast('error', t('issues.toast.saveFailed'), { body: e instanceof Error ? e.message : String(e) })
    } finally {
      busy.value = false
    }
  }

  const addNote = async () => {
    if (!it || !note.value.trim()) return
    busy.value = true
    try {
      await updateIssue(it.id, { note: note.value.trim(), updated_by: displayName.value.trim() || 'maintainer' })
      note.value = ''
      await refresh()
    } catch (e) {
      toast('error', t('issues.toast.saveFailed'), { body: e instanceof Error ? e.message : String(e) })
    } finally {
      busy.value = false
    }
  }

  // "mark fixed" gating: required fields must be present in the draft.
  const missingFixed = FIXED_REQUIRED_FIELDS.filter((f) => {
    const v = f === 'root_cause' ? rootCause.value : f === 'fix_summary' ? fixSummary.value : verifySteps.value
    return !v.trim()
  })
  const fixedBlocked = status === 'in_progress' && missingFixed.length > 0

  const debugJson = it ? JSON.stringify(it.context ?? {}, null, 2) : ''

  return (
    <Drawer open={open} onClose={onClose} title={t('issues.detail.title')} width={520} side="right">
      {loading.value || !it ? (
        <p class="dialog-text">{t('common.loading')}</p>
      ) : (
        <div class="iss-detail">
          <div class="iss-detail__head">
            <code class="iss-detail__id">{it.id}</code>
            <Badge tone={STATUS_TONE[it.status]} icon={STATUS_EMOJI[it.status]}>
              {t(`issues.status.${it.status}`)}
            </Badge>
            <Badge tone={SEVERITY_TONE[it.severity]}>{t(`issues.severity.${it.severity}`)}</Badge>
          </div>
          <h3 class="iss-detail__title">{it.title}</h3>
          <p class="iss-detail__meta">
            {t('issues.detail.createdBy', { name: it.created_by || '—', when: relativeDay(ts(it.created_at)) })}
          </p>

          <section class="iss-block">
            <h4>{t('issues.detail.description')}</h4>
            <div class="iss-md" dangerouslySetInnerHTML={{ __html: renderMarkdown(it.description) }} />
          </section>

          {it.steps_to_reproduce.length > 0 ? (
            <section class="iss-block">
              <h4>{t('issues.detail.steps')}</h4>
              <ol class="iss-steps">
                {it.steps_to_reproduce.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ol>
            </section>
          ) : null}

          {it.expected || it.actual ? (
            <section class="iss-block iss-row">
              {it.expected ? (
                <div class="iss-half">
                  <h4>{t('issues.detail.expected')}</h4>
                  <p class="iss-md-inline">{it.expected}</p>
                </div>
              ) : null}
              {it.actual ? (
                <div class="iss-half">
                  <h4>{t('issues.detail.actual')}</h4>
                  <p class="iss-md-inline">{it.actual}</p>
                </div>
              ) : null}
            </section>
          ) : null}

          <section class="iss-block">
            <h4>
              {t('issues.detail.debugContext')} <Tip label={t('issues.empty.body')} />
            </h4>
            <div class="iss-md" dangerouslySetInnerHTML={{ __html: renderMarkdown('```json\n' + debugJson + '\n```') }} />
          </section>

          <section class="iss-block">
            <h4>{t('issues.detail.timeline')}</h4>
            {it.timeline.length === 0 ? (
              <p class="dialog-text--dim">{t('issues.detail.noTimeline')}</p>
            ) : (
              <ol class="iss-timeline">
                {it.timeline.map((e, i) => (
                  <li key={i}>
                    <span class="iss-timeline__dot" aria-hidden="true" />
                    <div>
                      <div class="iss-timeline__ev">
                        <code>{e.event}</code> <span class="iss-timeline__by">· {e.by}</span>
                      </div>
                      <time class="iss-timeline__at" dateTime={e.at} title={fmtDateTime(ts(e.at))}>
                        {relativeDay(ts(e.at))}
                      </time>
                      {e.note ? <p class="iss-timeline__note">{e.note}</p> : null}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>

          {/* ── verify flow (user) ─────────────────────────────── */}
          {it.status === 'verify_pending' ? (
            <section class="iss-block iss-verify">
              <h4>
                <ShieldCheck size={15} aria-hidden="true" /> {t('issues.verify.title')}
              </h4>
              <textarea
                class="md-input iss-textarea"
                rows={2}
                placeholder={t('issues.verify.notePlaceholder')}
                value={verifyNote.value}
                onInput={(e) => (verifyNote.value = (e.target as HTMLInputElement).value)}
              />
              <div class="iss-verify__btns">
                <Button variant="primary" size="sm" loading={busy.value} onClick={() => void doVerify(true)}>
                  <CheckCircle2 size={14} aria-hidden="true" /> {t('issues.verify.confirm')}
                </Button>
                <Button variant="danger" size="sm" loading={busy.value} onClick={() => void doVerify(false)}>
                  <XOctagon size={14} aria-hidden="true" /> {t('issues.verify.still')}
                </Button>
              </div>
            </section>
          ) : null}

          {/* ── maintainer mode ────────────────────────────────── */}
          <section class="iss-block iss-maint">
            <label class="iss-toggle">
              <input
                type="checkbox"
                checked={maintainer.value}
                onChange={(e) => setMaintainer((e.target as HTMLInputElement).checked)}
              />
              <span>
                <Wrench size={13} aria-hidden="true" /> {t('issues.maintainer.toggle')}
              </span>
              <Tip label={t('issues.maintainer.toggleHint')} />
            </label>

            {maintainer.value ? (
              <div class="iss-maint__panel">
                <label class="iss-field">
                  <span>{t('issues.maintainer.rootCause')}</span>
                  <textarea
                    class="md-input iss-textarea"
                    rows={2}
                    value={rootCause.value}
                    onInput={(e) => (rootCause.value = (e.target as HTMLInputElement).value)}
                  />
                </label>
                <label class="iss-field">
                  <span>{t('issues.maintainer.fixSummary')}</span>
                  <textarea
                    class="md-input iss-textarea"
                    rows={2}
                    value={fixSummary.value}
                    onInput={(e) => (fixSummary.value = (e.target as HTMLInputElement).value)}
                  />
                </label>
                <label class="iss-field">
                  <span>{t('issues.maintainer.verifySteps')}</span>
                  <textarea
                    class="md-input iss-textarea"
                    rows={2}
                    value={verifySteps.value}
                    onInput={(e) => (verifySteps.value = (e.target as HTMLInputElement).value)}
                  />
                </label>
                <div class="iss-row">
                  <label class="iss-field">
                    <span>{t('issues.maintainer.commit')}</span>
                    <input
                      class="md-input"
                      type="text"
                      value={commit.value}
                      onInput={(e) => (commit.value = (e.target as HTMLInputElement).value)}
                    />
                  </label>
                  <label class="iss-field iss-field--inline">
                    <span>{t('issues.toolbar.filterSeverity')}</span>
                    <select
                      class="md-input md-select"
                      value={sevDraft.value}
                      onChange={(e) => void changeSeverity((e.target as HTMLSelectElement).value as Severity)}
                    >
                      {SEVERITIES.map((s) => (
                        <option key={s} value={s}>
                          {t(`issues.severity.${s}`)}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <label class="iss-field">
                  <span>{t('issues.maintainer.testNotes')}</span>
                  <textarea
                    class="md-input iss-textarea"
                    rows={2}
                    value={testNotes.value}
                    onInput={(e) => (testNotes.value = (e.target as HTMLInputElement).value)}
                  />
                </label>
                <Button variant="soft" size="sm" loading={busy.value} onClick={() => void saveFields()}>
                  {t('issues.maintainer.saveFields')}
                </Button>

                {fixedBlocked ? (
                  <p class="iss-maint__req">
                    ⚠️ {t('issues.maintainer.fixedRequires', { fields: missingFixed.map((f) => t(`issues.maintainer.${camel(f)}`)).join(', ') })}
                  </p>
                ) : null}

                <div class="iss-actions">
                  {maintainerActions(it.status).map((a) => {
                    const disabled = a.kind === 'status' && a.toStatus && (!canTransition(it.status, a.toStatus) || (a.toStatus === 'fixed' && fixedBlocked))
                    return (
                      <Button
                        key={a.labelKey}
                        variant={a.tone}
                        size="sm"
                        loading={busy.value}
                        disabled={!!disabled}
                        onClick={() => a.toStatus && void changeStatus(a.toStatus)}
                      >
                        {t(a.labelKey)}
                      </Button>
                    )
                  })}
                </div>

                <div class="iss-note-row">
                  <input
                    class="md-input"
                    type="text"
                    placeholder={t('issues.maintainer.notePlaceholder')}
                    value={note.value}
                    onInput={(e) => (note.value = (e.target as HTMLInputElement).value)}
                  />
                  <Button variant="ghost" size="sm" disabled={!note.value.trim() || busy.value} onClick={() => void addNote()}>
                    {t('issues.maintainer.saveFields')}
                  </Button>
                </div>
              </div>
            ) : null}
          </section>
        </div>
      )}
    </Drawer>
  )
}

/** root_cause -> rootCause for i18n label lookup. */
function camel(s: string): string {
  return s.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase())
}

/* Issues API client + lifecycle model (spec §9.5).
   Shapes mirror weight_stream/issues/models.py EXACTLY (Issue, IssueCreate,
   IssueUpdate, IssueVerify, TimelineEvent) and the server transition matrix
   TRANSITIONS so the maintainer UI can disable illegal moves client-side
   (the server re-enforces — 400 on illegal transition / missing fixed fields).
   Endpoints are all pre-existing (P3 adds NO backend): POST/GET/GET export/
   GET {id}/PATCH {id}/POST {id}/verify. Debug context from /v1/debug/context
   (app_version here is the TRUTH — 0.13.0 — unlike /health's 0.11.0). */
import { apiJSON, ApiError } from './api'

export type IssueStatus =
  | 'open'
  | 'triaged'
  | 'in_progress'
  | 'fixed'
  | 'verify_pending'
  | 'verified'
  | 'wontfix'
  | 'duplicate'
  | 'closed'

export type Severity = 'low' | 'medium' | 'high' | 'critical'

export const ISSUE_STATUSES: IssueStatus[] = [
  'open',
  'triaged',
  'in_progress',
  'fixed',
  'verify_pending',
  'verified',
  'wontfix',
  'duplicate',
  'closed',
]

export const SEVERITIES: Severity[] = ['low', 'medium', 'high', 'critical']

/** Server TRANSITIONS (from -> allowed to). Terminal `closed` has none. */
export const TRANSITIONS: Record<IssueStatus, IssueStatus[]> = {
  open: ['triaged', 'in_progress', 'duplicate', 'wontfix'],
  triaged: ['in_progress', 'duplicate', 'wontfix'],
  in_progress: ['fixed', 'wontfix', 'duplicate'],
  fixed: ['verify_pending', 'in_progress'],
  verify_pending: ['verified', 'in_progress'],
  verified: ['closed'],
  wontfix: ['closed'],
  duplicate: ['closed'],
  closed: [],
}

export function canTransition(from: IssueStatus, to: IssueStatus): boolean {
  return TRANSITIONS[from]?.includes(to) ?? false
}

export interface TimelineEvent {
  at: string
  event: string
  by: string
  note?: string | null
}

export interface Issue {
  id: string
  title: string
  description: string
  steps_to_reproduce: string[]
  expected: string
  actual: string
  severity: Severity
  status: IssueStatus
  created_at: string
  updated_at: string
  created_by: string
  context: Record<string, unknown>
  root_cause?: string | null
  fix_summary?: string | null
  commit?: string | null
  test_notes?: string | null
  verify_steps?: string | null
  timeline: TimelineEvent[]
}

export interface IssueCreate {
  title: string
  description: string
  steps_to_reproduce?: string[]
  expected?: string
  actual?: string
  severity?: Severity
  created_by?: string
  context?: Record<string, unknown>
}

export interface IssueUpdate {
  title?: string
  description?: string
  severity?: Severity
  status?: IssueStatus
  root_cause?: string
  fix_summary?: string
  commit?: string
  test_notes?: string
  verify_steps?: string
  note?: string
  updated_by?: string
}

export interface IssueVerify {
  verified: boolean
  note?: string
  verified_by?: string
}

export interface DebugContext {
  app_version?: string
  llama_cpp_version?: string
  python_version?: string
  os?: string
  cwd?: string
  model_path?: string | null
  model_architecture?: string | null
  last_error?: string | null
  last_endpoint?: string | null
  env?: Record<string, string>
  log_tail?: string[]
}

/* ── Presentation maps (emoji + badge tone + i18n key) ───────────── */
import type { BadgeTone } from '@/components/Badge'

export const STATUS_EMOJI: Record<IssueStatus, string> = {
  open: '🔵',
  triaged: '🟣',
  in_progress: '🟡',
  fixed: '🟢',
  verify_pending: '🟠',
  verified: '✅',
  wontfix: '⚪',
  duplicate: '🔁',
  closed: '⚫',
}

export const STATUS_TONE: Record<IssueStatus, BadgeTone> = {
  open: 'info',
  triaged: 'brand',
  in_progress: 'warn',
  fixed: 'ok',
  verify_pending: 'warn',
  verified: 'ok',
  wontfix: 'neutral',
  duplicate: 'neutral',
  closed: 'neutral',
}

export const SEVERITY_TONE: Record<Severity, BadgeTone> = {
  low: 'neutral',
  medium: 'info',
  high: 'warn',
  critical: 'error',
}

/** Fields the server demands (require_fixed_fields) before status=fixed. */
export const FIXED_REQUIRED_FIELDS = ['root_cause', 'fix_summary', 'verify_steps'] as const

export type MaintainerActionKind = 'status' | 'verify'

export interface MaintainerAction {
  /** i18n key under issues.action.* */
  labelKey: string
  kind: MaintainerActionKind
  /** for kind 'status': the status we PATCH (fixed auto-advances server-side) */
  toStatus?: IssueStatus
  tone: 'primary' | 'soft' | 'ghost' | 'outline' | 'danger'
}

/** Maintainer-facing actions valid FROM a given status. `verify_pending`
 *  additionally surfaces the user verify flow (handled in the page). */
export function maintainerActions(status: IssueStatus): MaintainerAction[] {
  switch (status) {
    case 'open':
      return [
        { labelKey: 'issues.action.startProgress', kind: 'status', toStatus: 'in_progress', tone: 'primary' },
        { labelKey: 'issues.action.triage', kind: 'status', toStatus: 'triaged', tone: 'soft' },
        { labelKey: 'issues.action.wontfix', kind: 'status', toStatus: 'wontfix', tone: 'ghost' },
        { labelKey: 'issues.action.duplicate', kind: 'status', toStatus: 'duplicate', tone: 'ghost' },
      ]
    case 'triaged':
      return [
        { labelKey: 'issues.action.startProgress', kind: 'status', toStatus: 'in_progress', tone: 'primary' },
        { labelKey: 'issues.action.wontfix', kind: 'status', toStatus: 'wontfix', tone: 'ghost' },
        { labelKey: 'issues.action.duplicate', kind: 'status', toStatus: 'duplicate', tone: 'ghost' },
      ]
    case 'in_progress':
      return [
        // "Mark fixed" requires root_cause+fix_summary+verify_steps (enforced).
        { labelKey: 'issues.action.markFixed', kind: 'status', toStatus: 'fixed', tone: 'primary' },
        { labelKey: 'issues.action.wontfix', kind: 'status', toStatus: 'wontfix', tone: 'ghost' },
        { labelKey: 'issues.action.duplicate', kind: 'status', toStatus: 'duplicate', tone: 'ghost' },
      ]
    case 'fixed':
      // fixed auto-advances to verify_pending on the server; offer reopen.
      return [{ labelKey: 'issues.action.reopen', kind: 'status', toStatus: 'in_progress', tone: 'ghost' }]
    case 'verify_pending':
      // verify flow (✅/❌) is rendered separately; here only maintainer reopen.
      return [{ labelKey: 'issues.action.reopen', kind: 'status', toStatus: 'in_progress', tone: 'ghost' }]
    case 'verified':
      return [{ labelKey: 'issues.action.close', kind: 'status', toStatus: 'closed', tone: 'soft' }]
    case 'wontfix':
    case 'duplicate':
      return [{ labelKey: 'issues.action.close', kind: 'status', toStatus: 'closed', tone: 'soft' }]
    case 'closed':
      return []
  }
}

/* ── API helpers ─────────────────────────────────────────────────── */

export function listIssues(filter?: { status?: IssueStatus; severity?: Severity }): Promise<Issue[]> {
  const q = new URLSearchParams()
  if (filter?.status) q.set('status', filter.status)
  if (filter?.severity) q.set('severity', filter.severity)
  const qs = q.toString()
  return apiJSON<Issue[]>(`/v1/issues${qs ? `?${qs}` : ''}`, undefined, { timeoutMs: 8000 })
}

export function getIssue(id: string): Promise<Issue> {
  return apiJSON<Issue>(`/v1/issues/${encodeURIComponent(id)}`, undefined, { timeoutMs: 8000 })
}

export function createIssue(body: IssueCreate): Promise<Issue> {
  return apiJSON<Issue>('/v1/issues', { method: 'POST', body: JSON.stringify(body) }, { timeoutMs: 8000 })
}

export function updateIssue(id: string, body: IssueUpdate): Promise<Issue> {
  return apiJSON<Issue>(`/v1/issues/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(body) }, { timeoutMs: 8000 })
}

export function verifyIssue(id: string, body: IssueVerify): Promise<Issue> {
  return apiJSON<Issue>(`/v1/issues/${encodeURIComponent(id)}/verify`, { method: 'POST', body: JSON.stringify(body) }, { timeoutMs: 8000 })
}

/** Export — server returns text/markdown or a JSON array; we hand back the
 *  raw string so the page can trigger a user-initiated download (honest: no
 *  silent file writes). */
export async function exportIssues(format: 'md' | 'json'): Promise<string> {
  const res = await fetch(`/v1/issues/export?format=${format}`)
  if (!res.ok) throw new ApiError('http', `HTTP ${res.status} on export`, res.status)
  return await res.text()
}

/** Best-effort debug context (redacted server-side). null on failure so the
 *  report modal can still open without it. */
export async function fetchDebugContext(): Promise<DebugContext | null> {
  try {
    return await apiJSON<DebugContext>('/v1/debug/context', undefined, { timeoutMs: 6000 })
  } catch {
    return null
  }
}

/** Trigger a client-side download of text content (md/json export). */
export function downloadText(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

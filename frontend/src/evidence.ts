// Turns the evidence endpoint's response into what the dashboard says. Pure and
// dependency-free (tested with `node --test`). Nothing here assumes a pass: every
// verdict is derived from the report the backend actually read.
// Type-only import, so it is erased when Node strips types.
import type { EvidenceView, SecurityReport } from './types.ts'

export type Flag =
  | 'missing' | 'invalid' | 'failed' | 'partial' | 'stale'
  | 'commit_unknown' | 'uncommitted_changes' | 'runtime_db_changed'

export interface Verdict {
  tone: 'ok' | 'warn' | 'stop' | 'muted'
  title: string
  detail: string
  flags: Flag[]
}

export const FLAG_TEXT: Record<Flag, { label: string; explain: string }> = {
  missing: { label: 'Missing', explain: 'No report file has been generated on this machine yet.' },
  invalid: { label: 'Unusable', explain: 'The report file is malformed, uses an unsupported schema or failed the content check.' },
  failed: { label: 'Failed', explain: 'At least one scenario had a failing check in this run.' },
  partial: { label: 'Partial', explain: 'Some scenarios were not run, or the run was interrupted or errored.' },
  stale: { label: 'Stale', explain: 'The report was generated for a different commit than the one running now.' },
  commit_unknown: { label: 'Commit unknown', explain: 'The report or the running code has no verifiable Git commit.' },
  uncommitted_changes: { label: 'Uncommitted changes', explain: 'The report was generated with uncommitted changes to tracked files.' },
  runtime_db_changed: { label: 'Demo DB changed', explain: 'The runtime demo database changed during the run (another process may have used it).' },
}

/** Light structural check so an unexpected response is labelled, never rendered as a pass. */
export function isEvidenceView(value: unknown): value is EvidenceView {
  if (!value || typeof value !== 'object') return false
  const v = value as Record<string, unknown>
  if (!['available', 'missing', 'invalid'].includes(v.availability as string)) return false
  if (v.availability !== 'available') return true
  const r = v.report as SecurityReport | null
  return !!r && Array.isArray(r.scenarios) && r.scenarios.length > 0 && !!r.totals && !!r.suite && !!r.git
}

export function assessEvidence(view: EvidenceView): Verdict {
  if (view.availability === 'missing' || !view.report) {
    const invalid = view.availability === 'invalid'
    return {
      tone: invalid ? 'stop' : 'muted',
      title: invalid ? 'Report unusable' : 'No report yet',
      detail: view.problem ?? (invalid ? 'The report could not be read.' : 'Generate one with the command below.'),
      flags: [invalid ? 'invalid' : 'missing'],
    }
  }
  const r = view.report
  const total = r.scenarios.length
  const { passed, failed, not_run: notRun } = r.totals
  const flags: Flag[] = []
  if (failed > 0) flags.push('failed')
  if (notRun > 0 || r.suite.run_status !== 'complete') flags.push('partial')
  if (view.freshness === 'stale') flags.push('stale')
  if (view.freshness === 'unknown') flags.push('commit_unknown')
  if (r.git.dirty) flags.push('uncommitted_changes')
  if (r.isolation.runtime_db_unchanged === false) flags.push('runtime_db_changed')

  if (failed > 0) {
    return { tone: 'stop', title: `${failed} of ${total} scenarios failed`, detail: 'See the failing scenarios below. This run is not passing evidence.', flags }
  }
  if (flags.includes('partial') || passed !== total) {
    const why = r.suite.run_status === 'interrupted' ? 'The run was interrupted. '
      : r.suite.run_status === 'error' ? 'The run ended with an error. ' : ''
    return { tone: 'warn', title: `Incomplete: ${passed} of ${total} scenarios passed`, detail: `${why}${notRun} not run. Missing scenarios are not evidence either way.`, flags }
  }
  if (flags.includes('stale')) {
    return { tone: 'warn', title: `All ${total} scenarios passed on an older commit`, detail: 'Regenerate the report to get evidence for the code running now.', flags }
  }
  if (flags.includes('commit_unknown')) {
    return { tone: 'warn', title: `All ${total} scenarios passed; commit not verifiable`, detail: 'The report cannot be tied to the running code.', flags }
  }
  return { tone: 'ok', title: `All ${total} scenarios passed on the current commit`, detail: 'Every mapped check ran and passed in this report.', flags }
}

export function shortCommit(commit: string | null): string {
  return commit ? commit.slice(0, 7) : 'unknown'
}

/** "3 min ago" style age, for spotting old reports at a glance. */
export function ageText(iso: string, now: number = Date.now()): string {
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return 'unknown time'
  const s = Math.max(0, Math.round((now - t) / 1000))
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return `${Math.round(s / 86400)} d ago`
}

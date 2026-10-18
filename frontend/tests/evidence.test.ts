// Evidence verdict tests. Run: node --experimental-strip-types --test tests/evidence.test.ts
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { ageText, assessEvidence, isEvidenceView, shortCommit } from '../src/evidence.ts'
import type { EvidenceView, ScenarioResult, SecurityReport } from '../src/types.ts'

function report(results: ScenarioResult[], over: Partial<SecurityReport> = {}): SecurityReport {
  const scenarios = results.map((result, i) => ({
    id: `SEC-${String(i + 1).padStart(2, '0')}`, title: 't', claim: 'c', result, duration_seconds: 0,
    tests_total: 1, tests_passed: +(result === 'passed'), tests_failed: +(result === 'failed'),
    tests_not_run: +(result === 'not_run'), evidence: [], failure_summary: null,
  }))
  const count = (r: ScenarioResult) => results.filter((x) => x === r).length
  return {
    schema_version: '1.0', report_type: 'datagate-security-regression', generated_at: '2026-10-18T08:00:00Z',
    git: { commit: 'a'.repeat(40), dirty: false },
    suite: { id: 's', command: 'c', run_status: 'complete', pytest_exit_code: 0, tests_collected: 1, tests_passed: 1, tests_failed: 0, tests_not_run: 0, duration_seconds: 1 },
    isolation: { storage: 's', receiver: 'r', runtime_db_unchanged: true },
    totals: { passed: count('passed'), failed: count('failed'), not_run: count('not_run') },
    scenarios, disclaimer: 'd', ...over,
  }
}

function view(r: SecurityReport | null, over: Partial<EvidenceView> = {}): EvidenceView {
  return {
    availability: r ? 'available' : 'missing', problem: null, current_commit: 'a'.repeat(40), current_dirty: false,
    freshness: 'current', report: r, disclaimer: 'd', ...over,
  }
}

const ALL = Array<ScenarioResult>(14).fill('passed')

test('a complete, current, all-passed report is the only green verdict', () => {
  const v = assessEvidence(view(report(ALL)))
  assert.equal(v.tone, 'ok')
  assert.equal(v.title, 'All 14 scenarios passed on the current commit')
  assert.deepEqual(v.flags, [])
})

test('missing and invalid reports are labelled, never passing', () => {
  assert.deepEqual(assessEvidence(view(null)).flags, ['missing'])
  const inv = assessEvidence(view(null, { availability: 'invalid', problem: 'The report file is unusable: unsupported report schema.' }))
  assert.equal(inv.tone, 'stop')
  assert.deepEqual(inv.flags, ['invalid'])
  assert.match(inv.detail, /unsupported/)
})

test('a failure wins over everything else', () => {
  const v = assessEvidence(view(report([...ALL.slice(1), 'failed']), { freshness: 'stale' }))
  assert.equal(v.tone, 'stop')
  assert.equal(v.title, '1 of 14 scenarios failed')
  assert.deepEqual(v.flags, ['failed', 'stale'])
})

test('not-run scenarios or an interrupted run are partial', () => {
  const some = assessEvidence(view(report([...ALL.slice(2), 'not_run', 'not_run'])))
  assert.equal(some.tone, 'warn')
  assert.equal(some.title, 'Incomplete: 12 of 14 scenarios passed')
  const interrupted = report(ALL)
  interrupted.suite = { ...interrupted.suite, run_status: 'interrupted' }
  const v = assessEvidence(view(interrupted))
  assert.ok(v.flags.includes('partial') && v.tone === 'warn')
  assert.match(v.detail, /interrupted/)
})

test('stale, unknown commit, dirty tree and a changed demo DB are flagged', () => {
  assert.equal(assessEvidence(view(report(ALL), { freshness: 'stale' })).title, 'All 14 scenarios passed on an older commit')
  assert.ok(assessEvidence(view(report(ALL, { git: { commit: null, dirty: null } }), { freshness: 'unknown' })).flags.includes('commit_unknown'))
  const dirty = assessEvidence(view(report(ALL, { git: { commit: 'a'.repeat(40), dirty: true } })))
  assert.ok(dirty.flags.includes('uncommitted_changes'))
  const db = assessEvidence(view(report(ALL, { isolation: { storage: 's', receiver: 'r', runtime_db_unchanged: false } })))
  assert.ok(db.flags.includes('runtime_db_changed'))
})

test('unexpected response shapes are rejected', () => {
  assert.equal(isEvidenceView(null), false)
  assert.equal(isEvidenceView({ availability: 'yes' }), false)
  assert.equal(isEvidenceView({ availability: 'available', report: { scenarios: [] } }), false)
  assert.equal(isEvidenceView(view(report(ALL))), true)
  assert.equal(isEvidenceView(view(null)), true)
})

test('small display helpers', () => {
  assert.equal(shortCommit('0123456789'.repeat(4)), '0123456')
  assert.equal(shortCommit(null), 'unknown')
  const t = Date.parse('2026-10-18T08:00:00Z')
  assert.equal(ageText('2026-10-18T08:00:00Z', t + 30_000), 'just now')
  assert.equal(ageText('2026-10-18T08:00:00Z', t + 5 * 60_000), '5 min ago')
  assert.equal(ageText('2026-10-18T08:00:00Z', t + 3 * 86_400_000), '3 d ago')
  assert.equal(ageText('nonsense', t), 'unknown time')
})

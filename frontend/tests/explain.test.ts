// Policy explanation tests. Run: node --experimental-strip-types --test tests/explain.test.ts
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { explainPreview } from '../src/explain.ts'
import type { Passport, PreviewResponse } from '../src/types.ts'

const PASSPORT: Passport = {
  declared_owner: 'o', allowed_purposes: ['feedback_summary'], allowed_destinations: ['demo_receiver'],
  outbound_fields: ['message'], required_redactions: ['EMAIL', 'PHONE'], sharing_mode: 'redacted_only', policy_version: 1,
}

function preview(over: Partial<PreviewResponse> = {}): PreviewResponse {
  return {
    request_id: 'req_x', dataset_id: 'feedback_a', dataset_revision: 1, policy_version: 1, review_revision: 1,
    decision: 'redact', status: 'ready', reason_codes: ['REDACTION_REQUIRED'],
    dropped_fields: ['ticket_id', 'customer_name', 'email', 'account_value'],
    redaction_counts: { EMAIL: 3, PHONE: 0 }, hidden_message_indices: [], custom_redactions: [],
    outbound_payload: { schema_version: '1.0', purpose: 'feedback_summary', instruction: 'i', messages: ['a', 'b'] },
    preview_hash: 'f'.repeat(64), receiver_mode: 'local_demo', receiver_attempts: 0, receipt_available: false,
    ...over,
  }
}

function rows(p: PreviewResponse, passport: Passport | null = PASSPORT) {
  const e = explainPreview(p, passport)
  assert.equal(e.kind, 'rows')
  return e.kind === 'rows' ? e : (null as never)
}

test('rows come from the response: kept field, removed columns, required checks', () => {
  const e = rows(preview())
  assert.deepEqual(e.rows.map((r) => [r.field, r.result, r.explanation]).slice(0, 7), [
    ['Feedback message', 'Included', 'Needed to summarize customer feedback'],
    ['Ticket ID column', 'Removed', 'Not permitted for this purpose'],
    ['Customer name column', 'Removed', 'Not permitted for this purpose'],
    ['Email column', 'Removed', 'Not permitted for this purpose'],
    ['Account value column', 'Removed', 'Not permitted for this purpose'],
    ['Email addresses inside messages', 'Redacted · 3 matches', 'Required by company policy'],
    ['Phone numbers inside messages', 'Checked · no matches', 'Required by company policy; the automatic check found none'],
  ])
})

test('zero matches never claim redaction or absence of PII', () => {
  const e = rows(preview({ redaction_counts: { EMAIL: 0, PHONE: 0 }, decision: 'allow', reason_codes: [] }))
  const inside = e.rows.filter((r) => r.key.startsWith('inside-'))
  assert.ok(inside.every((r) => r.result === 'Checked · no matches' && r.tone === 'checked'))
  const last = e.rows[e.rows.length - 1]
  assert.equal(last.result, 'Not auto-checked')
  assert.match(last.explanation, /person names/)
  assert.match(last.explanation, /Review each message/)
})

test('PERSON appears as a required check only when the policy requires it', () => {
  const off = rows(preview())
  assert.ok(!off.rows.some((r) => r.key === 'inside-PERSON'))
  assert.match(off.rows[off.rows.length - 1].explanation, /person names/)
  const on = rows(preview({ redaction_counts: { EMAIL: 3, PHONE: 0, PERSON: 5 } }),
    { ...PASSPORT, required_redactions: ['EMAIL', 'PHONE', 'PERSON'], person_style: 'numbered' })
  const person = on.rows.find((r) => r.key === 'inside-PERSON')!
  assert.equal(person.result, 'Redacted · 5 matches')
  assert.match(person.explanation, /numbered placeholder/)
  assert.doesNotMatch(on.rows[on.rows.length - 1].explanation, /person names/)
  const one = rows(preview({ redaction_counts: { EMAIL: 1, PHONE: 0, PERSON: 0 } }))
  assert.equal(one.rows.find((r) => r.key === 'inside-EMAIL')!.result, 'Redacted · 1 match')
  assert.equal(one.rows.find((r) => r.key === 'inside-PERSON')!.result, 'Checked · no matches')
})

test("the analyst's own choices are counted separately, never as policy", () => {
  const e = rows(preview({
    hidden_message_indices: [1],
    custom_redactions: [{ message_index: 0, start: 0, end: 1 }, { message_index: 1, start: 0, end: 1 }],
  }))
  assert.deepEqual(e.yourChoices, { hiddenMessages: 1, textRedactions: 1 })
  assert.equal(e.rows.find((r) => r.key === 'inside-EMAIL')!.result, 'Redacted · 3 matches')
})

test('blocked previews show reasons and no invented rows or counts', () => {
  const e = explainPreview(preview({
    status: 'blocked', decision: 'block', outbound_payload: null, preview_hash: null, review_revision: null,
    reason_codes: ['PURPOSE_NOT_ALLOWED', 'DESTINATION_NOT_ALLOWED'], dropped_fields: [], redaction_counts: {},
  }), PASSPORT)
  assert.deepEqual(e, { kind: 'blocked', reasons: [
    'The owner does not allow this purpose for this data.',
    'The owner does not allow sending this data to the chosen receiver.',
  ] })
})

test('without a passport the kept message row still comes from the payload', () => {
  const e = rows(preview(), null)
  assert.equal(e.rows[0].field, 'Feedback message')
})

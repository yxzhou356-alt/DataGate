// Timeline wording tests. Run: node --experimental-strip-types --test tests/timeline.test.ts
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { deliveryOf, redactionSummary } from '../src/timeline.ts'

const HASH = 'f'.repeat(64)

test('zero attempts, failed delivery and acknowledged delivery are distinct', () => {
  assert.equal(deliveryOf({ receiver_attempts: 0, confirmed_sent_payload_hash: null, status: 'blocked' }), 'not_called')
  assert.equal(deliveryOf({ receiver_attempts: 0, confirmed_sent_payload_hash: null, status: 'stale' }), 'not_called')
  assert.equal(deliveryOf({ receiver_attempts: 1, confirmed_sent_payload_hash: null, status: 'send_failed' }), 'unconfirmed')
  assert.equal(deliveryOf({ receiver_attempts: 1, confirmed_sent_payload_hash: HASH, status: 'sent' }), 'acknowledged')
  // A confirmed hash alone is not enough: the outcome must be sent.
  assert.equal(deliveryOf({ receiver_attempts: 1, confirmed_sent_payload_hash: HASH, status: 'send_failed' }), 'unconfirmed')
})

test('redaction summary counts owner rules and requester choices', () => {
  const base = { redaction_counts: { EMAIL: 2, PHONE: 1 }, additional_hidden_messages: 1, additional_custom_redactions: 2, review_revision: 3 }
  assert.equal(redactionSummary(base),
    '2 email addresses, 1 phone number removed by owner rules · 1 message hidden by you · 2 text redactions by you')
  assert.equal(redactionSummary({ ...base, redaction_counts: { EMAIL: 0, PHONE: 0 }, additional_hidden_messages: 0, additional_custom_redactions: 0 }),
    'No supported identifiers detected')
})

test('blocked-before-preview receipts say they were not scanned', () => {
  assert.equal(redactionSummary({ redaction_counts: {}, additional_hidden_messages: 0, additional_custom_redactions: 0, review_revision: null }),
    'Not scanned: blocked before a preview was prepared')
})

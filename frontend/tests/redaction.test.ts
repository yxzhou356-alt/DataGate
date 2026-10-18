// Display-helper tests. Run with Node's built-in runner (no extra dependencies):
//   node --experimental-strip-types --test tests/redaction.test.ts
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  HIDDEN_MARKER, countPlaceholders, placeholderTypes, segmentMessage, shortHash, toggleIndex,
} from '../src/redaction.ts'

const TYPES = placeholderTypes(['PHONE', 'EMAIL'])

test('placeholder types come only from plain upper-case identifiers', () => {
  assert.deepEqual(TYPES, ['EMAIL', 'PHONE'])
  assert.deepEqual(placeholderTypes(['EMAIL', 'EMAIL', 'a|b', '.*', 'HIDDEN_BY_USER', '']), ['EMAIL'])
})

test('multiple and repeated placeholders become separate redaction segments', () => {
  const text = 'Mail [EMAIL] or [EMAIL], call [PHONE] / [PHONE].'
  assert.deepEqual(segmentMessage(text, TYPES), [
    { kind: 'text', text: 'Mail ' }, { kind: 'redaction', type: 'EMAIL' },
    { kind: 'text', text: ' or ' }, { kind: 'redaction', type: 'EMAIL' },
    { kind: 'text', text: ', call ' }, { kind: 'redaction', type: 'PHONE' },
    { kind: 'text', text: ' / ' }, { kind: 'redaction', type: 'PHONE' },
    { kind: 'text', text: '.' },
  ])
  assert.deepEqual(countPlaceholders(text, TYPES), { EMAIL: 2, PHONE: 2 })
})

test('adjacent placeholders at the edges produce no empty text segments', () => {
  assert.deepEqual(segmentMessage('[PHONE][EMAIL]', TYPES), [
    { kind: 'redaction', type: 'PHONE' }, { kind: 'redaction', type: 'EMAIL' },
  ])
})

test('messages without redactions stay one text segment', () => {
  assert.deepEqual(segmentMessage('Checkout is slow.', TYPES), [{ kind: 'text', text: 'Checkout is slow.' }])
  assert.deepEqual(countPlaceholders('Checkout is slow.', TYPES), {})
  assert.deepEqual(segmentMessage('', TYPES), [])
})

test('HTML-like text and unknown brackets stay literal text', () => {
  const text = '<img src=x onerror=alert(1)> [NAME] [email] <b>[EMAIL]</b>'
  const segs = segmentMessage(text, TYPES)
  assert.deepEqual(segs.filter((s) => s.kind === 'redaction'), [{ kind: 'redaction', type: 'EMAIL' }])
  assert.equal(segs.map((s) => (s.kind === 'text' ? s.text : '[EMAIL]')).join(''), text)
})

test('Unicode text is preserved around placeholders', () => {
  const text = 'Ça marche pas 😕 — écrivez à [EMAIL] 谢谢'
  const segs = segmentMessage(text, TYPES)
  assert.equal(segs.map((s) => (s.kind === 'text' ? s.text : '[EMAIL]')).join(''), text)
  assert.deepEqual(countPlaceholders(text, TYPES), { EMAIL: 1 })
})

test('the hidden marker is not a redaction type', () => {
  assert.deepEqual(segmentMessage(HIDDEN_MARKER, TYPES), [{ kind: 'text', text: HIDDEN_MARKER }])
})

test('toggling hidden indices is deduplicated and sorted', () => {
  assert.deepEqual(toggleIndex([], 3), [3])
  assert.deepEqual(toggleIndex([3], 3), [])
  assert.deepEqual(toggleIndex([5, 1, 5, 3], 0), [0, 1, 3, 5])
  assert.deepEqual(toggleIndex([5, 1, 5, 3], 5), [1, 3])
  assert.deepEqual(toggleIndex([2, 10], 9), [2, 9, 10]) // numeric, not lexicographic
})

test('short hash shows the head and tail only', () => {
  assert.equal(shortHash('a'.repeat(60) + 'bcde'), 'aaaaaaaa…bcde')
  assert.equal(shortHash(null), '—')
})

// Display-helper tests. Run with Node's built-in runner (no extra dependencies):
//   node --experimental-strip-types --test tests/redaction.test.ts
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  CUSTOM_MARKER, HIDDEN_MARKER, buildReviewSegments, countPlaceholders, cpToUnit, placeholderTypes, renderSegments,
  segmentMessage, shortHash, snapSelection, toggleIndex, unitToCp,
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

// ---------------------------------------------------------------- custom spans --
const BASE = 'Call [PHONE] about 😕 order 42 for [EMAIL].'

test('code-point and UTF-16 offsets convert across astral characters', () => {
  const emoji = BASE.indexOf('😕')
  assert.equal(cpToUnit(BASE, unitToCp(BASE, emoji)), emoji)
  assert.equal(unitToCp(BASE, emoji + 2), unitToCp(BASE, emoji) + 1) // 😕 is 2 units, 1 code point
  assert.equal(cpToUnit(BASE, 1_000), BASE.length)
})

test('segments overlay custom spans and reproduce the server outbound text', () => {
  const order = BASE.indexOf('order 42')
  const span = { start: unitToCp(BASE, order), end: unitToCp(BASE, order + 8) }
  const segs = buildReviewSegments(BASE, [span], TYPES)
  assert.equal(renderSegments(segs), `Call [PHONE] about 😕 ${CUSTOM_MARKER} for [EMAIL].`)
  assert.deepEqual(segs.map((s) => s.kind), ['text', 'redaction', 'text', 'custom', 'text', 'redaction', 'text'])
  for (const s of segs) if (s.kind === 'text') assert.equal(BASE.slice(s.start, s.end), s.text)
})

test('overlapping or out-of-order spans do not verify against server text', () => {
  const segs = buildReviewSegments(BASE, [{ start: 0, end: 10 }, { start: 5, end: 12 }], TYPES)
  assert.notEqual(renderSegments(segs), `${CUSTOM_MARKER}${BASE.slice(12)}`)
})

test('selection snapping expands over markers, trims whitespace and keeps surrogate pairs whole', () => {
  const segs = buildReviewSegments(BASE, [], TYPES)
  const phone = BASE.indexOf('[PHONE]')
  // Starting inside the [PHONE] marker expands to cover all of it.
  const snapped = snapSelection(BASE, segs, phone + 3, BASE.indexOf(' about'))!
  assert.deepEqual(snapped, { start: unitToCp(BASE, phone), end: unitToCp(BASE, phone + 7) })
  // Whitespace-only and reversed selections.
  assert.equal(snapSelection(BASE, segs, 4, 5), null)
  const order = BASE.indexOf('order')
  assert.deepEqual(snapSelection(BASE, segs, order + 5, order - 1), { start: unitToCp(BASE, order), end: unitToCp(BASE, order + 5) })
  // Ending between the two halves of the emoji includes the whole emoji.
  const emoji = BASE.indexOf('😕')
  assert.deepEqual(snapSelection(BASE, segs, emoji, emoji + 1), { start: unitToCp(BASE, emoji), end: unitToCp(BASE, emoji) + 1 })
})

test('selecting text already inside a custom span requests nothing', () => {
  const segs = buildReviewSegments(BASE, [{ start: 0, end: 4 }], TYPES)
  assert.equal(snapSelection(BASE, segs, 1, 3), null)
  // Extending past it is allowed; the server merges the overlap.
  assert.deepEqual(snapSelection(BASE, segs, 2, 12), { start: 0, end: 12 })
})

// ----------------------------------------------------------- PERSON placeholders --
const PTYPES = placeholderTypes(['EMAIL', 'PHONE', 'PERSON'])

test('numbered PERSON placeholders parse with their ordinal, including multi-digit', () => {
  const text = '[PERSON_1] met [PERSON_12] and [PERSON] at [EMAIL]'
  const segs = segmentMessage(text, PTYPES)
  assert.deepEqual(segs.filter((s) => s.kind === 'redaction'), [
    { kind: 'redaction', type: 'PERSON', ordinal: 1 },
    { kind: 'redaction', type: 'PERSON', ordinal: 12 },
    { kind: 'redaction', type: 'PERSON' },
    { kind: 'redaction', type: 'EMAIL' },
  ])
  assert.deepEqual(countPlaceholders(text, PTYPES), { PERSON: 3, EMAIL: 1 })
})

test('escaped source tokens and malformed numbers stay plain text', () => {
  for (const text of ['(PERSON_1) wrote', '[PERSON_0] wrote', '[PERSON_] wrote', '[person_1] wrote']) {
    assert.deepEqual(segmentMessage(text, PTYPES), [{ kind: 'text', text }])
  }
})

test('numbered placeholders round-trip through review segments with custom spans', () => {
  const base = '[PERSON_1] asked [PERSON_2] to check 😀 the export.'
  const at = base.indexOf('check')
  const span = { start: unitToCp(base, at), end: unitToCp(base, at + 5) }
  const segs = buildReviewSegments(base, [span], PTYPES)
  assert.equal(renderSegments(segs), `[PERSON_1] asked [PERSON_2] to ${CUSTOM_MARKER} 😀 the export.`)
  for (const s of segs) if (s.kind === 'text') assert.equal(base.slice(s.start, s.end), s.text)
})

test('a selection starting inside [PERSON_2] expands to the whole placeholder', () => {
  const base = '[PERSON_1] asked [PERSON_2] to check.'
  const segs = buildReviewSegments(base, [], PTYPES)
  const p2 = base.indexOf('[PERSON_2]')
  assert.deepEqual(snapSelection(base, segs, p2 + 4, base.indexOf(' to')), { start: p2, end: p2 + 10 })
})

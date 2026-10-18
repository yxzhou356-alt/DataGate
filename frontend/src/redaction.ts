// Display-only parsing of server-issued outbound message text. The backend owns
// redaction and hiding; nothing here changes, reconstructs or submits content.
// Self-contained (no imports) so it can be unit-tested with plain `node --test`.

export const HIDDEN_MARKER = '[HIDDEN_BY_USER]'

/** `ordinal` is set for numbered PERSON placeholders: [PERSON_3] -> type 'PERSON', ordinal 3. */
export type Segment =
  | { kind: 'text'; text: string }
  | { kind: 'redaction'; type: string; ordinal?: number }

/** The exact server token a redaction segment stands for. */
export function placeholderToken(s: { type: string; ordinal?: number }): string {
  return `[${s.type}${s.ordinal ? `_${s.ordinal}` : ''}]`
}

/**
 * Placeholder types to recognise, taken from the server's own preview fields
 * (e.g. redaction_counts keys). Only plain upper-case identifiers are accepted,
 * so they are safe to embed in a RegExp.
 */
export function placeholderTypes(types: Iterable<string>): string[] {
  const out = new Set<string>()
  for (const t of types) if (/^[A-Z][A-Z_]*$/.test(t) && `[${t}]` !== HIDDEN_MARKER) out.add(t)
  return [...out].sort()
}

/** Splits a server-issued message into plain text and `[TYPE]` / `[PERSON_n]` placeholder segments. */
export function segmentMessage(text: string, types: readonly string[]): Segment[] {
  if (types.length === 0) return text ? [{ kind: 'text', text }] : []
  const alternatives = types.map((t) => (t === 'PERSON' ? 'PERSON(?:_[1-9]\\d{0,5})?' : t))
  const pattern = new RegExp(`\\[(${alternatives.join('|')})\\]`, 'g')
  const segments: Segment[] = []
  let last = 0
  for (const match of text.matchAll(pattern)) {
    const at = match.index ?? 0
    if (at > last) segments.push({ kind: 'text', text: text.slice(last, at) })
    const numbered = /^PERSON_(\d+)$/.exec(match[1])
    segments.push(numbered ? { kind: 'redaction', type: 'PERSON', ordinal: Number(numbered[1]) } : { kind: 'redaction', type: match[1] })
    last = at + match[0].length
  }
  if (last < text.length) segments.push({ kind: 'text', text: text.slice(last) })
  return segments
}

/** Placeholder counts in one message, in the given type order; zero counts omitted. */
export function countPlaceholders(text: string, types: readonly string[]): Record<string, number> {
  const counts: Record<string, number> = {}
  for (const s of segmentMessage(text, types)) {
    if (s.kind === 'redaction') counts[s.type] = (counts[s.type] ?? 0) + 1
  }
  return counts
}

/** Next complete hidden-index set after toggling one message: deduplicated and sorted. */
export function toggleIndex(current: readonly number[], index: number): number[] {
  const next = new Set(current)
  if (next.has(index)) next.delete(index)
  else next.add(index)
  return [...next].sort((a, b) => a - b)
}

/** Short form of a SHA-256 hex fingerprint for display next to the full value. */
export function shortHash(hash: string | null): string {
  return hash ? `${hash.slice(0, 8)}…${hash.slice(-4)}` : '—'
}

// ---------------------------------------------------------------------------
// Custom (requester-selected) redactions. The browser only sends offsets into the
// server's mandatory-redacted text; the backend applies them and returns the
// authoritative outbound text, which the UI re-derives and verifies before use.

export const CUSTOM_MARKER = '[REDACTED_BY_USER]'

/** A custom redaction span in Unicode code points (the wire unit). */
export interface CpSpan { start: number; end: number }

export type ReviewSegment =
  | { kind: 'text'; text: string; start: number; end: number }
  | { kind: 'redaction'; type: string; ordinal?: number; start: number; end: number }
  | { kind: 'custom'; start: number; end: number; cpStart: number; cpEnd: number }

const isLowSurrogate = (code: number) => code >= 0xdc00 && code <= 0xdfff

/** Code-point offset to UTF-16 index (what DOM selections and String#slice use). */
export function cpToUnit(text: string, cp: number): number {
  let unit = 0
  for (let n = 0; n < cp && unit < text.length; n++) unit += (text.codePointAt(unit) ?? 0) > 0xffff ? 2 : 1
  return unit
}

/** UTF-16 index to code-point offset. Callers snap indices off surrogate pairs first. */
export function unitToCp(text: string, unit: number): number {
  let n = 0
  for (let i = 0; i < unit && i < text.length; n++) i += (text.codePointAt(i) ?? 0) > 0xffff ? 2 : 1
  return n
}

/**
 * Segments of the base (mandatory-redacted) text with custom spans overlaid.
 * Offsets are UTF-16 indices into `base`, so DOM selections map onto them directly.
 */
export function buildReviewSegments(base: string, spans: readonly CpSpan[], types: readonly string[]): ReviewSegment[] {
  const out: ReviewSegment[] = []
  const plain = (from: number, to: number) => {
    let at = from
    for (const s of segmentMessage(base.slice(from, to), types)) {
      const len = s.kind === 'text' ? s.text.length : placeholderToken(s).length
      out.push({ ...s, start: at, end: at + len })
      at += len
    }
  }
  let pos = 0
  const ordered = [...spans].sort((a, b) => a.start - b.start)
  for (const span of ordered) {
    const start = cpToUnit(base, span.start)
    const end = cpToUnit(base, span.end)
    if (start < pos || end <= start) continue // not normalised; verification below will fail closed
    plain(pos, start)
    out.push({ kind: 'custom', start, end, cpStart: span.start, cpEnd: span.end })
    pos = end
  }
  plain(pos, base.length)
  return out
}

/** The outbound text these segments stand for; compared with the server's text before editing is allowed. */
export function renderSegments(segments: readonly ReviewSegment[]): string {
  return segments.map((s) => (s.kind === 'text' ? s.text : s.kind === 'redaction' ? placeholderToken(s) : CUSTOM_MARKER)).join('')
}

/**
 * Turns a raw selection (UTF-16 indices into `base`) into a span to request:
 * expands over any marker it touches, trims surrounding whitespace, never splits a
 * surrogate pair, and returns null if nothing new would be redacted.
 */
export function snapSelection(base: string, segments: readonly ReviewSegment[], start: number, end: number): CpSpan | null {
  if (start > end) [start, end] = [end, start]
  start = Math.max(0, start)
  end = Math.min(base.length, end)
  for (const s of segments) {
    if (s.kind !== 'text' && s.start < end && start < s.end) {
      start = Math.min(start, s.start)
      end = Math.max(end, s.end)
    }
  }
  while (start < end && /\s/.test(base[start])) start++
  while (end > start && /\s/.test(base[end - 1])) end--
  if (start > 0 && start < base.length && isLowSurrogate(base.charCodeAt(start))) start--
  if (end < base.length && isLowSurrogate(base.charCodeAt(end))) end++
  if (start >= end) return null
  if (segments.some((s) => s.kind === 'custom' && s.start <= start && end <= s.end)) return null
  return { start: unitToCp(base, start), end: unitToCp(base, end) }
}

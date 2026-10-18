// Display-only parsing of server-issued outbound message text. The backend owns
// redaction and hiding; nothing here changes, reconstructs or submits content.
// Self-contained (no imports) so it can be unit-tested with plain `node --test`.

export const HIDDEN_MARKER = '[HIDDEN_BY_USER]'

export type Segment =
  | { kind: 'text'; text: string }
  | { kind: 'redaction'; type: string }

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

/** Splits a server-issued message into plain text and `[TYPE]` placeholder segments. */
export function segmentMessage(text: string, types: readonly string[]): Segment[] {
  if (types.length === 0) return text ? [{ kind: 'text', text }] : []
  const pattern = new RegExp(`\\[(${types.join('|')})\\]`, 'g')
  const segments: Segment[] = []
  let last = 0
  for (const match of text.matchAll(pattern)) {
    const at = match.index ?? 0
    if (at > last) segments.push({ kind: 'text', text: text.slice(last, at) })
    segments.push({ kind: 'redaction', type: match[1] })
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

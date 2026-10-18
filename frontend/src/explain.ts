// Policy explanation: turns a real preview response (and the owner passport, when known)
// into rows of "what happened to this data and why". Pure, dependency-free, tested with
// `node --test`. Every row and number comes from the response; only the wording is mapped.
// It never shows source values, and never counts the analyst's own choices as policy.
import type { Passport, PreviewResponse } from './types.ts'

export type ResultTone = 'included' | 'removed' | 'redacted' | 'checked' | 'unchecked'

export interface ExplanationRow {
  key: string
  field: string
  result: string
  tone: ResultTone
  explanation: string
}

export type Explanation =
  | { kind: 'blocked'; reasons: string[] }
  | {
      kind: 'rows'
      rows: ExplanationRow[]
      /** The analyst's own review choices, kept separate from company rules. */
      yourChoices: { hiddenMessages: number; textRedactions: number }
    }

// Redaction types the backend can apply, in its precedence order (display order).
export const SUPPORTED_TYPES = ['EMAIL', 'SSN', 'CREDIT_CARD', 'IP_ADDRESS', 'PHONE', 'DOB', 'ADDRESS', 'PERSON'] as const

const FIELD_NAMES: Record<string, string> = {
  message: 'Feedback message',
  ticket_id: 'Ticket ID column',
  customer_name: 'Customer name column',
  email: 'Email column',
  phone: 'Phone column',
  plan_tier: 'Subscription plan column',
  account_value: 'Account value column',
  product_area: 'Product category column',
}

const INSIDE_NAMES: Record<string, string> = {
  EMAIL: 'Email addresses inside messages',
  PHONE: 'Phone numbers inside messages',
  PERSON: 'Person names inside messages',
  SSN: 'Social Security numbers inside messages',
  CREDIT_CARD: 'Card numbers inside messages',
  IP_ADDRESS: 'IP addresses inside messages',
  ADDRESS: 'Street addresses inside messages',
  DOB: 'Dates of birth inside messages',
}

const NOT_REQUIRED_NAMES: Record<string, string> = {
  EMAIL: 'email addresses', PHONE: 'phone numbers', PERSON: 'person names', SSN: 'Social Security numbers',
  CREDIT_CARD: 'card numbers', IP_ADDRESS: 'IP addresses', ADDRESS: 'street addresses', DOB: 'dates of birth',
}

const PURPOSE_NEED: Record<string, string> = {
  feedback_summary: 'Needed to summarize customer feedback',
}

export const BLOCK_REASONS: Record<string, string> = {
  PURPOSE_NOT_ALLOWED: 'The owner does not allow this purpose for this data.',
  DESTINATION_NOT_ALLOWED: 'The owner does not allow sending this data to the chosen receiver.',
  SHARING_PROHIBITED: 'The owner does not allow this data to be shared, even after redaction.',
  ACCESS_REVOKED: 'Your access to this data was revoked.',
}

export function fieldName(field: string): string {
  return FIELD_NAMES[field] ?? `${field} column`
}

function list(items: string[]): string {
  return items.length <= 2 ? items.join(' and ') : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
}

function matches(n: number): string {
  return `${n} ${n === 1 ? 'match' : 'matches'}`
}

export function explainPreview(preview: PreviewResponse, passport?: Passport | null): Explanation {
  const payload = preview.outbound_payload
  if (preview.status === 'blocked' || !payload) {
    // Nothing was prepared: no field handling or detection happened, so none is shown.
    const reasons = preview.reason_codes.map((c) => BLOCK_REASONS[c] ?? `Blocked by the owner policy (${c}).`)
    return { kind: 'blocked', reasons: reasons.length ? reasons : ['The owner policy blocked this request.'] }
  }

  const rows: ExplanationRow[] = []
  const dropped = new Set(preview.dropped_fields)

  // 1. Columns kept: what the owner allows for this purpose and the payload actually carries.
  const kept = (passport?.outbound_fields ?? ['message']).filter((f) => !dropped.has(f))
  for (const field of kept) {
    if (field !== 'message' || payload.messages.length > 0) {
      rows.push({
        key: `keep-${field}`, field: fieldName(field), result: 'Included', tone: 'included',
        explanation: PURPOSE_NEED[payload.purpose] ?? 'Allowed by the owner for this purpose',
      })
    }
  }

  // 2. Columns removed entirely before review.
  for (const field of preview.dropped_fields) {
    rows.push({
      key: `drop-${field}`, field: fieldName(field), result: 'Removed', tone: 'removed',
      explanation: 'Not permitted for this purpose',
    })
  }

  // 3. Owner-required checks inside the kept text. redaction_counts lists exactly the
  //    types the server applied for this preview, including zero counts.
  const counted = Object.keys(preview.redaction_counts)
  const known: readonly string[] = SUPPORTED_TYPES
  const required = [...known.filter((t) => counted.includes(t)), ...counted.filter((t) => !known.includes(t))]
  for (const type of required) {
    const n = preview.redaction_counts[type] ?? 0
    const numbered = type === 'PERSON' && passport?.person_style === 'numbered'
    rows.push({
      key: `inside-${type}`,
      field: INSIDE_NAMES[type] ?? `${type} inside messages`,
      result: n > 0 ? `Redacted · ${matches(n)}` : 'Checked · no matches',
      tone: n > 0 ? 'redacted' : 'checked',
      explanation: n > 0
        ? `Required by company policy${numbered ? '; each person gets a numbered placeholder for this request' : ''}`
        : 'Required by company policy; the automatic check found none',
    })
  }

  // 4. What the policy does not check automatically (so "no matches" is never read as "no PII").
  const notRequired = SUPPORTED_TYPES.filter((t) => !(t in preview.redaction_counts)).map((t) => NOT_REQUIRED_NAMES[t])
  rows.push({
    key: 'unchecked',
    field: 'Other details inside messages',
    result: 'Not auto-checked',
    tone: 'unchecked',
    explanation: notRequired.length
      ? `This policy does not require checks for ${list(notRequired)}, or for other personal details. Review each message.`
      : 'Other personal details are not detected automatically. Review each message.',
  })

  const hiddenMessages = preview.hidden_message_indices.length
  const hidden = new Set(preview.hidden_message_indices)
  const textRedactions = (preview.custom_redactions ?? []).filter((c) => !hidden.has(c.message_index)).length
  return { kind: 'rows', rows, yourChoices: { hiddenMessages, textRedactions } }
}

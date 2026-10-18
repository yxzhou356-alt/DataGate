// Wording for the creator-only receipt timeline. Pure and dependency-free (tested with
// `node --test`). Delivery is derived from the receipt fields, never assumed.
import type { Receipt } from './types.ts'

export type Delivery = 'not_called' | 'unconfirmed' | 'acknowledged'

/**
 * receiver_attempts = 0  -> the receiver was never invoked;
 * attempts > 0, no confirmed hash -> invoked, delivery not confirmed (may be uncertain);
 * attempts > 0 and a confirmed hash on a sent request -> acknowledged.
 */
export function deliveryOf(r: Pick<Receipt, 'receiver_attempts' | 'confirmed_sent_payload_hash' | 'status'>): Delivery {
  if (r.receiver_attempts === 0) return 'not_called'
  if (r.status === 'sent' && r.confirmed_sent_payload_hash) return 'acknowledged'
  return 'unconfirmed'
}

export const DELIVERY_TEXT: Record<Delivery, { label: string; detail: string; tone: 'muted' | 'warn' | 'ok' }> = {
  not_called: { label: 'Receiver not called', detail: 'Nothing left DataGate for this request.', tone: 'muted' },
  unconfirmed: { label: 'Called, not confirmed', detail: 'The receiver was invoked but did not confirm delivery. DataGate did not retry.', tone: 'warn' },
  acknowledged: { label: 'Delivered and acknowledged', detail: 'The receiver acknowledged exactly the approved payload.', tone: 'ok' },
}

export const OUTCOME_TEXT: Record<string, { label: string; tone: 'ok' | 'stop' | 'warn' }> = {
  sent: { label: 'Sent', tone: 'ok' },
  blocked: { label: 'Blocked', tone: 'stop' },
  stale: { label: 'Out of date', tone: 'warn' },
  send_failed: { label: 'Not confirmed', tone: 'warn' },
}

export const REASON_TEXT: Record<string, string> = {
  REDACTION_REQUIRED: 'Owner rules required redaction',
  PURPOSE_NOT_ALLOWED: 'Purpose not allowed by the owner',
  DESTINATION_NOT_ALLOWED: 'Destination not allowed by the owner',
  SHARING_PROHIBITED: 'Owner prohibits sharing this dataset',
  ACCESS_REVOKED: 'Access was revoked before sending',
  DATASET_CHANGED: 'Source data changed after the preview',
  POLICY_CHANGED: 'Owner policy changed after the preview',
  PREVIEW_CHANGED: 'Prepared content changed after review',
  TRANSFORM_CHANGED: 'Redaction pipeline changed after the preview',
  DETECTOR_UNAVAILABLE: 'Required person-name detection was unavailable',
}

/** "2 email addresses, 1 phone number removed · 1 message hidden · 2 text redactions by you" */
export function redactionSummary(r: Pick<Receipt, 'redaction_counts' | 'additional_hidden_messages' | 'additional_custom_redactions' | 'review_revision'>): string {
  if (r.review_revision === null) return 'Not scanned: blocked before a preview was prepared'
  const words: Record<string, [string, string]> = {
    EMAIL: ['email address', 'email addresses'], PHONE: ['phone number', 'phone numbers'], PERSON: ['person name', 'person names'],
  }
  const auto = Object.entries(r.redaction_counts)
    .filter(([, n]) => n > 0)
    .map(([t, n]) => `${n} ${(words[t] ?? [t, t])[n === 1 ? 0 : 1]}`)
  const parts = [auto.length ? `${auto.join(', ')} removed by owner rules` : 'No supported identifiers detected']
  const hidden = r.additional_hidden_messages
  const custom = r.additional_custom_redactions ?? 0
  if (hidden) parts.push(`${hidden} ${hidden === 1 ? 'message' : 'messages'} hidden by you`)
  if (custom) parts.push(`${custom} text ${custom === 1 ? 'redaction' : 'redactions'} by you`)
  return parts.join(' · ')
}

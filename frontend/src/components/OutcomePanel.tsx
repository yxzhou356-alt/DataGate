import type { Receipt, SendResponse } from '../types'
import { decisionLabel, destinationLabel, purposeLabel, receiverLabel, redactionCountLabel } from '../labels'

interface Props {
  receipt: Receipt | null
  sendResult: SendResponse | null
  datasetName: string | null
  onStartOver: () => void
}

const STAMPS: Record<string, { label: string; tone: string; text: string }> = {
  sent: { label: 'Sent', tone: 'ok', text: 'The receiver acknowledged the approved payload.' },
  blocked: { label: 'Blocked', tone: 'stop', text: 'Owner rules stopped this request. Nothing was sent.' },
  send_failed: { label: 'Not confirmed', tone: 'warn', text: 'The receiver was called but did not confirm delivery. DataGate does not retry automatically.' },
}

const REASONS: Record<string, string> = {
  REDACTION_REQUIRED: 'Email addresses or phone numbers were hidden',
  PURPOSE_NOT_ALLOWED: 'The owner does not allow this purpose',
  DESTINATION_NOT_ALLOWED: 'The owner does not allow this destination',
  SHARING_PROHIBITED: 'The owner does not allow this dataset to be shared',
  ACCESS_REVOKED: 'Your access was revoked before sending',
}

export function OutcomePanel({ receipt, sendResult, datasetName, onStartOver }: Props) {
  if (!receipt) return null
  const stamp = STAMPS[receipt.status] ?? { label: receipt.status, tone: 'warn', text: '' }
  const redactions = Object.entries(receipt.redaction_counts)
    .filter(([, count]) => count > 0)
    .map(([type, count]) => redactionCountLabel(type, count))
    .join(', ')
  const receiverActivity = receipt.receiver_attempts === 0
    ? `${receiverLabel(receipt.receiver_mode)} was not called`
    : `${receiverLabel(receipt.receiver_mode)} called ${receipt.receiver_attempts} time${receipt.receiver_attempts === 1 ? '' : 's'}`

  return (
    <section className="outcome" aria-live="polite">
      <div className={`stamp stamp-${stamp.tone}`} role="status">{stamp.label}</div>
      <p className="outcome-text">{stamp.text}</p>
      {receipt.reason_codes.length > 0 && (
        <ul className="reasons">
          {receipt.reason_codes.map((c) => <li key={c}>{REASONS[c] ?? c}</li>)}
        </ul>
      )}

      {sendResult && (
        <div className="ack">
          <span className="ack-title">Receiver acknowledgement</span>
          <p>{sendResult.receiver_result.note}</p>
          <p>Entries received (including hidden-message placeholders): {sendResult.receiver_result.message_count}</p>
        </div>
      )}

      <h3 className="receipt-title">Activity receipt</h3>
      <p className="receipt-note">A safe summary of what DataGate did. It contains no customer values or message text.</p>
      <dl className="receipt">
        <Row k="Feedback source" v={datasetName ?? receipt.dataset_id} />
        <Row k="Requested use" v={purposeLabel(receipt.purpose)} />
        <Row k="Selected receiver" v={destinationLabel(receipt.destination)} />
        <Row k="Rule decision" v={decisionLabel(receipt.decision)} />
        <Row k="Automatically removed" v={receipt.review_revision === null ? 'Not scanned — blocked before preview' : redactions || 'No supported identifiers detected'} />
        <Row k="Messages hidden by you" v={receipt.additional_hidden_messages} />
        <Row k="Text redacted by you" v={receipt.additional_custom_redactions ?? 0} />
        <Row k="Receiver activity" v={receiverActivity} />
        <Row k="Recorded" v={receipt.occurred_at ? new Date(receipt.occurred_at).toLocaleString() : '—'} />
      </dl>
      <details className="technical-details">
        <summary>Technical verification details</summary>
        <p>These identifiers and fingerprints support audit and change detection.</p>
        <dl className="receipt technical-receipt">
          <Row k="Reference ID" v={receipt.request_id} code />
          <Row k="Demo account ID" v={receipt.account_id} />
          <Row k="Source ID / version" v={`${receipt.dataset_id} / ${receipt.dataset_revision ?? '—'}`} />
          <Row k="Rule set at decision" v={receipt.policy_version ?? '—'} />
          <Row k="Rule set at preview" v={receipt.preview_policy_version ?? 'No preview prepared'} />
          <Row k="Prepared fingerprint" v={receipt.prepared_payload_hash ?? '—'} code />
          <Row k="Confirmed sent fingerprint" v={receipt.confirmed_sent_payload_hash ?? 'Not confirmed'} code />
        </dl>
      </details>
      <button className="btn btn-secondary" onClick={onStartOver}>Start a new request</button>
    </section>
  )
}

function Row({ k, v, code }: { k: string; v: string | number; code?: boolean }) {
  return (
    <div>
      <dt>{k}</dt>
      <dd>{code ? <code className="hash">{v}</code> : v}</dd>
    </div>
  )
}

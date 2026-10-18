import type { Receipt, SendResponse } from '../types'
import { decisionLabel } from '../labels'
import { downloadJson } from '../download'

interface Props {
  receipt: Receipt | null
  sendResult: SendResponse | null
  onStartOver: () => void
}

const STAMPS: Record<string, { label: string; tone: string; text: string }> = {
  sent: { label: 'Sent', tone: 'ok', text: 'The receiver acknowledged the approved payload.' },
  blocked: { label: 'Blocked', tone: 'stop', text: 'Owner rules stopped this request. Nothing was sent.' },
  send_failed: { label: 'Not confirmed', tone: 'warn', text: 'The receiver was called but did not confirm delivery. DataGate does not retry automatically.' },
}

const REASONS: Record<string, string> = {
  REDACTION_REQUIRED: 'Supported identifiers were hidden by owner rules',
  PURPOSE_NOT_ALLOWED: 'The owner does not allow this purpose',
  DESTINATION_NOT_ALLOWED: 'The owner does not allow this destination',
  SHARING_PROHIBITED: 'The owner does not allow this dataset to be shared',
  ACCESS_REVOKED: 'Your access was revoked before sending',
}

export function OutcomePanel({ receipt, sendResult, onStartOver }: Props) {
  if (!receipt) return null
  const stamp = STAMPS[receipt.status] ?? { label: receipt.status, tone: 'warn', text: '' }

  return (
    <section className="outcome" aria-live="polite">
      <div className={`stamp stamp-${stamp.tone}`} role="status">{stamp.label}</div>
      <p className="outcome-text">{stamp.text}</p>
      <div className="receiver-call-counter"><strong>{receipt.receiver_attempts}</strong><span>actual adapter call{receipt.receiver_attempts === 1 ? '' : 's'} for this request</span></div>
      {receipt.reason_codes.length > 0 && (
        <ul className="reasons">
          {receipt.reason_codes.map((c) => <li key={c}>{REASONS[c] ?? c}</li>)}
        </ul>
      )}

      {sendResult && (
        <div className="ack">
          <span className="ack-title">Receiver acknowledgement</span>
          <p>{sendResult.receiver_result.note}</p>
          <p>Messages received: {sendResult.receiver_result.message_count}</p>
        </div>
      )}

      <h3 className="receipt-title">Receipt</h3>
      <p className="receipt-note">Metadata only. No customer values or message text are stored in it.</p>
      <dl className="receipt">
        <Row k="Request" v={receipt.request_id} code />
        <Row k="Account" v={receipt.account_id} />
        <Row k="Dataset" v={`${receipt.dataset_id} (revision ${receipt.dataset_revision ?? '—'})`} />
        <Row k="Purpose → destination" v={`${receipt.purpose} → ${receipt.destination}`} />
        <Row k="Decision" v={decisionLabel(receipt.decision)} />
        <Row k="Policy version at decision" v={receipt.policy_version ?? '—'} />
        <Row k="Policy version at preview" v={receipt.preview_policy_version ?? 'No preview prepared'} />
        <Row k="Redactions" v={Object.entries(receipt.redaction_counts).map(([t, n]) => `${t} ${n}`).join(', ') || '—'} />
        <Row k="Messages hidden by you" v={receipt.additional_hidden_messages} />
        <Row k="Prepared payload hash" v={receipt.prepared_payload_hash ?? '—'} code />
        <Row k="Confirmed sent hash" v={receipt.confirmed_sent_payload_hash ?? 'Not confirmed'} code />
        <Row k="Receiver" v={`${receipt.receiver_mode}, ${receipt.receiver_attempts} call${receipt.receiver_attempts === 1 ? '' : 's'}`} />
        <Row k="Recorded" v={receipt.occurred_at ? new Date(receipt.occurred_at).toLocaleString() : '—'} />
      </dl>
      <button className="btn btn-secondary" onClick={() => downloadJson(receipt, `datagate-receipt-${receipt.request_id}.json`)}>Download receipt JSON</button>
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

import type { PreviewResponse } from '../types'
import { decisionLabel } from '../labels'
import { shortHash } from '../redaction'

export interface ReviewChange {
  fromRevision: number
  toRevision: number
  previousHash: string | null
}

interface Props {
  preview: PreviewResponse
  confirmed: boolean
  busy: boolean
  disabledReason: string | null
  lastChange: ReviewChange | null
  onConfirm: (value: boolean) => void
  onSend: () => void
}

export function ApprovalPanel({ preview, confirmed, busy, disabledReason, lastChange, onConfirm, onSend }: Props) {
  const changed = lastChange && lastChange.toRevision === preview.review_revision ? lastChange : null
  return (
    <section className="step approval" aria-labelledby="step-send">
      <h2 id="step-send" className="step-title"><span className="step-no">3</span>Approve and send</h2>
      <dl className="facts">
        <div><dt>Company rule</dt><dd className={`decision decision-${preview.decision}`}>{decisionLabel(preview.decision)}</dd></div>
        <div><dt>Content version</dt><dd>Review {preview.review_revision}</dd></div>
      </dl>
      {changed && (
        <p className="review-changed" role="status">
          Review updated from {changed.fromRevision} to {changed.toRevision}. The content fingerprint changed, so approve again.
        </p>
      )}
      <p className="approval-note">
        DataGate rechecks your access, the source data and the owner policy when you press send.
        If anything changed, nothing is sent and you'll be asked for a fresh preview.
      </p>
      <details className="technical-details">
        <summary>Technical verification details</summary>
        <p>DataGate uses these values to detect any change between review and send.</p>
        <dl className="technical-facts">
          <div><dt>Review revision</dt><dd>{preview.review_revision}{changed && <span className="tech-updated"> (was {changed.fromRevision})</span>}</dd></div>
          <div><dt>Source version</dt><dd>{preview.dataset_revision}</dd></div>
          <div><dt>Rule set version</dt><dd>{preview.policy_version}</dd></div>
          <div><dt>Hidden messages (0-based)</dt><dd>{preview.hidden_message_indices.length ? preview.hidden_message_indices.join(', ') : 'none'}</dd></div>
          <div className="facts-wide">
            <dt>Content fingerprint (SHA-256)</dt>
            <dd><code className="hash">{preview.preview_hash}</code></dd>
          </div>
          {changed && (
            <div className="facts-wide">
              <dt>Previous fingerprint</dt>
              <dd><code className="hash">{shortHash(changed.previousHash)}</code> <span className="tech-updated">no longer approvable</span></dd>
            </div>
          )}
        </dl>
      </details>
      <label className="confirm">
        <input type="checkbox" checked={confirmed && !disabledReason} onChange={(e) => onConfirm(e.target.checked)} disabled={!!disabledReason} />
        <span>I reviewed the messages above and approve sending exactly this content.</span>
      </label>
      <button className="btn btn-primary btn-send" disabled={busy || !confirmed || !!disabledReason} onClick={onSend}>
        {busy ? 'Working…' : 'Approve and send'}
      </button>
      {disabledReason && <p className="hint" role="status">{disabledReason}</p>}
    </section>
  )
}

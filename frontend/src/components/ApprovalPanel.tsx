import type { PreviewResponse } from '../types'
import { decisionLabel } from '../labels'

interface Props {
  preview: PreviewResponse
  confirmed: boolean
  busy: boolean
  disabledReason: string | null
  onConfirm: (value: boolean) => void
  onSend: () => void
}

export function ApprovalPanel({ preview, confirmed, busy, disabledReason, onConfirm, onSend }: Props) {
  return (
    <section className="step approval" aria-labelledby="step-send">
      <h2 id="step-send" className="step-title"><span className="step-no">3</span>Approve and send</h2>
      <dl className="facts">
        <div><dt>Policy decision</dt><dd className={`decision decision-${preview.decision}`}>{decisionLabel(preview.decision)}</dd></div>
        <div><dt>Review revision</dt><dd>{preview.review_revision}</dd></div>
        <div><dt>Dataset revision</dt><dd>{preview.dataset_revision}</dd></div>
        <div><dt>Policy version</dt><dd>{preview.policy_version}</dd></div>
        <div className="facts-wide">
          <dt>Fingerprint of this exact payload (SHA-256)</dt>
          <dd><code className="hash">{preview.preview_hash}</code></dd>
        </div>
      </dl>
      <p className="approval-note">
        DataGate rechecks your access, the source data and the owner policy when you press send.
        If anything changed, nothing is sent and you'll be asked for a fresh preview.
      </p>
      <label className="confirm">
        <input type="checkbox" checked={confirmed} onChange={(e) => onConfirm(e.target.checked)} disabled={busy || !!disabledReason} />
        <span>I reviewed the messages above and approve sending exactly this content.</span>
      </label>
      <button className="btn btn-primary btn-send" disabled={busy || !confirmed || !!disabledReason} onClick={onSend}>
        {busy ? 'Working…' : 'Approve and send'}
      </button>
      {disabledReason && <p className="hint">{disabledReason}</p>}
    </section>
  )
}

import type { PreviewResponse } from '../types'
import { redactionCountLabel, redactionLabel, redactionShortLabel, sourceFieldLabel } from '../labels'
import { HIDDEN_MARKER, countPlaceholders, placeholderTypes, segmentMessage } from '../redaction'

export interface ReviewFailure {
  code: string
  message: string
  action: string
  /** The server confirmed it left the review unchanged (e.g. NO_CONTENT_TO_SEND). */
  previewUnchanged: boolean
  index: number
}

interface Props {
  preview: PreviewResponse
  editable: boolean
  /** Failed delivery is uncertain and must not be described as zero dispatch. */
  outcome: 'draft' | 'sent' | 'not_sent' | 'unconfirmed'
  busy: boolean
  /** Message whose include/hide change is in flight, if any. */
  pendingIndex: number | null
  failure: ReviewFailure | null
  /** Placeholder counts last seen in server text for each message, so hidden cards can say what restoring brings back. */
  knownRedactions: Record<number, Record<string, number>>
  onToggle: (index: number) => void
  onDismissFailure: () => void
}

/** A server-issued placeholder as a locked bar. Text is rendered as React text nodes only. */
function RedactionMarker({ type }: { type: string }) {
  return (
    <span className="redaction" title={`${redactionShortLabel(type)} removed — required by owner policy`}>
      <span className="redaction-label" aria-hidden="true">{redactionShortLabel(type)}</span>
      <span className="sr-only">[{redactionShortLabel(type)} removed, required by owner policy]</span>
    </span>
  )
}

function MessageText({ text, types }: { text: string; types: string[] }) {
  return (
    <>
      {segmentMessage(text, types).map((s, i) =>
        s.kind === 'redaction' ? <RedactionMarker key={i} type={s.type} /> : <span key={i}>{s.text}</span>,
      )}
    </>
  )
}

function countsText(counts: Record<string, number>): string {
  return Object.entries(counts).filter(([, n]) => n > 0).map(([t, n]) => redactionCountLabel(t, n)).join(', ')
}

export function ManifestReview({
  preview, editable, outcome, busy, pendingIndex, failure, knownRedactions, onToggle, onDismissFailure,
}: Props) {
  const payload = preview.outbound_payload
  if (!payload) return null
  const types = placeholderTypes(Object.keys(preview.redaction_counts))
  const redactions = Object.entries(preview.redaction_counts).filter(([, n]) => n > 0)
  const total = payload.messages.length
  const visible = payload.messages.filter((m) => m !== HIDDEN_MARKER).length

  return (
    <section className="step manifest" aria-labelledby="step-review">
      <h2 id="step-review" className="step-title"><span className="step-no">2</span>Review exactly what leaves</h2>

      <div className="review-summary">
        <div className="summary-block">
          <h3 className="summary-title">Columns removed entirely</h3>
          <p className="summary-help">These columns are dropped before review. None of their values are shown here or sent.</p>
          <ul className="field-chips" aria-label="Columns removed entirely">
            {preview.dropped_fields.map((f) => <li key={f} className="field-chip">{sourceFieldLabel(f)}</li>)}
          </ul>
        </div>
        <div className="summary-block">
          <h3 className="summary-title">Replaced inside messages</h3>
          <p className="summary-help">
            {redactions.length === 0
              ? 'No email addresses or phone numbers were found in the messages.'
              : `${redactions.map(([t, n]) => redactionCountLabel(t, n)).join(' and ')} replaced across all messages.`}
          </p>
          <p className="legend">
            {(types.length ? types : ['EMAIL']).map((t) => <RedactionMarker key={t} type={t} />)}
            <span className="lock-note"><span className="lock" aria-hidden="true" />Required by owner policy. Locked; cannot be undone here.</span>
          </p>
        </div>
        <p className="summary-help">
          Automatic detection covers {types.map(redactionLabel).join(' and ') || 'supported identifiers'} only.
          Read each message for other sensitive details and hide any you do not want to share.
        </p>
      </div>

      <div className="instruction">
        <span className="instruction-label">Instruction sent with the messages</span>
        <q>{payload.instruction}</q>
      </div>

      <p className="review-count" aria-live="polite">
        <strong>{visible} of {total}</strong> messages included
        {total - visible > 0 && <> · {total - visible} hidden by you</>}
      </p>

      {failure && (
        <div className="review-failure" role="alert">
          <p><strong>{failure.message}</strong> {failure.action}</p>
          {failure.previewUnchanged
            ? <p>Nothing changed. The preview below is still the current review.</p>
            : <p>DataGate could not confirm whether the change was applied. Approval stays off until the preview is confirmed.</p>}
          <div className="notice-actions">
            {!failure.previewUnchanged && editable && (
              <button className="btn btn-secondary" disabled={busy} onClick={() => onToggle(failure.index)}>Try again</button>
            )}
            {failure.previewUnchanged && <button className="btn btn-quiet" onClick={onDismissFailure}>Keep current preview</button>}
          </div>
        </div>
      )}

      <ol className="review-cards">
        {payload.messages.map((message, index) => {
          const hidden = message === HIDDEN_MARKER
          const lastVisible = !hidden && visible === 1
          const pending = pendingIndex === index
          const counts = hidden ? knownRedactions[index] : countPlaceholders(message, types)
          const detected = counts ? countsText(counts) : ''
          const headingId = `msg-${index}-title`
          return (
            <li key={index} className={`review-card ${hidden ? 'is-hidden' : ''} ${pending ? 'is-pending' : ''}`} aria-labelledby={headingId}>
              <div className="card-head">
                <h3 id={headingId} className="card-title">Message {index + 1} <span className="card-of">of {total}</span></h3>
                <span className={`state-badge ${hidden ? 'state-hidden' : 'state-included'}`}>
                  {pending ? 'Updating…' : hidden ? 'Hidden by you' : 'Included'}
                </span>
              </div>

              <p className="message-text">
                {hidden
                  ? <span className="hidden-note">Withheld. The receiver gets a “hidden by user” placeholder, not this message.</span>
                  : <MessageText text={message} types={types} />}
              </p>

              <div className="card-foot">
                <p className="card-detected">
                  {hidden
                    ? detected
                      ? <>Restoring brings back the server’s redacted version ({detected} still removed).</>
                      : <>Restoring brings back the server’s redacted version.</>
                    : detected
                      ? <><span className="lock" aria-hidden="true" />{detected} removed · required by owner policy</>
                      : 'No email or phone detected'}
                </p>
                {editable && (
                  <button
                    className="btn btn-quiet card-toggle"
                    // aria-disabled (not disabled) while busy, so keyboard focus stays on the button during the update.
                    disabled={lastVisible}
                    aria-disabled={busy || lastVisible}
                    aria-describedby={lastVisible ? `msg-${index}-last` : undefined}
                    aria-label={`${hidden ? 'Restore' : 'Hide'} message ${index + 1}`}
                    onClick={() => { if (!busy) onToggle(index) }}
                  >
                    {pending ? 'Updating…' : hidden ? 'Restore redacted version' : 'Hide from send'}
                  </button>
                )}
              </div>
              {editable && lastVisible && (
                <p id={`msg-${index}-last`} className="card-hint">At least one message must stay included.</p>
              )}
            </li>
          )
        })}
      </ol>
      <p className="manifest-foot">
        {outcome === 'sent' && `${visible} of ${total} messages were sent.`}
        {outcome === 'not_sent' && 'Nothing from this preview was sent.'}
        {outcome === 'unconfirmed' && 'The receiver was called, but delivery was not confirmed. DataGate will not resend automatically.'}
        {outcome === 'draft' && `${visible} of ${total} messages will be sent after you approve. ` +
          'Hiding a message replaces it with a placeholder, so the receiver still sees how many were withheld.'}
      </p>
    </section>
  )
}

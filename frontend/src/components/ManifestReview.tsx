import type { PreviewResponse } from '../types'
import { redactionCountLabel, sourceFieldLabel } from '../labels'

const HIDDEN = '[HIDDEN_BY_USER]'
const TOKEN = /(\[EMAIL\]|\[PHONE\])/g

interface Props {
  preview: PreviewResponse
  editable: boolean
  /** Failed delivery is uncertain and must not be described as zero dispatch. */
  outcome: 'draft' | 'sent' | 'not_sent' | 'unconfirmed'
  busy: boolean
  onToggle: (index: number) => void
}

/** Renders a retained message with mandatory redactions shown as solid bars. */
function MessageText({ text }: { text: string }) {
  const parts = text.split(TOKEN)
  return (
    <>
      {parts.map((part, i) =>
        part === '[EMAIL]' || part === '[PHONE]' ? (
          <span key={i} className="redaction" title={`Removed by owner rule: ${part}`}>
            <span className="redaction-label">{part === '[EMAIL]' ? 'email' : 'phone'}</span>
          </span>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  )
}

export function ManifestReview({ preview, editable, outcome, busy, onToggle }: Props) {
  const payload = preview.outbound_payload
  if (!payload) return null
  const redactions = Object.entries(preview.redaction_counts).filter(([, n]) => n > 0)
  const visible = payload.messages.filter((m) => m !== HIDDEN).length

  return (
    <section className="step manifest" aria-labelledby="step-review">
      <h2 id="step-review" className="step-title"><span className="step-no">2</span>Review exactly what leaves</h2>

      <div className="rules">
        <p>
          <strong>Removed columns.</strong>{' '}
          {preview.dropped_fields.map(sourceFieldLabel).join(', ')}. Only the message text may leave.
        </p>
        <p>
          <strong>Hidden inside messages.</strong>{' '}
          {redactions.length === 0
            ? 'No email addresses or phone numbers were found.'
            : redactions.map(([t, n]) => redactionCountLabel(t, n)).join(' and ') + '.'}{' '}
          The owner requires this and it can't be undone here.
        </p>
        <p>Automatic detection covers email addresses and supported phone formats. Review for other sensitive details and hide any message you do not want to share.</p>
      </div>

      <div className="instruction">
        <span className="instruction-label">Instruction sent with the messages</span>
        <q>{payload.instruction}</q>
      </div>

      <ol className="messages" start={0}>
        {payload.messages.map((message, index) => {
          const hidden = message === HIDDEN
          const lastVisible = !hidden && visible === 1
          return (
            <li key={index} className={`message ${hidden ? 'is-hidden' : ''}`}>
              <span className="message-index" aria-hidden="true">{index + 1}</span>
              <p className="message-text">
                {hidden ? <span className="hidden-note">Hidden by you. Only a placeholder is shared, not this message.</span> : <MessageText text={message} />}
              </p>
              {editable && (
                <button
                  className="btn btn-quiet"
                  disabled={busy || lastVisible}
                  title={lastVisible ? 'At least one message must stay visible.' : undefined}
                  aria-label={`${hidden ? 'Include' : 'Hide'} message ${index + 1}`}
                  onClick={() => onToggle(index)}
                >
                  {hidden ? 'Include' : 'Hide'}
                </button>
              )}
            </li>
          )
        })}
      </ol>
      <p className="manifest-foot">
        {outcome === 'sent' && `${visible} of ${payload.messages.length} messages were sent.`}
        {outcome === 'not_sent' && 'Nothing from this preview was sent.'}
        {outcome === 'unconfirmed' && 'The receiver was called, but delivery was not confirmed. DataGate will not resend automatically.'}
        {outcome === 'draft' && `${visible} of ${payload.messages.length} messages will be sent after you approve. ` +
          'Hiding a message replaces it with a placeholder, so the receiver still sees how many were withheld.'}
      </p>
    </section>
  )
}

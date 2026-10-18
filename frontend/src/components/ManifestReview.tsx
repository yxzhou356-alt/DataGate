import type { PreviewResponse } from '../types'
import { redactionLabel } from '../labels'
import { MessageComparison } from './MessageComparison'
import type { ManualSpan } from '../types'

const HIDDEN = '[HIDDEN_BY_USER]'
const TOKEN = /(\[(?:EMAIL|PHONE|PERSON_\d+|MANUAL(?:_REDACTION)?|REDACTED(?:_BY_USER)?)\])/g

interface Props {
  preview: PreviewResponse
  editable: boolean
  /** draft: not sent yet; sent: receiver acknowledged; not_sent: blocked, stale or unconfirmed */
  outcome: 'draft' | 'sent' | 'not_sent' | 'uncertain'
  busy: boolean
  onToggle: (index: number) => void
  onAddSpan: (span: ManualSpan) => void
  onRemoveSpan: (span: ManualSpan) => void
}

/** Renders a retained message with mandatory redactions shown as solid bars. */
function MessageText({ text }: { text: string }) {
  const parts = text.split(TOKEN)
  return (
    <>
      {parts.map((part, i) =>
        /^\[(?:EMAIL|PHONE|PERSON_\d+|MANUAL(?:_REDACTION)?|REDACTED(?:_BY_USER)?)\]$/.test(part) ? (
          <span key={i} className="redaction" title={`Removed by owner rule: ${part}`}>
            <span className="redaction-label">{part.slice(1, -1).toLowerCase()}</span>
          </span>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  )
}

export function ManifestReview({ preview, editable, outcome, busy, onToggle, onAddSpan, onRemoveSpan }: Props) {
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
          {preview.dropped_fields.join(', ')}. Only the message text may leave.
        </p>
        <p>
          <strong>Hidden inside messages.</strong>{' '}
          {redactions.length === 0
            ? 'No supported sensitive patterns were found.'
            : redactions.map(([t, n]) => `${n} ${redactionLabel(t)}`).join(' and ') + '.'}{' '}
          The owner requires this and it can't be undone here.
        </p>
      </div>

      <div className={`detector-note ${preview.detector_status?.available ? '' : 'detector-unavailable'}`}>
        <strong>Person-name detector: {preview.detector_status?.available ? preview.detector_status.model : 'unavailable'}</strong>
        <p>{preview.detector_status?.available ? `Pretrained model${preview.detector_status.version ? ` v${preview.detector_status.version}` : ''}; no custom model training. Repeated detected names use stable PERSON_n placeholders within this request.` : 'Email and phone rules still run. Names and other unsupported details may be missed; this is not a guarantee of anonymity.'}</p>
      </div>

      {!preview.raw_view_allowed && <p className="raw-view-notice">Your account may process this dataset but cannot view original message text or select manual text ranges. Whole-message hiding is still available.</p>}

      <div className="instruction">
        <span className="instruction-label">Instruction sent with the messages</span>
        <q>{payload.instruction}</q>
      </div>

      <ol className="messages" start={0}>
        {payload.messages.map((message, index) => {
          const hidden = message === HIDDEN
          const lastVisible = !hidden && visible === 1
          const original = preview.raw_view_allowed ? preview.original_messages?.[index] : undefined
          if (original !== undefined) return <MessageComparison
            key={`${preview.request_id}-${preview.review_revision}-${index}`}
            index={index} source={original} outbound={message}
            findings={(preview.findings ?? []).filter(finding => finding.message_index === index)}
            manualSpans={(preview.manual_spans ?? []).filter(span => span.message_index === index)}
            editable={editable} busy={busy} lastVisible={lastVisible}
            onToggleMessage={() => onToggle(index)}
            onAddSpan={span => onAddSpan({ message_index: index, ...span })}
            onRemoveSpan={span => onRemoveSpan({ message_index: index, ...span })}
          />
          return (
            <li key={index} className={`message ${hidden ? 'is-hidden' : ''}`}>
              <span className="message-index" aria-hidden="true">{index + 1}</span>
              <p className="message-text">
                {hidden ? <span className="hidden-note">Hidden by you. This message won't be sent.</span> : <MessageText text={message} />}
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
        {outcome === 'sent' && `The receiver acknowledged this payload. ${visible} of ${payload.messages.length} message entries retain content; hidden entries contain only placeholders.`}
        {outcome === 'not_sent' && 'Nothing from this preview was sent.'}
        {outcome === 'uncertain' && 'Delivery was attempted but not confirmed. Do not assume nothing left the gateway; there is no automatic retry.'}
        {outcome === 'draft' && `${visible} of ${payload.messages.length} message entries retain content. ` +
          'Hiding replaces an entry with a placeholder; the receiver still sees the number of entries after approval.'}
      </p>
    </section>
  )
}

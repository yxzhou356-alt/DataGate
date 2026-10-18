import { useEffect, useState } from 'react'
import type { CustomRedaction, Passport, PreviewResponse } from '../types'
import { redactionCountLabel, redactionLabel, redactionShortLabel } from '../labels'
import { PolicyExplanation } from './PolicyExplanation'
import {
  HIDDEN_MARKER, buildReviewSegments, countPlaceholders, cpToUnit, placeholderTypes, renderSegments, segmentMessage, snapSelection,
  type CpSpan, type ReviewSegment,
} from '../redaction'

export interface ReviewFailure {
  code: string
  message: string
  action: string
  /** The server confirmed it left the review unchanged (e.g. NO_CONTENT_TO_SEND). */
  previewUnchanged: boolean
  index: number
  /** The review state that was attempted, for an exact retry. */
  hide: number[]
  custom?: CustomRedaction[]
}

interface Props {
  preview: PreviewResponse
  /** Owner passport of the previewed dataset (null if no longer visible), for the explanation table. */
  passport: Passport | null
  editable: boolean
  /** Failed delivery is uncertain and must not be described as zero dispatch. */
  outcome: 'draft' | 'sent' | 'not_sent' | 'unconfirmed'
  busy: boolean
  /** Message whose review change is in flight, if any. */
  pendingIndex: number | null
  failure: ReviewFailure | null
  /** Owner-placeholder counts of each message's base text, so hidden cards can say what restoring brings back. */
  knownRedactions: Record<number, Record<string, number>>
  /** Server-issued mandatory-redacted text per message; custom offsets refer to it. */
  baseTexts: Record<number, string>
  onToggle: (index: number) => void
  onAddCustom: (index: number, span: CpSpan) => void
  /** start null removes every custom redaction in the message. */
  onRemoveCustom: (index: number, start: number | null) => void
  onRetryFailure: () => void
  onDismissFailure: () => void
}

/** A raw selection inside one message, in UTF-16 indices of that message's base text. */
type RawSelection = { hash: string | null; index: number; start: number; end: number } | { hash: string | null; multi: true }

/** A server-issued owner placeholder as a locked bar. Text is rendered as React text nodes only. */
function RedactionMarker({ type, ordinal, seg }: { type: string; ordinal?: number; seg?: ReviewSegment }) {
  // Numbered people read as "person 1": the same number means the same name within this request.
  const label = `${redactionShortLabel(type)}${ordinal ? ` ${ordinal}` : ''}`
  return (
    <span className="redaction" title={`${label} removed — required by owner policy`} {...segData(seg)}>
      <span className="redaction-label" aria-hidden="true">{label}</span>
      <span className="sr-only">[{label} removed, required by owner policy]</span>
    </span>
  )
}

function segData(seg?: ReviewSegment) {
  return seg ? { 'data-kind': seg.kind, 'data-start': seg.start, 'data-end': seg.end } : {}
}

/** Read-only rendering of server text (used when the editable model is unavailable). */
function MessageText({ text, types }: { text: string; types: string[] }) {
  return (
    <>
      {segmentMessage(text, types).map((s, i) =>
        s.kind === 'redaction' ? <RedactionMarker key={i} type={s.type} ordinal={s.ordinal} /> : <span key={i}>{s.text}</span>,
      )}
    </>
  )
}

/** Editable rendering: every segment carries its base-text offsets so a DOM selection maps back to them. */
function ReviewText({ segments, editable, busy, index, onRemove }: {
  segments: ReviewSegment[]; editable: boolean; busy: boolean; index: number; onRemove: (start: number) => void
}) {
  return (
    <>
      {segments.map((s) => {
        if (s.kind === 'text') return <span key={s.start} {...segData(s)}>{s.text}</span>
        if (s.kind === 'redaction') return <RedactionMarker key={s.start} type={s.type} ordinal={s.ordinal} seg={s} />
        const label = <span className="redaction-label" aria-hidden="true">you</span>
        return editable ? (
          <button
            key={s.start} type="button" className="redaction redaction-custom" {...segData(s)}
            aria-disabled={busy}
            aria-label={`Text redacted by you in message ${index + 1}. Activate to undo this redaction.`}
            title="Redacted by you — click to undo"
            onClick={(e) => {
              if (busy) return
              // The marker disappears after the update; keep keyboard focus in this message.
              e.currentTarget.closest<HTMLElement>('.message-text')?.focus()
              onRemove(s.cpStart)
            }}
          >{label}</button>
        ) : (
          <span key={s.start} className="redaction redaction-custom" title="Redacted by you" {...segData(s)}>
            {label}<span className="sr-only">[text redacted by you]</span>
          </span>
        )
      })}
    </>
  )
}

/** Maps a DOM selection boundary to a UTF-16 offset in the base text of `container`. */
function pointOffset(container: HTMLElement, node: Node, offset: number, edge: 'start' | 'end'): number {
  const length = Number(container.dataset.length)
  if (!container.contains(node)) {
    // Boundary outside this message (e.g. triple-click): clamp to the nearer end.
    return node.compareDocumentPosition(container) & Node.DOCUMENT_POSITION_FOLLOWING ? 0 : length
  }
  if (node === container) {
    const child = container.childNodes[offset] as HTMLElement | undefined
    return child?.dataset?.start !== undefined ? Number(child.dataset.start) : length
  }
  let el: Node | null = node
  while (el && el.parentNode !== container) el = el.parentNode
  if (!(el instanceof HTMLElement) || el.dataset.start === undefined) return edge === 'start' ? 0 : length
  const start = Number(el.dataset.start)
  const end = Number(el.dataset.end)
  if (el.dataset.kind === 'text' && node.nodeType === Node.TEXT_NODE) return start + offset
  // Inside a marker: snap to the marker edge (the helper also expands to the whole marker).
  return edge === 'start' ? start : end
}

/** "a", "a and b", "a, b and c" */
function listText(items: string[]): string {
  return items.length <= 2 ? items.join(' and ') : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
}

function countsText(counts: Record<string, number>): string {
  return Object.entries(counts).filter(([, n]) => n > 0).map(([t, n]) => redactionCountLabel(t, n)).join(', ')
}

function excerpt(text: string): string {
  return text.length > 60 ? `${text.slice(0, 57)}…` : text
}

export function ManifestReview({
  preview, passport, editable, outcome, busy, pendingIndex, failure, knownRedactions, baseTexts,
  onToggle, onAddCustom, onRemoveCustom, onRetryFailure, onDismissFailure,
}: Props) {
  const [rawSelection, setRawSelection] = useState<RawSelection | null>(null)
  const hash = preview.preview_hash

  // Track text selections inside message cards. A collapsed selection keeps the last
  // one, so tapping the Redact button on touch devices does not lose it.
  useEffect(() => {
    if (!editable) return
    const onChange = () => {
      const sel = document.getSelection()
      if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return
      const range = sel.getRangeAt(0)
      const msgOf = (n: Node) => (n instanceof Element ? n : n.parentElement)?.closest<HTMLElement>('.message-text[data-editable="true"]') ?? null
      const startMsg = msgOf(range.startContainer)
      const endMsg = msgOf(range.endContainer)
      const container = startMsg ?? endMsg
      if (!container) return
      if (startMsg && endMsg && startMsg !== endMsg) { setRawSelection({ hash, multi: true }); return }
      setRawSelection({
        hash,
        index: Number(container.dataset.index),
        start: pointOffset(container, range.startContainer, range.startOffset, 'start'),
        end: pointOffset(container, range.endContainer, range.endOffset, 'end'),
      })
    }
    document.addEventListener('selectionchange', onChange)
    return () => document.removeEventListener('selectionchange', onChange)
  }, [editable, hash])

  const payload = preview.outbound_payload
  if (!payload) return null
  const types = placeholderTypes(Object.keys(preview.redaction_counts))
  const total = payload.messages.length
  const visible = payload.messages.filter((m) => m !== HIDDEN_MARKER).length
  // A backend that predates custom redactions omits this field; partial redaction is then unavailable.
  const supportsCustom = Array.isArray(preview.custom_redactions)
  const custom = preview.custom_redactions ?? []
  const customFor = (i: number) => custom.filter((c) => c.message_index === i)
  const customVisible = custom.filter((c) => !preview.hidden_message_indices.includes(c.message_index)).length
  // Only a selection made against the current preview counts.
  const selection = rawSelection && rawSelection.hash === hash ? rawSelection : null
  const clearSelection = () => { setRawSelection(null); document.getSelection()?.removeAllRanges() }

  return (
    <section className="step manifest" aria-labelledby="step-review">
      <h2 id="step-review" className="step-title"><span className="step-no">2</span>Review exactly what leaves</h2>

      <div className="review-summary">
        <PolicyExplanation preview={preview} passport={passport} />
        <div className="summary-block">
          <h3 className="summary-title">Markers in the messages</h3>
          <p className="legend">
            {(types.length ? types : ['EMAIL']).map((t) => <RedactionMarker key={t} type={t} />)}
            <span className="lock-note"><span className="lock" aria-hidden="true" />Required by owner policy. Locked; cannot be undone here.</span>
          </p>
          <p className="legend">
            <span className="redaction redaction-custom" aria-hidden="true"><span className="redaction-label">you</span></span>
            <span className="legend-text">Redacted by you. Select text in a message, then choose “Redact selection”. Click a marker to undo it.</span>
          </p>
        </div>
        <p className="summary-help">
          {editable && !supportsCustom && (
            <strong className="compat-note">Partial redaction is unavailable: the DataGate backend is older than this page. Restart the backend, then prepare a new preview. </strong>
          )}
          Automatic detection covers {listText(types.map(redactionLabel)) || 'supported identifiers'} only.
          Read each message for other sensitive details. Redact part of a message, or hide the whole message.
        </p>
      </div>

      <div className="instruction">
        <span className="instruction-label">Instruction sent with the messages</span>
        <q>{payload.instruction}</q>
      </div>

      <p className="review-count" aria-live="polite">
        <strong>{visible} of {total}</strong> messages included
        {total - visible > 0 && <> · {total - visible} hidden by you</>}
        {customVisible > 0 && <> · {customVisible} text {customVisible === 1 ? 'redaction' : 'redactions'} by you</>}
      </p>

      {selection && 'multi' in selection && editable && (
        <p className="card-hint" role="status">Select text within one message at a time.</p>
      )}

      {failure && (
        <div className="review-failure" role="alert">
          <p><strong>{failure.message}</strong> {failure.action}</p>
          {failure.previewUnchanged
            ? <p>Nothing changed. The preview below is still the current review.</p>
            : <p>DataGate could not confirm whether the change was applied. Approval stays off until the preview is confirmed.</p>}
          <div className="notice-actions">
            {!failure.previewUnchanged && editable && (
              <button className="btn btn-secondary" disabled={busy} onClick={onRetryFailure}>Try again</button>
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
          const mine = customFor(index)
          const base = baseTexts[index]
          // Build the editable model from the server's base text and spans, and use it only if it
          // reproduces the server's outbound text exactly. Otherwise fall back to read-only text.
          const segments = !hidden && base !== undefined ? buildReviewSegments(base, mine, types) : null
          const verified = segments !== null && renderSegments(segments) === message
          const canRedact = editable && verified && supportsCustom
          const ownerCounts = base !== undefined ? countPlaceholders(base, types) : hidden ? knownRedactions[index] : countPlaceholders(message, types)
          const detected = ownerCounts ? countsText(ownerCounts) : ''
          const sel = selection && !('multi' in selection) && selection.index === index && segments && base !== undefined
            ? { raw: selection, span: snapSelection(base, segments, selection.start, selection.end) }
            : null
          // Show exactly the span that will be requested (after snapping), from the server's base text.
          const selText = sel?.span && base !== undefined
            ? excerpt(base.slice(cpToUnit(base, sel.span.start), cpToUnit(base, sel.span.end)))
            : ''
          const headingId = `msg-${index}-title`
          return (
            <li key={index} className={`review-card ${hidden ? 'is-hidden' : ''} ${pending ? 'is-pending' : ''}`} aria-labelledby={headingId}>
              <div className="card-head">
                <h3 id={headingId} className="card-title">Message {index + 1} <span className="card-of">of {total}</span></h3>
                <span className={`state-badge ${hidden ? 'state-hidden' : 'state-included'}`}>
                  {pending ? 'Updating…' : hidden ? 'Hidden by you' : 'Included'}
                </span>
              </div>

              <p
                className={`message-text ${canRedact ? 'is-selectable' : ''}`}
                data-index={index}
                data-editable={canRedact ? 'true' : 'false'}
                data-length={base?.length ?? 0}
                tabIndex={-1}
              >
                {hidden
                  ? <span className="hidden-note">Withheld. The receiver gets a “hidden by user” placeholder, not this message.</span>
                  : verified
                    ? <ReviewText segments={segments} editable={editable} busy={busy} index={index} onRemove={(start) => onRemoveCustom(index, start)} />
                    : <MessageText text={message} types={types} />}
              </p>

              {sel && canRedact && (
                <div className="selection-bar" role="group" aria-label={`Selection in message ${index + 1}`}>
                  {sel.span ? (
                    <>
                      <span className="selection-text">Selected: <q>{selText}</q></span>
                      <button
                        type="button" className="btn btn-secondary btn-small"
                        aria-disabled={busy}
                        // Keep the text selection when the button takes the pointer.
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => { if (!busy && sel.span) { onAddCustom(index, sel.span); clearSelection() } }}
                      >Redact selection</button>
                    </>
                  ) : (
                    <span className="selection-text">That selection is already redacted or only whitespace.</span>
                  )}
                  <button type="button" className="btn btn-quiet" onMouseDown={(e) => e.preventDefault()} onClick={clearSelection}>Cancel</button>
                </div>
              )}

              <div className="card-foot">
                <p className="card-detected">
                  {hidden
                    ? <>
                        {detected
                          ? <>Restoring brings back the server’s redacted version ({detected} still removed).</>
                          : <>Restoring brings back the server’s redacted version.</>}
                        {mine.length > 0 && <> Your {mine.length} text {mine.length === 1 ? 'redaction is' : 'redactions are'} kept.</>}
                      </>
                    : <>
                        {detected
                          ? <><span className="lock" aria-hidden="true" />{detected} removed · required by owner policy</>
                          : 'Nothing found by owner rules'}
                        {mine.length > 0 && <>&nbsp;· {mine.length} redacted by you</>}
                      </>}
                </p>
                {editable && (
                  <span className="card-actions">
                    {!hidden && mine.length > 0 && (
                      <button
                        type="button" className="btn btn-quiet" aria-disabled={busy}
                        aria-label={`Undo all of your text redactions in message ${index + 1}`}
                        onClick={() => { if (!busy) onRemoveCustom(index, null) }}
                      >Undo my redactions</button>
                    )}
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
                  </span>
                )}
              </div>
              {editable && !hidden && !verified && supportsCustom && (
                <p className="card-hint">Partial redaction is unavailable for this message. You can still hide it.</p>
              )}
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
          'Hidden messages and text you redact are replaced with placeholders on the server, never edited in the browser.'}
      </p>
    </section>
  )
}

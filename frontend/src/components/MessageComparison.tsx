import { useRef, useState } from 'react'
import { readSourceSelection, textareaSelectionOffsets } from '../reviewSelection'

export interface DisplayFinding {
  id: string
  start: number
  end: number
  category: string
  replacement: string
  mandatory: boolean
}

export interface DisplaySpan { start: number; end: number }

interface Props {
  index: number
  source: string
  outbound: string
  findings: DisplayFinding[]
  manualSpans: DisplaySpan[]
  editable: boolean
  busy: boolean
  lastVisible: boolean
  onToggleMessage: () => void
  onAddSpan: (span: DisplaySpan) => void
  onRemoveSpan: (span: DisplaySpan) => void
}

const PLACEHOLDERS = /(\[(?:EMAIL|PHONE|PERSON_\d+|MANUAL(?:_REDACTION)?|REDACTED(?:_BY_USER)?|HIDDEN_BY_USER)\])/g

function OutboundText({ text }: { text: string }) {
  return <>{text.split(PLACEHOLDERS).map((part, index) => /^\[(?:EMAIL|PHONE|PERSON_\d+|MANUAL(?:_REDACTION)?|REDACTED(?:_BY_USER)?|HIDDEN_BY_USER)\]$/.test(part)
    ? <span key={index} className={`redaction ${part.startsWith('[PERSON_') ? 'redaction-person' : ''}`} title={`Outgoing placeholder ${part}`}><span className="redaction-label">{part.slice(1, -1).toLowerCase()}</span></span>
    : <span key={index}>{part}</span>)}</>
}

function SourceText({ source, findings, manualSpans }: { source: string; findings: DisplayFinding[]; manualSpans: DisplaySpan[] }) {
  const characters = Array.from(source)
  const intervals = [...findings.map(f => ({ ...f, kind: f.category.toLowerCase().split('+')[0] })), ...manualSpans.map(s => ({ ...s, kind: 'manual' }))]
  const boundaries = [...new Set([0, characters.length, ...intervals.flatMap(s => [s.start, s.end])])].filter(n => n >= 0 && n <= characters.length).sort((a, b) => a - b)
  return <>{boundaries.slice(0, -1).map((start, index) => {
    const end = boundaries[index + 1]
    const active = intervals.filter(f => f.start < end && f.end > start)
    const text = characters.slice(start, end).join('')
    return active.length ? <mark key={start} className={`finding-highlight finding-${active.some(f => f.kind === 'manual') ? 'manual' : active[0].kind}`} title={active.map(f => f.kind).join(', ')}>{text}</mark> : <span key={start}>{text}</span>
  })}</>
}

export function MessageComparison({ index, source, outbound, findings, manualSpans, editable, busy, lastVisible, onToggleMessage, onAddSpan, onRemoveSpan }: Props) {
  const sourceRef = useRef<HTMLParagraphElement>(null)
  const [selection, setSelection] = useState<{ start: number; end: number; selected: string } | null>(null)
  const hidden = outbound === '[HIDDEN_BY_USER]'
  const captureSelection = () => {
    if (!editable || busy || !sourceRef.current) return
    const next = readSourceSelection(sourceRef.current, source)
    if (next) setSelection(next)
  }

  return <li className={`comparison-message ${hidden ? 'is-hidden' : ''}`}>
    <div className="comparison-heading"><strong>Message {index + 1}</strong><button className="btn btn-quiet" disabled={!editable || busy || lastVisible} onClick={onToggleMessage} title={lastVisible ? 'At least one message must remain.' : undefined}>{hidden ? 'Include message' : 'Hide entire message'}</button></div>
    <div className="comparison-columns">
      <div className="comparison-source"><span className="comparison-label">Original · authorized source</span><p className="message-text selectable-source" ref={sourceRef} onMouseUp={captureSelection} onKeyUp={captureSelection}><SourceText source={source} findings={findings} manualSpans={manualSpans} /></p></div>
      <div className="comparison-output"><span className="comparison-label">Exact outgoing message</span><p className="message-text">{hidden ? <span className="hidden-note">[HIDDEN_BY_USER] — the placeholder is sent, not the original text.</span> : <OutboundText text={outbound} />}</p></div>
    </div>
    {findings.length > 0 && <ul className="finding-tags" aria-label={`Required redactions in message ${index + 1}`}>{findings.map(f => <li key={f.id} className={`finding-tag finding-tag-${f.category.toLowerCase().split('+')[0]}`}><span aria-hidden="true">▣</span> {f.category} → {f.replacement}<span className="finding-locked">{f.mandatory ? 'locked' : 'detected'}</span></li>)}</ul>}
    {manualSpans.length > 0 && <ul className="manual-span-list" aria-label={`Additional redactions in message ${index + 1}`}>{manualSpans.map(span => <li key={`${span.start}-${span.end}`}><span>Manual range {span.start}–{span.end}</span><button className="btn btn-quiet" disabled={!editable || busy} onClick={() => onRemoveSpan(span)} aria-label={`Remove manual range ${span.start} to ${span.end} from message ${index + 1}`}>Remove</button></li>)}</ul>}
    {editable && !hidden && <div className="manual-selection">
      <p className="hint">Select words in the original to hide an extra detail. Required hiding stays locked.</p>
      <details className="selection-keyboard"><summary>Keyboard-friendly text selection</summary><textarea readOnly aria-label={`Select original text from message ${index + 1} for additional redaction`} value={source} onSelect={event => { const el = event.currentTarget; const next = textareaSelectionOffsets(source, el.selectionStart, el.selectionEnd); if (next) setSelection(next) }} /></details>
      {selection && <div className="selection-action"><span>Selected: <q>{selection.selected}</q></span><button className="btn btn-secondary" disabled={busy} onClick={() => { onAddSpan({ start: selection.start, end: selection.end }); setSelection(null); window.getSelection()?.removeAllRanges() }}>Redact selection</button><button className="btn btn-quiet" disabled={busy} onClick={() => setSelection(null)}>Cancel</button></div>}
    </div>}
  </li>
}

import type { AuditResponse } from '../types'
import { downloadJson } from '../download'
import { decisionLabel } from '../labels'

export function AuditDetail({ audit, onClose }: { audit: AuditResponse; onClose: () => void }) {
  return <section className="step audit-detail" aria-labelledby="audit-detail-title">
    <div className="section-heading"><div><span className="section-kicker">REQUEST TIMELINE</span><h2 id="audit-detail-title">From request to decision.</h2></div><button className="btn btn-quiet" onClick={onClose}>Close details</button></div>
    <dl className="audit-summary"><div><dt>Request</dt><dd><code>{audit.request.request_id}</code></dd></div><div><dt>Dataset</dt><dd>{audit.request.dataset_id}</dd></div><div><dt>Decision / status</dt><dd>{decisionLabel(audit.request.decision)} / {audit.request.status}</dd></div><div><dt>Receiver calls</dt><dd>{audit.request.receiver_attempts}</dd></div></dl>
    <ol className="audit-timeline">{audit.events.map(event => <li key={event.event_id}><div><strong>{event.event_type.replace(/_/g, ' ')}</strong><time dateTime={event.occurred_at}>{new Date(event.occurred_at).toLocaleString()}</time></div><p>{event.actor_kind} · {event.actor_id}</p><details><summary>Event metadata</summary><pre>{JSON.stringify(event.metadata, null, 2)}</pre></details></li>)}</ol>
    {audit.events.length === 0 && <p className="hint">No events were returned for this request.</p>}
    {audit.receipt ? <details className="audit-receipt"><summary>Inspect final metadata receipt</summary><pre>{JSON.stringify(audit.receipt, null, 2)}</pre><button className="btn btn-secondary" onClick={() => downloadJson(audit.receipt, `datagate-receipt-${audit.request.request_id}.json`)}>Download receipt</button></details> : <p className="hint">No final receipt is available yet. The timeline still records this request's progress.</p>}
    <div className="report-footer"><p>Metadata-only export. Raw source messages and payloads are excluded.</p><button className="btn btn-secondary" onClick={() => downloadJson(audit, `datagate-audit-${audit.request.request_id}.json`)}>Export request audit</button></div>
  </section>
}

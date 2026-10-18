import { useState } from 'react'
import type { HistoryResponse } from '../types'
import { decisionLabel } from '../labels'
import { downloadJson } from '../download'

interface Props {
  history: HistoryResponse | null
  accountId: string
  busy: boolean
  onRefresh: () => void
  onOpenReceipt: (requestId: string) => void
}

export function AuditHistory({ history, accountId, busy, onRefresh, onOpenReceipt }: Props) {
  const entries = history?.requests ?? []
  const [status, setStatus] = useState('all')
  const [decision, setDecision] = useState('all')
  const [dataset, setDataset] = useState('all')
  const [search, setSearch] = useState('')
  const filtered = entries.filter(entry => (status === 'all' || entry.status === status) && (decision === 'all' || entry.decision === decision) && (dataset === 'all' || entry.dataset_id === dataset) && `${entry.request_id} ${entry.dataset_id}`.toLowerCase().includes(search.toLowerCase()))
  const exportRecords = () => downloadJson({
    exported_at: new Date().toISOString(),
    scope: 'current_demo_account',
    filters: { status, decision, dataset, account_id: accountId },
    requests: filtered,
  }, 'datagate-audit-history.json')

  return <section className="step audit-history" aria-labelledby="history-title">
    <div className="section-heading"><div><span className="section-kicker">ACCOUNT-SCOPED HISTORY</span><h2 id="history-title">A record of your requests.</h2></div><div className="button-group"><button className="btn btn-quiet" disabled={busy} onClick={onRefresh}>{busy ? 'Refreshing…' : 'Refresh history'}</button><button className="btn btn-secondary" disabled={!filtered.length} onClick={exportRecords}>Export filtered metadata</button></div></div>
    <p className="approval-note">The backend returns only this account's request metadata. Receipts remain readable after access revocation; raw source text is never included here.</p>
    <div className="history-filters"><label className="field"><span className="field-label">User</span><select value={accountId} disabled aria-label="History user (current account only)"><option value={accountId}>{accountId} · current account only</option></select></label><label className="field"><span className="field-label">Dataset</span><select value={dataset} onChange={event => setDataset(event.target.value)}><option value="all">All your datasets</option>{[...new Set(entries.map(entry => entry.dataset_id))].map(id => <option value={id} key={id}>{id}</option>)}</select></label><label className="field"><span className="field-label">Status</span><select value={status} onChange={event => setStatus(event.target.value)}><option value="all">All statuses</option>{['ready', 'blocked', 'stale', 'sending', 'sent', 'send_failed'].map(value => <option value={value} key={value}>{value.replace('_', ' ')}</option>)}</select></label><label className="field"><span className="field-label">Decision</span><select value={decision} onChange={event => setDecision(event.target.value)}><option value="all">All decisions</option><option value="allow">Allowed</option><option value="redact">Redacted</option><option value="block">Blocked</option></select></label><label className="field history-search"><span className="field-label">Find a request</span><input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Request ID or dataset" /></label></div>
    <p className="hint">{filtered.length} of {entries.length} loaded requests match. {history && history.total > entries.length ? `${history.total} total requests; the backend returns the latest 200.` : ''}</p>
    {!filtered.length ? <div className="evidence-empty">{entries.length ? 'No requests match these filters.' : 'No requests recorded for this account yet. Prepare a preview to begin.'}</div> : <div className="table-scroll"><table className="history-table"><caption className="sr-only">Your request history</caption><thead><tr><th>Request / dataset</th><th>Purpose</th><th>Decision</th><th>Status</th><th>Calls</th><th>Recorded</th><th>Audit</th></tr></thead><tbody>{filtered.map(entry => <tr key={entry.request_id}><th scope="row"><code className="history-request-id">{entry.request_id}</code><small>{entry.dataset_id}</small></th><td>{entry.purpose}</td><td>{decisionLabel(entry.decision)}</td><td><span className={`result-pill ${entry.status === 'sent' ? 'result-pass' : entry.status === 'blocked' || entry.status === 'send_failed' ? 'result-fail' : 'result-info'}`}>{entry.status.replace('_', ' ')}</span></td><td>{entry.receiver_attempts}</td><td>{new Date(entry.occurred_at ?? entry.created_at).toLocaleString()}</td><td><button className="btn btn-quiet" disabled={busy} onClick={() => onOpenReceipt(entry.request_id)}>View audit</button></td></tr>)}</tbody></table></div>}
  </section>
}

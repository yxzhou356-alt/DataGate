import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, describeError } from '../api'
import type { DatasetSummary, ReceiptListItem, TimelineStatus } from '../types'
import { decisionLabel, destinationLabel, purposeLabel, receiverLabel } from '../labels'
import { DELIVERY_TEXT, OUTCOME_TEXT, REASON_TEXT, deliveryOf, redactionSummary } from '../timeline'

const PAGE_SIZE = 20
const STATUS_OPTIONS: { value: '' | TimelineStatus; label: string }[] = [
  { value: '', label: 'All outcomes' },
  { value: 'sent', label: 'Sent' },
  { value: 'blocked', label: 'Blocked' },
  { value: 'send_failed', label: 'Not confirmed' },
  { value: 'stale', label: 'Out of date' },
]

interface Props {
  token: string
  /** Currently accessible datasets, used only to show friendly names. */
  datasets: DatasetSummary[]
  onError: (err: unknown) => void
}

type Page = { items: ReceiptListItem[]; next: string | null }

export function ReceiptTimeline({ token, datasets, onError }: Props) {
  const [status, setStatus] = useState<'' | TimelineStatus>('')
  const [datasetId, setDatasetId] = useState('')
  const [page, setPage] = useState<Page | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Ignore responses from superseded requests (e.g. a filter changed mid-flight).
  const generation = useRef(0)
  // Dataset ids seen in this history, so revoked datasets stay filterable.
  const [seenDatasets, setSeenDatasets] = useState<string[]>([])

  const load = useCallback(async (cursor: string | null) => {
    const gen = ++generation.current
    setLoading(true)
    setError(null)
    try {
      const res = await api.listReceipts(token, {
        limit: PAGE_SIZE, status: status || undefined, dataset_id: datasetId || undefined, cursor: cursor ?? undefined,
      })
      if (gen !== generation.current) return
      setPage((prev) => ({ items: cursor && prev ? [...prev.items, ...res.receipts] : res.receipts, next: res.next_cursor }))
      setSeenDatasets((prev) => [...new Set([...prev, ...res.receipts.map((r) => r.dataset_id)])].sort())
    } catch (err) {
      if (gen !== generation.current) return
      setError(describeError(err, 'The history could not be loaded.'))
      // Let the app handle session expiry; a missing route is explained here, not as a second banner.
      if (!(err instanceof ApiError && err.code === 'NOT_FOUND')) onError(err)
    } finally {
      if (gen === generation.current) setLoading(false)
    }
  }, [token, status, datasetId, onError])

  useEffect(() => { load(null) }, [load])

  const nameOf = (id: string) => datasets.find((d) => d.dataset_id === id)?.display_name ?? id
  const datasetOptions = [...new Set([...datasets.map((d) => d.dataset_id), ...seenDatasets])].sort()
  const filtered = status !== '' || datasetId !== ''

  return (
    <section className="timeline" aria-labelledby="history-title">
      <div className="timeline-head">
        <h2 id="history-title" className="timeline-title">My request history</h2>
        <p className="timeline-note">
          Metadata receipts for your own finished or blocked requests. Only you can see them, and they stay readable
          after dataset access is revoked. They never contain message text, payloads or detected values.
        </p>
      </div>

      <div className="timeline-filters">
        <label className="field">
          <span className="field-label">Outcome</span>
          <select value={status} onChange={(e) => setStatus(e.target.value as '' | TimelineStatus)} disabled={loading}>
            {STATUS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </label>
        <label className="field">
          <span className="field-label">Feedback source</span>
          <select value={datasetId} onChange={(e) => setDatasetId(e.target.value)} disabled={loading}>
            <option value="">All sources</option>
            {datasetOptions.map((id) => <option key={id} value={id}>{nameOf(id)}</option>)}
          </select>
        </label>
        <button className="btn btn-quiet" onClick={() => load(null)} disabled={loading}>Refresh</button>
      </div>

      {error && <div className="notice" role="alert"><p><strong>{error}</strong></p></div>}

      {page && page.items.length === 0 && !error && (
        <p className="timeline-empty">
          {filtered ? 'No receipts match these filters.' : 'No receipts yet. Send or block a request and it will appear here.'}
        </p>
      )}

      {page && page.items.length > 0 && (
        <ol className="timeline-list" aria-live="polite">
          {page.items.map((r) => <TimelineEntry key={r.request_id} r={r} datasetName={nameOf(r.dataset_id)} />)}
        </ol>
      )}

      <div className="timeline-more">
        {loading && <span role="status">Loading…</span>}
        {!loading && page?.next && <button className="btn btn-secondary" onClick={() => load(page.next)}>Load older receipts</button>}
        {!loading && page && page.items.length > 0 && !page.next && <span className="timeline-end">End of history</span>}
      </div>
    </section>
  )
}

function TimelineEntry({ r, datasetName }: { r: ReceiptListItem; datasetName: string }) {
  const outcome = OUTCOME_TEXT[r.status] ?? { label: r.status, tone: 'warn' as const }
  const delivery = DELIVERY_TEXT[deliveryOf(r)]
  const when = new Date(r.recorded_at)
  return (
    <li className={`timeline-entry entry-${outcome.tone}`}>
      <div className="entry-head">
        <time className="entry-time" dateTime={r.recorded_at}>{when.toLocaleString()}</time>
        <span className={`entry-outcome outcome-${outcome.tone}`}>{outcome.label}</span>
      </div>
      <p className="entry-title">
        <strong>{datasetName}</strong> · {purposeLabel(r.purpose)} → {destinationLabel(r.destination)}
      </p>
      <p className={`entry-delivery delivery-${delivery.tone}`}>
        <strong>{delivery.label}</strong> <span>({r.receiver_attempts} {r.receiver_attempts === 1 ? 'call' : 'calls'}). {delivery.detail}</span>
      </p>
      <p className="entry-redactions">{redactionSummary(r)}</p>
      {r.reason_codes.length > 0 && (
        <ul className="entry-reasons">{r.reason_codes.map((c) => <li key={c}>{REASON_TEXT[c] ?? c}</li>)}</ul>
      )}
      <details className="technical-details">
        <summary>Technical metadata</summary>
        <dl className="receipt technical-receipt">
          <Row k="Reference ID" v={r.request_id} code />
          <Row k="Rule decision" v={decisionLabel(r.decision)} />
          <Row k="Source ID / version" v={`${r.dataset_id} / ${r.dataset_revision ?? '—'}`} />
          <Row k="Rule set at decision" v={r.policy_version ?? '—'} />
          <Row k="Rule set at preview" v={r.preview_policy_version ?? 'No preview prepared'} />
          <Row k="Review revision" v={r.review_revision ?? 'No preview prepared'} />
          <Row k="Prepared fingerprint" v={r.prepared_payload_hash ?? 'None (no preview)'} code />
          <Row k="Confirmed sent fingerprint" v={r.confirmed_sent_payload_hash ?? 'Not confirmed'} code />
          <Row k="Receiver" v={`${receiverLabel(r.receiver_mode)}, ${r.receiver_attempts} ${r.receiver_attempts === 1 ? 'attempt' : 'attempts'}`} />
          <Row k="Recorded (UTC)" v={r.occurred_at ?? `${r.recorded_at} (creation time; older record)`} />
        </dl>
      </details>
    </li>
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

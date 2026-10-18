import type { DatasetSummary } from '../types'
import {
  DESTINATIONS,
  PURPOSES,
  destinationLabel,
  outboundFieldLabel,
  purposeLabel,
  redactionLabel,
} from '../labels'

interface Props {
  datasets: DatasetSummary[]
  datasetId: string
  purpose: string
  destination: string
  busy: boolean
  onChange: (field: 'datasetId' | 'purpose' | 'destination', value: string) => void
  onPreview: () => void
}

export function RequestForm({ datasets, datasetId, purpose, destination, busy, onChange, onPreview }: Props) {
  const selected = datasets.find((d) => d.dataset_id === datasetId)

  return (
    <section className="step" aria-labelledby="step-request">
      <h2 id="step-request" className="step-title"><span className="step-no">1</span>Choose what to share</h2>

      {datasets.length === 0 ? (
        <p className="empty">
          This account has no feedback sources it may use. Ask the data owner for access, or switch account.
        </p>
      ) : (
        <fieldset className="field">
          <legend>Customer feedback source</legend>
          <p className="field-help">
            Choose the feedback collection this demo account is allowed to use. The original records stay in DataGate.
          </p>
          {datasets.map((d) => (
            <label key={d.dataset_id} className={`dataset-option ${d.dataset_id === datasetId ? 'is-on' : ''}`}>
              <input type="radio" name="dataset" value={d.dataset_id} checked={d.dataset_id === datasetId}
                disabled={busy}
                onChange={() => onChange('datasetId', d.dataset_id)} />
              <span className="dataset-name">{d.display_name}</span>
              <span className="dataset-meta">Source version {d.dataset_revision}</span>
            </label>
          ))}
        </fieldset>
      )}

      {selected && (
        <section className="passport-card" aria-labelledby="sharing-rules-title">
          <h3 id="sharing-rules-title">Company sharing rules</h3>
          <p>These rules are set by the data owner and cannot be loosened here.</p>
          <dl className="passport">
            <div><dt>Set by</dt><dd>{selected.passport.declared_owner}</dd></div>
            <div><dt>Approved use</dt><dd>{selected.passport.allowed_purposes.map(purposeLabel).join(', ')}</dd></div>
            <div><dt>Approved receiver</dt><dd>{selected.passport.allowed_destinations.map(destinationLabel).join(', ')}</dd></div>
            <div><dt>Content allowed to leave</dt><dd>{selected.passport.outbound_fields.map(outboundFieldLabel).join(', ')}</dd></div>
            <div><dt>Automatically removed</dt><dd>{selected.passport.required_redactions.map(redactionLabel).join(', ')}</dd></div>
            <div><dt>Sharing rule</dt><dd>{selected.passport.sharing_mode === 'none' ? 'Do not share' : 'Only after required redaction'}</dd></div>
          </dl>
          <details className="technical-details technical-details-compact">
            <summary>Rule set details</summary>
            <p>Policy version {selected.passport.policy_version}</p>
          </details>
        </section>
      )}

      <label className="field">
        <span className="field-label">What do you want to do?</span>
        <select value={purpose} disabled={busy} onChange={(e) => onChange('purpose', e.target.value)}>
          {PURPOSES.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
        </select>
        {purpose === 'model_training' && (
          <span className="field-help">This option is included to demonstrate a use blocked by the company rules.</span>
        )}
      </label>

      <label className="field">
        <span className="field-label">Where should the approved content go?</span>
        <select value={destination} disabled={busy} onChange={(e) => onChange('destination', e.target.value)}>
          {DESTINATIONS.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
        </select>
        <span className="field-help">
          {destination === 'demo_receiver'
            ? 'A local test receiver will capture the approved content. No external AI model is called.'
            : 'This option is included to demonstrate a receiver blocked by the company rules.'}
        </span>
      </label>

      <button className="btn btn-primary" disabled={busy || !datasetId} onClick={onPreview}>
        Prepare preview
      </button>
    </section>
  )
}

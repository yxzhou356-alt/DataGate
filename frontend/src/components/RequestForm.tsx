import type { DatasetSummary } from '../types'
import { DESTINATIONS, PURPOSES, destinationLabel, purposeLabel, redactionLabel } from '../labels'

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
          This account has no datasets it may use. Ask a dataset owner for access, or switch account.
        </p>
      ) : (
        <fieldset className="field">
          <legend>Dataset</legend>
          {datasets.map((d) => (
            <label key={d.dataset_id} className={`dataset-option ${d.dataset_id === datasetId ? 'is-on' : ''}`}>
              <input type="radio" name="dataset" value={d.dataset_id} checked={d.dataset_id === datasetId}
                disabled={busy}
                onChange={() => onChange('datasetId', d.dataset_id)} />
              <span className="dataset-name">{d.display_name}</span>
              <span className="dataset-meta">Revision {d.dataset_revision}</span>
            </label>
          ))}
        </fieldset>
      )}

      {selected && (
        <dl className="passport" aria-label="Owner rules for this dataset">
          <div><dt>Owner</dt><dd>{selected.passport.declared_owner}</dd></div>
          <div><dt>Allowed uses</dt><dd>{selected.passport.allowed_purposes.map(purposeLabel).join(', ')}</dd></div>
          <div><dt>Allowed destinations</dt><dd>{selected.passport.allowed_destinations.map(destinationLabel).join(', ')}</dd></div>
          <div><dt>Fields that may leave</dt><dd>{selected.passport.outbound_fields.join(', ')}</dd></div>
          <div><dt>Always hidden</dt><dd>{selected.passport.required_redactions.map(redactionLabel).join(', ')}</dd></div>
          <div><dt>Sharing</dt><dd>{selected.passport.sharing_mode === 'none' ? 'Not allowed' : 'Redacted only'}</dd></div>
          <div><dt>Policy version</dt><dd>{selected.passport.policy_version}</dd></div>
        </dl>
      )}

      <label className="field">
        <span className="field-label">Purpose</span>
        <select value={purpose} disabled={busy} onChange={(e) => onChange('purpose', e.target.value)}>
          {PURPOSES.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
        </select>
      </label>

      <label className="field">
        <span className="field-label">Send to</span>
        <select value={destination} disabled={busy} onChange={(e) => onChange('destination', e.target.value)}>
          {DESTINATIONS.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
        </select>
      </label>

      <button className="btn btn-primary" disabled={busy || !datasetId} onClick={onPreview}>
        Prepare preview
      </button>
    </section>
  )
}

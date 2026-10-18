import type { Passport, PreviewResponse } from '../types'
import { decisionLabel } from '../labels'
import { explainPreview } from '../explain'

interface Props {
  preview: PreviewResponse
  /** Owner passport of the previewed dataset, when the analyst can still see it. */
  passport: Passport | null
}

/** "How company rules protect this data": derived from the real preview response. */
export function PolicyExplanation({ preview, passport }: Props) {
  const e = explainPreview(preview, passport)

  if (e.kind === 'blocked') {
    return (
      <section className="policy-explain policy-blocked" aria-labelledby="policy-explain-title">
        <h3 id="policy-explain-title" className="summary-title">How company rules protect this data</h3>
        <p><strong>Blocked.</strong> Nothing was prepared, so no fields were processed and no checks ran.</p>
        <ul className="policy-reasons">
          {e.reasons.map((r) => <li key={r}>{r}</li>)}
        </ul>
      </section>
    )
  }

  const { hiddenMessages, textRedactions } = e.yourChoices
  return (
    <section className="policy-explain" aria-labelledby="policy-explain-title">
      <div className="policy-explain-head">
        <h3 id="policy-explain-title" className="summary-title">How company rules protect this data</h3>
        <span className={`decision decision-${preview.decision}`}>{decisionLabel(preview.decision)}</span>
      </div>
      <table className="policy-table">
        <caption className="sr-only">Each field and type of detail, what happens to it, and why</caption>
        <thead>
          <tr>
            <th scope="col">Field</th>
            <th scope="col">Result</th>
            <th scope="col">Explanation</th>
          </tr>
        </thead>
        <tbody>
          {e.rows.map((r) => (
            <tr key={r.key}>
              <th scope="row">{r.field}</th>
              <td><span className={`rule-result rule-${r.tone}`}>{r.result}</span></td>
              <td>{r.explanation}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="summary-help">
        Your own choices are separate from company rules:{' '}
        {hiddenMessages || textRedactions
          ? [hiddenMessages && `${hiddenMessages} ${hiddenMessages === 1 ? 'message' : 'messages'} hidden`,
             textRedactions && `${textRedactions} text ${textRedactions === 1 ? 'redaction' : 'redactions'}`]
              .filter(Boolean).join(' and ') + ' by you.'
          : 'none yet.'}
      </p>
    </section>
  )
}

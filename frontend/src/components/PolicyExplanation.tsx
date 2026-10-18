import type { PolicyExplanationRow } from '../types'

export function PolicyExplanation({ checks }: { checks: PolicyExplanationRow[] }) {
  if (!checks.length) return null
  return <section className="step policy-explanation" aria-labelledby="policy-explanation-title">
    <h2 className="step-title" id="policy-explanation-title">Why each field stays or leaves</h2>
    <p className="receipt-note">The backend evaluated these owner rules. Review choices may add protection; they cannot relax a rule.</p>
    <div className="table-scroll"><table className="policy-table"><caption className="sr-only">Field-level policy explanations</caption><thead><tr><th>Source field</th><th>Action</th><th>Owner rule</th><th>Explanation</th></tr></thead><tbody>{checks.map((check, index) => <tr key={`${check.field}-${index}`}><th scope="row"><code>{check.field}</code></th><td><span className={`result-pill ${check.result === 'included' ? 'result-pass' : check.result === 'excluded' ? 'result-info' : 'result-redacted'}`}>{check.result}</span></td><td><code>{check.rule_id}</code></td><td>{check.explanation}</td></tr>)}</tbody></table></div>
  </section>
}

import { downloadJson } from '../download'
import type { SecurityReportResponse } from '../types'

export function GovernanceTests({ result, busy, onRefresh }: { result: SecurityReportResponse | null; busy: boolean; onRefresh: () => void }) {
  const report = result?.report
  return <section className="step evidence-dashboard" aria-labelledby="evidence-title">
    <div className="section-heading"><div><span className="section-kicker">ACCESSCHECK EVIDENCE</span><h2 id="evidence-title">Real checks. Recorded results.</h2></div><button className="btn btn-primary" disabled={busy} onClick={onRefresh}>{busy ? 'Reading test report…' : 'Refresh test report'}</button></div>
    <p className="approval-note">This reads the backend's actual CLI-generated test report. Refreshing does not run tests, change permissions, or call an external model.</p>
    {!result?.available || !report ? <div className="evidence-empty"><strong>No generated test report is available.</strong><p>Run the command below from the backend environment, then refresh.</p><code>python -m app.security_report</code></div> : <>
      {result.stale && <div className="notice notice-stale" role="status"><p><strong>This report is stale.</strong> The source fingerprint changed after the recorded run. Regenerate it before using the results as evidence for current code.</p></div>}
      <dl className="evidence-summary"><div><dt>Passed / total</dt><dd>{report.passed}<span> / {report.total}</span></dd></div><div><dt>Failed / skipped</dt><dd>{report.failed}<span> / {report.skipped}</span></dd></div><div><dt>Actual duration</dt><dd>{report.duration_seconds.toFixed(3)}<span> seconds</span></dd></div></dl>
      <div className="table-scroll"><table className="evidence-table"><caption className="sr-only">Measured security controls</caption><thead><tr><th>Control</th><th>Result</th><th>Tests</th></tr></thead><tbody>{report.controls.map(control => <tr key={control.id}><th scope="row">{control.title}<small>{control.id}</small></th><td><span className={`result-pill ${control.status === 'passed' ? 'result-pass' : control.status === 'failed' ? 'result-fail' : 'result-info'}`}>{control.status.replace('_', ' ')}</span></td><td>{control.tests}</td></tr>)}</tbody></table></div>
      <details className="test-details"><summary>Inspect individual test results ({report.tests.length})</summary><div className="table-scroll"><table><caption className="sr-only">Individual tests from the recorded run</caption><thead><tr><th>Test</th><th>Result</th><th>Seconds</th></tr></thead><tbody>{report.tests.map(test => <tr key={test.id}><th scope="row"><code>{test.id}</code></th><td>{test.status}</td><td>{test.duration_seconds.toFixed(4)}</td></tr>)}</tbody></table></div></details>
      <dl className="report-provenance"><div><dt>Recorded</dt><dd>{new Date(report.generated_at).toLocaleString()}</dd></div><div><dt>Commit</dt><dd><code>{report.source_revision ?? 'Not available'}</code>{report.working_tree_dirty ? ' · uncommitted changes included' : ''}</dd></div><div><dt>Report fingerprint</dt><dd><code className="hash">{report.source_fingerprint}</code></dd></div><div><dt>Current fingerprint</dt><dd><code className="hash">{result.source_fingerprint}</code></dd></div><div><dt>Receiver mode</dt><dd>{report.receiver_mode}</dd></div></dl>
      <div className="report-footer"><p>Regenerate with <code>python -m app.security_report</code>.</p><button className="btn btn-secondary" onClick={() => downloadJson(report, 'datagate-security-report.json')}>Export actual report</button></div>
    </>}
    <p className="hint">Passing these fixtures demonstrates these configured cases. It is not a general security or privacy guarantee.</p>
  </section>
}

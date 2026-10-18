import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import type { EvidenceScenario, EvidenceView, ScenarioResult } from '../types'
import { FLAG_TEXT, ageText, assessEvidence, isEvidenceView, shortCommit } from '../evidence'

const GENERATE_CMD = 'cd backend && .venv/bin/python -m app.security_report'

const RESULT_TEXT: Record<ScenarioResult, string> = { passed: 'Passed', failed: 'Failed', not_run: 'Not run' }

type Load =
  | { state: 'idle' }
  | { state: 'error'; message: string }
  | { state: 'ready'; view: EvidenceView; loadedAt: number }

interface Props {
  onBack: () => void
}

export function EvidenceDashboard({ onBack }: Props) {
  const [load, setLoad] = useState<Load>({ state: 'idle' })
  // The previous result stays on screen while reloading, so the page never flashes empty.
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const view = await api.securityReport()
      setLoad(isEvidenceView(view)
        ? { state: 'ready', view, loadedAt: Date.now() }
        : { state: 'error', message: 'The backend returned an unexpected evidence format. Nothing is shown as passing.' })
    } catch (err) {
      setLoad({ state: 'error', message: err instanceof ApiError ? `${err.message} ${err.action}` : 'The report could not be loaded.' })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  return (
    <div className="app evidence-page">
      <header className="topbar">
        <span className="wordmark wordmark-small">DataGate</span>
        <span className="who">Security regression evidence</span>
        <button className="btn btn-quiet" onClick={onBack}>Back to the app</button>
      </header>

      <main className="evidence">
        <div className="evidence-head">
          <h1 className="evidence-title">What the security checks showed</h1>
          <button className="btn btn-secondary" onClick={refresh} disabled={loading}>
            {loading ? 'Loading…' : 'Reload report'}
          </button>
        </div>
        <p className="evidence-lede">
          Results come from the last run of the backend test suite on this machine, read from a metadata-only report file.
          This page never runs tests and never touches the demo database.
        </p>

        {load.state === 'idle' && <p className="evidence-lede" role="status">Loading the latest report…</p>}
        {load.state === 'error' && (
          <div className="verdict verdict-stop" role="alert">
            <p className="verdict-title">Report not loaded</p>
            <p>{load.message}</p>
          </div>
        )}
        {load.state === 'ready' && <ReportBody view={load.view} loadedAt={load.loadedAt} />}

        <section className="evidence-how" aria-labelledby="how-title">
          <h2 id="how-title" className="evidence-h2">Regenerate the evidence</h2>
          <p>Runs the full backend suite against temporary storage and an injected test receiver, then replaces the report file atomically:</p>
          <pre className="cmd"><code>{GENERATE_CMD}</code></pre>
          <p>Then choose <em>Reload report</em>. A report from another commit is labelled stale.</p>
        </section>
      </main>
    </div>
  )
}

function ReportBody({ view, loadedAt }: { view: EvidenceView; loadedAt: number }) {
  const verdict = assessEvidence(view)
  const r = view.report
  return (
    <>
      <div className={`verdict verdict-${verdict.tone}`} role="status">
        <p className="verdict-title">{verdict.title}</p>
        <p>{verdict.detail}</p>
        {verdict.flags.length > 0 && (
          <ul className="flags" aria-label="Report labels">
            {verdict.flags.map((f) => (
              <li key={f} className={`flag flag-${f}`} title={FLAG_TEXT[f].explain}>
                <strong>{FLAG_TEXT[f].label}</strong> <span>{FLAG_TEXT[f].explain}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <p className="disclaimer">{r?.disclaimer ?? view.disclaimer}</p>

      {r && (
        <>
          <div className="tiles" aria-label="Scenario totals">
            <Tile label="Passed" value={r.totals.passed} tone="ok" />
            <Tile label="Failed" value={r.totals.failed} tone="stop" />
            <Tile label="Not run" value={r.totals.not_run} tone="warn" />
          </div>

          <dl className="report-meta">
            <Meta k="Generated" v={`${new Date(r.generated_at).toLocaleString()} (${ageText(r.generated_at, loadedAt)})`} />
            <Meta k="Report commit" v={`${shortCommit(r.git.commit)}${r.git.dirty ? ' + uncommitted changes' : ''}`} code />
            <Meta k="Running commit" v={`${shortCommit(view.current_commit)}${view.current_dirty ? ' + uncommitted changes' : ''}`} code />
            <Meta k="Run" v={`${r.suite.run_status}, ${r.suite.tests_passed} of ${r.suite.tests_collected} tests passed in ${r.suite.duration_seconds.toFixed(1)} s`} />
            <Meta k="Command" v={r.suite.command} code />
            <Meta k="Storage" v={r.isolation.storage} />
            <Meta k="Receiver" v={r.isolation.receiver} />
            <Meta k="Runtime demo DB" v={r.isolation.runtime_db_unchanged === null ? 'Not present during the run'
              : r.isolation.runtime_db_unchanged ? 'Unchanged by the run' : 'Changed during the run'} />
          </dl>

          <h2 className="evidence-h2">Scenarios</h2>
          <ol className="scenarios">
            {r.scenarios.map((s) => <ScenarioRow key={s.id} s={s} />)}
          </ol>
        </>
      )}
    </>
  )
}

function ScenarioRow({ s }: { s: EvidenceScenario }) {
  return (
    <li className={`scenario scenario-${s.result}`}>
      <div className="scenario-head">
        <span className="scenario-id">{s.id}</span>
        <h3 className="scenario-title">{s.title}</h3>
        <span className={`result result-${s.result}`}>
          <span aria-hidden="true">{s.result === 'passed' ? '✓' : s.result === 'failed' ? '✕' : '–'}</span> {RESULT_TEXT[s.result]}
        </span>
      </div>
      <p className="scenario-claim">{s.claim}</p>
      <p className="scenario-stats">
        {s.tests_total === 0
          ? 'No mapped test ran.'
          : `${s.tests_passed} of ${s.tests_total} mapped tests passed${s.tests_failed ? `, ${s.tests_failed} failed` : ''}${s.tests_not_run ? `, ${s.tests_not_run} not run` : ''} · ${Math.round(s.duration_seconds * 1000)} ms`}
      </p>
      {s.failure_summary && <p className="scenario-summary">{s.failure_summary}</p>}
      {s.evidence.length > 0 && (
        <details className="scenario-evidence">
          <summary>Tests behind this result</summary>
          <ul>{s.evidence.map((e) => <li key={e}><code>{e}</code></li>)}</ul>
        </details>
      )}
    </li>
  )
}

function Tile({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className={`tile tile-${tone}`}>
      <span className="tile-value">{value}</span>
      <span className="tile-label">{label}</span>
    </div>
  )
}

function Meta({ k, v, code }: { k: string; v: string; code?: boolean }) {
  return (
    <div>
      <dt>{k}</dt>
      <dd>{code ? <code>{v}</code> : v}</dd>
    </div>
  )
}

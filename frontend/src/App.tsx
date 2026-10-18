import { useRef, useState } from 'react'
import { api, ApiError } from './api'
import type { Account, AuditResponse, DatasetSummary, HistoryResponse, ManualSpan, PreviewResponse, Receipt, SecurityReportResponse, SendResponse } from './types'
import { AccountGate } from './components/AccountGate'
import { RequestForm } from './components/RequestForm'
import { ManifestReview } from './components/ManifestReview'
import { ApprovalPanel } from './components/ApprovalPanel'
import { OutcomePanel } from './components/OutcomePanel'
import { PolicyExplanation } from './components/PolicyExplanation'
import { GovernanceTests } from './components/GovernanceTests'
import { AuditHistory } from './components/AuditHistory'
import { AuditDetail } from './components/AuditDetail'

interface Session { token: string; account: Account }
interface Notice { code: string; message: string; action: string; needsNewPreview: boolean }
type View = 'review' | 'evidence' | 'history'
type CurrentCheck = () => boolean

const STALE_CODES = new Set(['DATASET_CHANGED', 'POLICY_CHANGED', 'PREVIEW_CHANGED', 'REQUEST_NOT_READY', 'REQUEST_NOT_FOUND', 'REVIEW_CHANGED', 'DETECTOR_CHANGED', 'RAW_ACCESS_CHANGED'])
const FINAL_CODES = new Set(['ACCESS_REVOKED', 'PURPOSE_NOT_ALLOWED', 'DESTINATION_NOT_ALLOWED', 'SHARING_PROHIBITED', 'RECEIVER_FAILED', 'ALREADY_DISPATCHED', 'DETECTOR_UNAVAILABLE', 'UNSUPPORTED_POLICY'])

export default function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [datasets, setDatasets] = useState<DatasetSummary[]>([])
  const [form, setForm] = useState({ datasetId: '', purpose: 'feedback_summary', destination: 'demo_receiver' })
  const [preview, setPreview] = useState<PreviewResponse | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const [sendResult, setSendResult] = useState<SendResponse | null>(null)
  const [receipt, setReceipt] = useState<Receipt | null>(null)
  const [notice, setNotice] = useState<Notice | null>(null)
  const [invalidated, setInvalidated] = useState(false)
  const [deliveryUncertain, setDeliveryUncertain] = useState(false)
  const [busy, setBusy] = useState(false)
  const [view, setView] = useState<View>('review')
  const [history, setHistory] = useState<HistoryResponse | null>(null)
  const [audit, setAudit] = useState<AuditResponse | null>(null)
  const [securityReport, setSecurityReport] = useState<SecurityReportResponse | null>(null)
  const generation = useRef(0)
  const inFlight = useRef(false)

  const resetRequest = () => {
    setPreview(null); setConfirmed(false); setSendResult(null); setReceipt(null); setNotice(null); setInvalidated(false); setDeliveryUncertain(false)
  }

  const clearPrivateState = () => {
    resetRequest(); setDatasets([]); setHistory(null); setAudit(null); setSecurityReport(null); setView('review')
  }

  const signOut = () => {
    generation.current += 1
    inFlight.current = false
    setBusy(false); setSession(null); clearPrivateState()
  }

  const showError = (error: unknown) => {
    if (error instanceof ApiError) {
      const stale = STALE_CODES.has(error.code)
      const locked = stale || FINAL_CODES.has(error.code) || error.status === 403
      if (error.code === 'RECEIVER_FAILED' || error.code === 'ALREADY_DISPATCHED') setDeliveryUncertain(true)
      if (locked) {
        setInvalidated(true)
        setPreview(value => value ? { ...value, raw_view_allowed: false, original_messages: null } : value)
      }
      setConfirmed(false)
      if (error.code === 'INVALID_SESSION' || error.code === 'AUTH_REQUIRED') signOut()
      setNotice({ code: error.code, message: error.message, action: error.action, needsNewPreview: stale })
    } else {
      setNotice({ code: 'UNKNOWN', message: 'Something unexpected went wrong.', action: 'Check the backend and prepare a fresh preview if necessary.', needsNewPreview: false })
    }
  }

  const run = async (fn: (isCurrent: CurrentCheck) => Promise<void>) => {
    if (inFlight.current) return
    const startedIn = generation.current
    const isCurrent = () => generation.current === startedIn
    inFlight.current = true
    setBusy(true)
    try { await fn(isCurrent) } catch (error) { if (isCurrent()) showError(error) } finally {
      if (isCurrent()) { inFlight.current = false; setBusy(false) }
    }
  }

  const signIn = (accountId: string) => {
    if (inFlight.current) return
    generation.current += 1
    return run(async isCurrent => {
      setNotice(null)
      const next = await api.startSession(accountId)
      const list = await api.listDatasets(next.token)
      if (!isCurrent()) return
      clearPrivateState()
      setSession({ token: next.token, account: next.account })
      setDatasets(list)
      setForm({ datasetId: list[0]?.dataset_id ?? '', purpose: 'feedback_summary', destination: 'demo_receiver' })
    })
  }

  const loadReceipt = async (token: string, requestId: string, isCurrent: CurrentCheck) => {
    const next = await api.receipt(token, requestId)
    if (isCurrent()) {
      setReceipt(next)
      if (next.status === 'sent' || next.status === 'blocked') setDeliveryUncertain(false)
    }
  }

  const makePreview = () => run(async isCurrent => {
    if (!session) return
    resetRequest()
    const list = await api.listDatasets(session.token)
    if (!isCurrent()) return
    setDatasets(list)
    const datasetId = list.some(dataset => dataset.dataset_id === form.datasetId) ? form.datasetId : list[0]?.dataset_id
    if (!datasetId) throw new ApiError(403, { code: 'DATASET_ACCESS_DENIED', message: 'This account has no available datasets.', action: 'Ask the owner for access or switch demo accounts.', request_id: null })
    setForm(value => ({ ...value, datasetId }))
    const next = await api.preview(session.token, datasetId, form.purpose, form.destination)
    if (!isCurrent()) return
    setPreview(next)
    if (next.status === 'blocked') await loadReceipt(session.token, next.request_id, isCurrent)
  })

  const draftLocked = !!receipt || !!sendResult || invalidated || preview?.status !== 'ready'

  const updateReview = (hidden: number[], spans: ManualSpan[]) => run(async isCurrent => {
    if (!session || !preview || draftLocked || preview.review_revision === null || !preview.preview_hash) return
    setConfirmed(false)
    try {
      const next = await api.review(session.token, preview.request_id, preview.review_revision, preview.preview_hash, hidden, spans)
      if (!isCurrent()) return
      setPreview(next); setNotice(null)
    } catch (error) {
      if (!isCurrent()) return
      if (error instanceof ApiError && FINAL_CODES.has(error.code)) await loadReceipt(session.token, preview.request_id, isCurrent).catch(() => undefined)
      throw error
    }
  })

  const toggleHidden = (index: number) => {
    if (!preview) return
    const hidden = new Set(preview.hidden_message_indices)
    if (hidden.has(index)) hidden.delete(index); else hidden.add(index)
    return updateReview([...hidden].sort((a, b) => a - b), preview.manual_spans ?? [])
  }

  const addSpan = (span: ManualSpan) => {
    if (!preview || !preview.raw_view_allowed) return
    const spans = preview.manual_spans ?? []
    if (spans.some(current => current.message_index === span.message_index && current.start === span.start && current.end === span.end)) return
    return updateReview(preview.hidden_message_indices, [...spans, span])
  }

  const removeSpan = (span: ManualSpan) => {
    if (!preview || !preview.raw_view_allowed) return
    return updateReview(preview.hidden_message_indices, (preview.manual_spans ?? []).filter(current => current.message_index !== span.message_index || current.start !== span.start || current.end !== span.end))
  }

  const sendNow = () => run(async isCurrent => {
    if (!session || !preview || !confirmed || draftLocked || !preview.preview_hash || preview.review_revision === null) return
    setConfirmed(false)
    let acknowledged = false
    try {
      const result = await api.send(session.token, preview.request_id, preview.review_revision, preview.preview_hash)
      if (!isCurrent()) return
      acknowledged = result.status === 'sent'
      setSendResult(result)
      await loadReceipt(session.token, preview.request_id, isCurrent)
    } catch (error) {
      if (!isCurrent()) return
      const uncertainTransport = !acknowledged && error instanceof ApiError && (error.status === 0 || error.status >= 500 && !['DETECTOR_UNAVAILABLE', 'UNSUPPORTED_POLICY'].includes(error.code))
      if (uncertainTransport) { setDeliveryUncertain(true); setInvalidated(true) }
      if (error instanceof ApiError && (FINAL_CODES.has(error.code) || uncertainTransport)) {
        await loadReceipt(session.token, preview.request_id, isCurrent).catch(() => undefined)
        if (error.code === 'ACCESS_REVOKED') {
          const list = await api.listDatasets(session.token).catch(() => null)
          if (isCurrent() && list) setDatasets(list)
        }
      }
      throw error
    }
  })

  const refreshHistory = () => run(async isCurrent => {
    if (!session) return
    const next = await api.history(session.token, { user_id: session.account.account_id })
    if (isCurrent()) { setHistory(next); setNotice(null) }
  })

  const refreshSecurity = () => run(async isCurrent => {
    if (!session) return
    const next = await api.securityReport(session.token)
    if (isCurrent()) { setSecurityReport(next); setNotice(null) }
  })

  const openAudit = (requestId: string) => run(async isCurrent => {
    if (!session) return
    const next = await api.audit(session.token, requestId)
    if (isCurrent()) { setAudit(next); setNotice(null) }
  })

  const changeView = (next: View) => {
    if (busy) return
    setView(next)
    if (next === 'history') void refreshHistory()
    if (next === 'evidence') void refreshSecurity()
  }

  if (!session) return <AccountGate busy={busy} onSelect={signIn} error={notice ? `${notice.message} ${notice.action}` : null} />

  const showDraft = preview && preview.status !== 'blocked' && preview.outbound_payload
  const reviewOutcome = receipt?.status === 'sent' || sendResult?.status === 'sent' ? 'sent' : receipt?.status === 'send_failed' || deliveryUncertain ? 'uncertain' : invalidated || receipt ? 'not_sent' : 'draft'

  return <div className="app">
    <a className="skip-link" href="#main-content">Skip to workspace</a>
    <header className="topbar"><span className="wordmark wordmark-small">DataGate</span><span className="who">Signed in as <strong>{session.account.display_name}</strong><span className="demo-tag">demo session</span></span><button className="btn btn-quiet" onClick={signOut} disabled={busy}>Switch account</button></header>
    <nav className="workspace-nav" aria-label="DataGate workspace"><button className={view === 'review' ? 'is-active' : ''} aria-current={view === 'review' ? 'page' : undefined} disabled={busy} onClick={() => changeView('review')}>Review & release</button><button className={view === 'evidence' ? 'is-active' : ''} aria-current={view === 'evidence' ? 'page' : undefined} disabled={busy} onClick={() => changeView('evidence')}>Security evidence</button><button className={view === 'history' ? 'is-active' : ''} aria-current={view === 'history' ? 'page' : undefined} disabled={busy} onClick={() => changeView('history')}>My audit history</button></nav>
    {notice && <div className={`notice ${notice.needsNewPreview ? 'notice-stale' : ''}`} role="alert"><p><strong>{notice.message}</strong> {notice.action}</p><div className="notice-actions">{notice.needsNewPreview && <button className="btn btn-secondary" onClick={makePreview} disabled={busy || view !== 'review'}>Prepare a new preview</button>}<button className="btn btn-quiet" onClick={() => setNotice(null)}>Dismiss</button></div></div>}
    {busy && <p className="working-notice" role="status">Working with the backend…</p>}
    <main id="main-content">
      {view === 'review' && <>
        <div className="workspace"><RequestForm datasets={datasets} {...form} busy={busy} onChange={(field, value) => { if (busy) return; resetRequest(); setForm(current => ({ ...current, [field]: value })) }} onPreview={makePreview} />
          {showDraft ? <><ManifestReview preview={preview} editable={!draftLocked} outcome={reviewOutcome} busy={busy} onToggle={toggleHidden} onAddSpan={addSpan} onRemoveSpan={removeSpan} /><div className="side">{receipt ? <OutcomePanel receipt={receipt} sendResult={sendResult} onStartOver={resetRequest} /> : <><ApprovalPanel preview={preview} confirmed={confirmed} busy={busy} disabledReason={draftLocked ? 'This review cannot be sent again. Prepare a fresh preview to continue.' : null} onConfirm={setConfirmed} onSend={sendNow} />{sendResult && <button className="btn btn-secondary retry-receipt" disabled={busy} onClick={() => void run(isCurrent => loadReceipt(session.token, preview.request_id, isCurrent))}>Load metadata receipt</button>}</>}</div></> : receipt ? <div className="side side-wide"><OutcomePanel receipt={receipt} sendResult={null} onStartOver={resetRequest} /></div> : <section className="placeholder"><p>Choose a dataset, a purpose and a destination, then prepare a preview.</p><p>You'll see the exact content that would leave before anything is sent.</p></section>}
        </div>
        {preview && <PolicyExplanation checks={preview.policy_explanations ?? []} />}
      </>}
      {view === 'evidence' && <div className="full-workspace"><GovernanceTests result={securityReport} busy={busy} onRefresh={refreshSecurity} /></div>}
      {view === 'history' && <div className="full-workspace"><AuditHistory key={session.account.account_id} history={history} accountId={session.account.account_id} busy={busy} onRefresh={refreshHistory} onOpenReceipt={openAudit} />{audit && <AuditDetail audit={audit} onClose={() => setAudit(null)} />}</div>}
    </main>
    <footer className="foot">Local demo. The receiver is a capturing test adapter; no external AI model is called. Pretrained name detection supports review, not a guarantee of anonymity.</footer>
  </div>
}

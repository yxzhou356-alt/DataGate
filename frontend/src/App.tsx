import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from './api'
import type { Account, DatasetSummary, PreviewResponse, Receipt, SendResponse } from './types'
import { AccountGate } from './components/AccountGate'
import { RequestForm } from './components/RequestForm'
import { ManifestReview } from './components/ManifestReview'
import { ApprovalPanel } from './components/ApprovalPanel'
import { OutcomePanel } from './components/OutcomePanel'

interface Session { token: string; account: Account }
interface Notice { code: string; message: string; action: string; needsNewPreview: boolean }

// Errors after which the current draft can never be sent; a fresh preview is needed.
const STALE_CODES = new Set(['DATASET_CHANGED', 'POLICY_CHANGED', 'PREVIEW_CHANGED', 'REQUEST_NOT_READY', 'REVIEW_CHANGED'])
// Errors whose final outcome is recorded in a receipt we can show.
const FINAL_CODES = new Set(['ACCESS_REVOKED', 'PURPOSE_NOT_ALLOWED', 'DESTINATION_NOT_ALLOWED', 'SHARING_PROHIBITED', 'RECEIVER_FAILED', 'ALREADY_DISPATCHED'])

export default function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [datasets, setDatasets] = useState<DatasetSummary[]>([])
  const [form, setForm] = useState({ datasetId: '', purpose: 'feedback_summary', destination: 'demo_receiver' })
  const [preview, setPreview] = useState<PreviewResponse | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const [sendResult, setSendResult] = useState<SendResponse | null>(null)
  const [receipt, setReceipt] = useState<Receipt | null>(null)
  const [notice, setNotice] = useState<Notice | null>(null)
  const [busy, setBusy] = useState(false)

  const showError = useCallback((err: unknown) => {
    if (err instanceof ApiError) {
      setNotice({ code: err.code, message: err.message, action: err.action, needsNewPreview: STALE_CODES.has(err.code) })
      if (err.code === 'INVALID_SESSION' || err.code === 'AUTH_REQUIRED') setSession(null)
    } else {
      setNotice({ code: 'UNKNOWN', message: 'Something unexpected went wrong.', action: 'Try again.', needsNewPreview: false })
    }
  }, [])

  const refreshDatasets = useCallback(async (token: string) => {
    const list = await api.listDatasets(token)
    setDatasets(list)
    setForm((f) => ({ ...f, datasetId: list.some((d) => d.dataset_id === f.datasetId) ? f.datasetId : list[0]?.dataset_id ?? '' }))
  }, [])

  useEffect(() => {
    if (session) refreshDatasets(session.token).catch(showError)
  }, [session, refreshDatasets, showError])

  const resetRequest = () => {
    setPreview(null); setConfirmed(false); setSendResult(null); setReceipt(null); setNotice(null)
  }

  const run = async (fn: () => Promise<void>) => {
    setBusy(true)
    try { await fn() } catch (e) { showError(e) } finally { setBusy(false) }
  }

  const signIn = (accountId: string) => run(async () => {
    const s = await api.startSession(accountId)
    resetRequest()
    setSession({ token: s.token, account: s.account })
  })

  const signOut = () => { setSession(null); setDatasets([]); resetRequest() }

  const loadReceipt = async (token: string, requestId: string) => {
    setReceipt(await api.receipt(token, requestId))
  }

  const makePreview = () => run(async () => {
    if (!session) return
    resetRequest()
    await refreshDatasets(session.token)
    const p = await api.preview(session.token, form.datasetId, form.purpose, form.destination)
    setPreview(p)
    if (p.status === 'blocked') await loadReceipt(session.token, p.request_id)
  })

  const toggleHidden = (index: number) => run(async () => {
    if (!session || !preview || preview.review_revision === null) return
    const current = new Set(preview.hidden_message_indices)
    if (current.has(index)) current.delete(index); else current.add(index)
    const next = await api.review(session.token, preview.request_id, preview.review_revision, [...current].sort((a, b) => a - b))
    setPreview(next)
    setConfirmed(false) // a changed payload needs a fresh approval
  })

  const sendNow = () => run(async () => {
    if (!session || !preview || !preview.preview_hash || preview.review_revision === null) return
    try {
      const result = await api.send(session.token, preview.request_id, preview.review_revision, preview.preview_hash)
      setSendResult(result)
      await loadReceipt(session.token, preview.request_id)
    } catch (err) {
      if (err instanceof ApiError && FINAL_CODES.has(err.code)) {
        await loadReceipt(session.token, preview.request_id).catch(() => undefined)
        if (err.code === 'ACCESS_REVOKED') await refreshDatasets(session.token).catch(() => undefined)
      }
      throw err
    }
  })

  if (!session) return <AccountGate busy={busy} onSelect={signIn} />

  const draftLocked = !!receipt || !!notice?.needsNewPreview
  const showDraft = preview && preview.status !== 'blocked' && preview.outbound_payload

  return (
    <div className="app">
      <header className="topbar">
        <span className="wordmark wordmark-small">DataGate</span>
        <span className="who">
          Signed in as <strong>{session.account.display_name}</strong>
          <span className="demo-tag">demo session</span>
        </span>
        <button className="btn btn-quiet" onClick={signOut}>Switch account</button>
      </header>

      {notice && (
        <div className={`notice ${notice.needsNewPreview ? 'notice-stale' : ''}`} role="alert">
          <p><strong>{notice.message}</strong> {notice.action}</p>
          <div className="notice-actions">
            {notice.needsNewPreview && <button className="btn btn-secondary" onClick={makePreview} disabled={busy}>Prepare a new preview</button>}
            <button className="btn btn-quiet" onClick={() => setNotice(null)}>Dismiss</button>
          </div>
        </div>
      )}

      <div className="workspace">
        <RequestForm
          datasets={datasets}
          {...form}
          busy={busy}
          onChange={(field, value) => setForm((f) => ({ ...f, [field]: value }))}
          onPreview={makePreview}
        />

        {showDraft ? (
          <>
            <ManifestReview
              preview={preview}
              editable={!draftLocked}
              outcome={receipt ? (receipt.status === 'sent' ? 'sent' : 'not_sent') : notice?.needsNewPreview ? 'not_sent' : 'draft'}
              busy={busy}
              onToggle={toggleHidden}
            />
            <div className="side">
              {receipt ? (
                <OutcomePanel receipt={receipt} sendResult={sendResult} onStartOver={resetRequest} />
              ) : (
                <ApprovalPanel
                  preview={preview}
                  confirmed={confirmed}
                  busy={busy}
                  disabledReason={notice?.needsNewPreview ? 'This preview is out of date. Prepare a new one to continue.' : null}
                  onConfirm={setConfirmed}
                  onSend={sendNow}
                />
              )}
            </div>
          </>
        ) : receipt ? (
          <div className="side side-wide"><OutcomePanel receipt={receipt} sendResult={null} onStartOver={resetRequest} /></div>
        ) : (
          <section className="placeholder">
            <p>Choose a dataset, a purpose and a destination, then prepare a preview.</p>
            <p>You'll see the exact content that would leave before anything is sent.</p>
          </section>
        )}
      </div>

      <footer className="foot">
        Local demo. The receiver is a capturing test endpoint; no external AI model is called.
      </footer>
    </div>
  )
}

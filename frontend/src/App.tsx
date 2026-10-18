import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from './api'
import type { Account, CustomRedaction, DatasetSummary, PreviewResponse, Receipt, SendResponse } from './types'
import { AccountGate } from './components/AccountGate'
import { RequestForm } from './components/RequestForm'
import { ManifestReview, type ReviewFailure } from './components/ManifestReview'
import { ApprovalPanel, type ReviewChange } from './components/ApprovalPanel'
import { HIDDEN_MARKER, countPlaceholders, placeholderTypes, toggleIndex } from './redaction'
import { OutcomePanel } from './components/OutcomePanel'
import { EvidenceDashboard } from './components/EvidenceDashboard'

interface Session { token: string; account: Account }
interface Notice { code: string; message: string; action: string; needsNewPreview: boolean }

// Errors after which the current draft can never be sent; a fresh preview is needed.
const STALE_CODES = new Set(['DATASET_CHANGED', 'POLICY_CHANGED', 'PREVIEW_CHANGED', 'REQUEST_NOT_READY', 'REVIEW_CHANGED'])
// Errors whose final outcome is recorded in a receipt we can show.
const FINAL_CODES = new Set(['ACCESS_REVOKED', 'PURPOSE_NOT_ALLOWED', 'DESTINATION_NOT_ALLOWED', 'SHARING_PROHIBITED', 'RECEIVER_FAILED', 'ALREADY_DISPATCHED'])
// Final codes meaning access/owner rules now forbid this request: stop showing its preview.
const DENIED_CODES = new Set(['ACCESS_REVOKED', 'PURPOSE_NOT_ALLOWED', 'DESTINATION_NOT_ALLOWED', 'SHARING_PROHIBITED'])
// Review errors where the backend confirms the existing review was left unchanged.
// A 422 is a definite rejection: the server did not apply the change.
const REVIEW_UNCHANGED_CODES = new Set(['NO_CONTENT_TO_SEND', 'INVALID_REVIEW', 'INVALID_REQUEST'])

/** Approval is bound to one exact draft state; any new revision or hash needs a fresh tick. */
const approvalKey = (p: PreviewResponse) => `${p.request_id}:${p.review_revision}:${p.preview_hash}`

/**
 * Per request: each message's mandatory-redacted base text (the server text before any
 * requester choice) and its owner-placeholder counts. Custom offsets refer to this base.
 */
interface KnownRedactions {
  requestId: string
  counts: Record<number, Record<string, number>>
  base: Record<number, string>
}

export default function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [datasets, setDatasets] = useState<DatasetSummary[]>([])
  const [form, setForm] = useState({ datasetId: '', purpose: 'feedback_summary', destination: 'demo_receiver' })
  const [preview, setPreview] = useState<PreviewResponse | null>(null)
  const [approvedKey, setApprovedKey] = useState<string | null>(null)
  const [pendingIndex, setPendingIndex] = useState<number | null>(null)
  const [reviewFailure, setReviewFailure] = useState<ReviewFailure | null>(null)
  const [lastChange, setLastChange] = useState<ReviewChange | null>(null)
  const [known, setKnown] = useState<KnownRedactions | null>(null)
  const [sendResult, setSendResult] = useState<SendResponse | null>(null)
  const [receipt, setReceipt] = useState<Receipt | null>(null)
  const [notice, setNotice] = useState<Notice | null>(null)
  const [busy, setBusy] = useState(false)
  // '#evidence' opens the read-only security evidence dashboard; the request state is kept meanwhile.
  const [view, setView] = useState<'app' | 'evidence'>(() => (window.location.hash === '#evidence' ? 'evidence' : 'app'))

  useEffect(() => {
    const onHash = () => setView(window.location.hash === '#evidence' ? 'evidence' : 'app')
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

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
    setPreview(null); setApprovedKey(null); setSendResult(null); setReceipt(null); setNotice(null)
    setPendingIndex(null); setReviewFailure(null); setLastChange(null); setKnown(null)
  }

  /** Stores a server preview and remembers per-message placeholder counts from its (already redacted) text. */
  const acceptPreview = (p: PreviewResponse) => {
    setPreview(p)
    const types = placeholderTypes(Object.keys(p.redaction_counts))
    const customised = new Set((p.custom_redactions ?? []).map((c) => c.message_index))
    setKnown((prev) => {
      const same = prev?.requestId === p.request_id
      const counts = same ? { ...prev.counts } : {}
      const base = same ? { ...prev.base } : {}
      p.outbound_payload?.messages.forEach((m, i) => {
        // Only text with no requester choice applied is the base for that message.
        if (m !== HIDDEN_MARKER && !customised.has(i)) {
          base[i] = m
          counts[i] = countPlaceholders(m, types)
        }
      })
      return { requestId: p.request_id, counts, base }
    })
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
    acceptPreview(p)
    if (p.status === 'blocked') await loadReceipt(session.token, p.request_id)
  })

  /** Sends a complete review state (hidden indices + custom spans). The server returns the authoritative preview. */
  /** `custom` undefined keeps the stored custom redactions (the field is omitted). */
  const submitReview = async (index: number, hide: number[], custom?: CustomRedaction[]) => {
    if (!session || !preview || preview.review_revision === null || busy) return
    const before = preview
    // Withdraw approval before the request leaves, so a failed or slow PATCH never
    // leaves the checkbox bound to the old preview.
    setApprovedKey(null)
    setReviewFailure(null)
    setPendingIndex(index)
    setBusy(true)
    try {
      const next = await api.review(session.token, before.request_id, before.review_revision!, hide, custom)
      acceptPreview(next)
      setLastChange({ fromRevision: before.review_revision!, toRevision: next.review_revision!, previousHash: before.preview_hash })
    } catch (err) {
      if (err instanceof ApiError && DENIED_CODES.has(err.code)) {
        // Access or owner rules changed: the request is now blocked. Drop the preview content.
        setPreview(null)
        await loadReceipt(session.token, before.request_id).catch(() => undefined)
        await refreshDatasets(session.token).catch(() => undefined)
        showError(err)
      } else if (err instanceof ApiError && (STALE_CODES.has(err.code) || err.code === 'INVALID_SESSION' || err.code === 'AUTH_REQUIRED')) {
        showError(err)
      } else {
        const apiErr = err instanceof ApiError ? err : null
        setReviewFailure({
          code: apiErr?.code ?? 'UNKNOWN',
          message: apiErr?.message ?? 'The review change failed.',
          action: apiErr?.action ?? 'Try again.',
          index, hide, custom,
          previewUnchanged: !!apiErr && REVIEW_UNCHANGED_CODES.has(apiErr.code),
        })
      }
    } finally {
      setPendingIndex(null)
      setBusy(false)
    }
  }

  const currentCustom = () => preview?.custom_redactions ?? []

  const toggleHidden = (index: number) => {
    if (!preview) return
    submitReview(index, toggleIndex(preview.hidden_message_indices, index))
  }

  const addCustom = (index: number, span: { start: number; end: number }) => {
    if (!preview) return
    submitReview(index, preview.hidden_message_indices, [...currentCustom(), { message_index: index, ...span }])
  }

  const removeCustom = (index: number, start: number | null) => {
    if (!preview) return
    const keep = currentCustom().filter((c) => c.message_index !== index || (start !== null && c.start !== start))
    submitReview(index, preview.hidden_message_indices, keep)
  }


  const sendNow = () => run(async () => {
    if (!session || !preview || !preview.preview_hash || preview.review_revision === null) return
    if (approvedKey !== approvalKey(preview) || pendingIndex !== null || reviewFailure) return
    try {
      const result = await api.send(session.token, preview.request_id, preview.review_revision, preview.preview_hash)
      setSendResult(result)
      await loadReceipt(session.token, preview.request_id)
    } catch (err) {
      if (err instanceof ApiError && FINAL_CODES.has(err.code)) {
        if (DENIED_CODES.has(err.code)) setPreview(null) // no longer authorized to view this preview
        await loadReceipt(session.token, preview.request_id).catch(() => undefined)
        if (err.code === 'ACCESS_REVOKED') await refreshDatasets(session.token).catch(() => undefined)
      }
      throw err
    }
  })

  if (view === 'evidence') {
    return <EvidenceDashboard onBack={() => { window.location.hash = '' }} />
  }
  if (!session) return <AccountGate busy={busy} onSelect={signIn} />

  const draftLocked = !!receipt || !!notice?.needsNewPreview
  const approvalBlocker = notice?.needsNewPreview
    ? 'This preview is out of date. Prepare a new one to continue.'
    : pendingIndex !== null
      ? 'Updating the preview. Approval is paused until the new version arrives.'
      : reviewFailure
        ? 'The last review change failed. Resolve it above before approving.'
        : null
  const showDraft = preview && preview.status !== 'blocked' && preview.outbound_payload
  const receiptDatasetName = receipt
    ? datasets.find((dataset) => dataset.dataset_id === receipt.dataset_id)?.display_name ?? null
    : null

  return (
    <div className="app">
      <header className="topbar">
        <span className="wordmark wordmark-small">DataGate</span>
        <span className="who">
          Signed in as <strong>{session.account.display_name}</strong>
          <span className="demo-tag">demo session</span>
        </span>
        <a className="btn btn-quiet" href="#evidence">Security evidence</a>
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
          onChange={(field, value) => {
            setForm((f) => ({ ...f, [field]: value }))
            resetRequest()
          }}
          onPreview={makePreview}
        />

        {showDraft ? (
          <>
            <ManifestReview
              preview={preview}
              editable={!draftLocked}
              outcome={receipt ? (receipt.status === 'sent' ? 'sent' : receipt.status === 'send_failed' ? 'unconfirmed' : 'not_sent') : notice?.needsNewPreview ? 'not_sent' : 'draft'}
              busy={busy}
              pendingIndex={pendingIndex}
              failure={reviewFailure}
              knownRedactions={known?.requestId === preview.request_id ? known.counts : {}}
              baseTexts={known?.requestId === preview.request_id ? known.base : {}}
              onToggle={toggleHidden}
              onAddCustom={addCustom}
              onRemoveCustom={removeCustom}
              onRetryFailure={() => reviewFailure && submitReview(reviewFailure.index, reviewFailure.hide, reviewFailure.custom)}
              onDismissFailure={() => setReviewFailure(null)}
            />
            <div className="side">
              {receipt ? (
                <OutcomePanel receipt={receipt} sendResult={sendResult} datasetName={receiptDatasetName} onStartOver={resetRequest} />
              ) : (
                <ApprovalPanel
                  preview={preview}
                  confirmed={approvedKey === approvalKey(preview)}
                  busy={busy}
                  disabledReason={approvalBlocker}
                  lastChange={lastChange}
                  onConfirm={(v) => setApprovedKey(v ? approvalKey(preview) : null)}
                  onSend={sendNow}
                />
              )}
            </div>
          </>
        ) : receipt ? (
          <div className="side side-wide"><OutcomePanel receipt={receipt} sendResult={null} datasetName={receiptDatasetName} onStartOver={resetRequest} /></div>
        ) : (
          <section className="placeholder">
            <p>Choose a feedback source, what you want to do and where the approved content should go.</p>
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

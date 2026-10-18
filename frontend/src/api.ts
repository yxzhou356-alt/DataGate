// Thin client for the DataGate v1 API. The token lives in memory only.
import type {
  ApiErrorBody, CustomRedaction, DatasetSummary, EvidenceView, ReceiptPage, TimelineFilters, PreviewResponse, Receipt, SendResponse, SessionResponse,
} from './types'

export class ApiError extends Error {
  readonly code: string
  readonly action: string
  readonly status: number
  readonly requestId: string | null

  constructor(status: number, body: ApiErrorBody) {
    super(body.message)
    this.code = body.code
    this.action = body.action
    this.status = status
    this.requestId = body.request_id
  }
}

/**
 * Readable text for an error shown inside a view. A 404 NOT_FOUND from an API route this
 * page relies on almost always means the running backend predates the page (uvicorn
 * started without --reload before the route was added), so say how to fix it.
 */
export function describeError(err: unknown, fallback: string): string {
  if (err instanceof ApiError && err.code === 'NOT_FOUND') {
    return 'The running backend does not have this feature yet; it was probably started before the code was updated. Restart the backend, then reload this page.'
  }
  return err instanceof ApiError ? `${err.message} ${err.action}` : fallback
}

async function call<T>(method: string, path: string, token: string | null, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (token) headers['Authorization'] = `Bearer ${token}`
  let resp: Response
  try {
    resp = await fetch(`/api${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
  } catch {
    throw new ApiError(0, {
      code: 'BACKEND_UNREACHABLE',
      message: 'The DataGate backend is not reachable.',
      request_id: null,
      action: 'Start the backend on 127.0.0.1:8000 and try again.',
    })
  }
  const data = await resp.json().catch(() => null)
  if (!resp.ok) {
    const err = data?.error as ApiErrorBody | undefined
    throw new ApiError(resp.status, err ?? { code: 'UNKNOWN', message: `Request failed (${resp.status}).`, request_id: null, action: 'Try again.' })
  }
  return data as T
}

export const api = {
  startSession: (accountId: string) =>
    call<SessionResponse>('POST', '/demo/session', null, { account_id: accountId }),

  listDatasets: (token: string) =>
    call<{ datasets: DatasetSummary[] }>('GET', '/datasets', token).then((r) => r.datasets),

  preview: (token: string, datasetId: string, purpose: string, destination: string) =>
    call<PreviewResponse>('POST', '/requests/preview', token, { dataset_id: datasetId, purpose, destination }),

  /**
   * Replaces the review choices. Offsets only; there is no way to submit message text.
   * `custom` undefined omits the field, which keeps the stored custom redactions
   * (and stays compatible with a backend that predates them).
   */
  review: (token: string, requestId: string, expectedRevision: number, hide: number[], custom?: CustomRedaction[]) =>
    call<PreviewResponse>('PATCH', `/requests/${encodeURIComponent(requestId)}/review`, token, {
      expected_review_revision: expectedRevision,
      hide_message_indices: hide,
      ...(custom === undefined ? {} : { custom_redactions: custom }),
    }),

  send: (token: string, requestId: string, expectedRevision: number, previewHash: string) =>
    call<SendResponse>('POST', `/requests/${encodeURIComponent(requestId)}/send`, token, {
      approve: true,
      expected_review_revision: expectedRevision,
      preview_hash: previewHash,
    }),

  /** Read-only security evidence report; no token, never runs tests. */
  securityReport: () => call<EvidenceView>('GET', '/evidence/security-report', null),

  /** Creator-only receipt timeline. The account comes from the token; only safe filters are sent. */
  listReceipts: (token: string, filters: TimelineFilters = {}) => {
    const params = new URLSearchParams()
    for (const [key, value] of Object.entries(filters)) if (value !== undefined && value !== '') params.set(key, String(value))
    const query = params.toString()
    return call<ReceiptPage>('GET', `/receipts${query ? `?${query}` : ''}`, token)
  },

  receipt: (token: string, requestId: string) =>
    call<Receipt>('GET', `/requests/${encodeURIComponent(requestId)}/receipt`, token),
}

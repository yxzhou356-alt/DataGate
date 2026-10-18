// Thin client for the DataGate v1 API. The token lives in memory only.
import type {
  ApiErrorBody, CustomRedaction, DatasetSummary, PreviewResponse, Receipt, SendResponse, SessionResponse,
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

  receipt: (token: string, requestId: string) =>
    call<Receipt>('GET', `/requests/${encodeURIComponent(requestId)}/receipt`, token),
}

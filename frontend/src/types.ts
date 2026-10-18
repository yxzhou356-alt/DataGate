// Wire types mirroring API_CONTRACT.md v1. Change only with a coordinated contract update.

export type Decision = 'allow' | 'redact' | 'block'
export type Status = 'ready' | 'blocked' | 'stale' | 'sending' | 'sent' | 'send_failed'

export interface Account {
  account_id: string
  display_name: string
}

export interface SessionResponse {
  token: string
  token_type: 'bearer'
  account: Account
  authentication_mode: 'demo'
}

export interface Passport {
  declared_owner: string
  allowed_purposes: string[]
  allowed_destinations: string[]
  outbound_fields: string[]
  required_redactions: string[]
  sharing_mode: 'redacted_only' | 'none'
  policy_version: number
  /** How PERSON is replaced when required: [PERSON] or request-scoped [PERSON_1], [PERSON_2], ... */
  person_style?: 'generic' | 'numbered'
}

export interface DatasetSummary {
  dataset_id: string
  display_name: string
  dataset_revision: number
  passport: Passport
}

export interface OutboundPayload {
  schema_version: string
  purpose: string
  instruction: string
  messages: string[]
}

/** A span of the server's mandatory-redacted message text, in Unicode code points (end-exclusive). */
export interface CustomRedaction {
  message_index: number
  start: number
  end: number
}

export interface PreviewResponse {
  request_id: string
  dataset_id: string
  dataset_revision: number
  policy_version: number
  review_revision: number | null
  decision: Decision
  status: Status
  reason_codes: string[]
  dropped_fields: string[]
  redaction_counts: Record<string, number>
  hidden_message_indices: number[]
  custom_redactions: CustomRedaction[]
  outbound_payload: OutboundPayload | null
  preview_hash: string | null
  receiver_mode: string
  receiver_attempts: number
  receipt_available: boolean
}

export interface ReceiverResult {
  mode: string
  acknowledged: boolean
  message_count: number
  note: string
}

export interface SendResponse {
  request_id: string
  decision: Decision
  status: Status
  receiver_mode: string
  receiver_attempts: number
  receiver_result: ReceiverResult
  receipt_available: boolean
}

export interface Receipt {
  schema_version: string
  request_id: string
  account_id: string
  dataset_id: string
  dataset_revision: number | null
  policy_version: number | null
  preview_policy_version: number | null
  review_revision: number | null
  purpose: string
  destination: string
  decision: Decision
  status: Status
  reason_codes: string[]
  redaction_counts: Record<string, number>
  additional_hidden_messages: number
  additional_custom_redactions: number
  prepared_payload_hash: string | null
  confirmed_sent_payload_hash: string | null
  receiver_mode: string
  receiver_attempts: number
  occurred_at: string | null
}

/** One creator-only timeline entry: the single-receipt shape plus the sort timestamp. */
export interface ReceiptListItem extends Receipt {
  /** occurred_at, or created_at for older rows recorded without one. */
  recorded_at: string
}

export interface ReceiptPage {
  receipts: ReceiptListItem[]
  next_cursor: string | null
  limit: number
}

export type TimelineStatus = 'blocked' | 'stale' | 'sent' | 'send_failed'

export interface TimelineFilters {
  status?: TimelineStatus
  dataset_id?: string
  cursor?: string
  limit?: number
}

export interface ApiErrorBody {
  code: string
  message: string
  request_id: string | null
  action: string
}

// Security evidence report (read-only, metadata only). See API_CONTRACT.md §13.
export type ScenarioResult = 'passed' | 'failed' | 'not_run'

export interface EvidenceScenario {
  id: string
  title: string
  claim: string
  result: ScenarioResult
  duration_seconds: number
  tests_total: number
  tests_passed: number
  tests_failed: number
  tests_not_run: number
  evidence: string[]
  failure_summary: string | null
}

export interface SecurityReport {
  schema_version: string
  report_type: string
  generated_at: string
  git: { commit: string | null; dirty: boolean | null }
  suite: {
    id: string
    command: string
    run_status: 'complete' | 'interrupted' | 'error'
    pytest_exit_code: number | null
    tests_collected: number
    tests_passed: number
    tests_failed: number
    tests_not_run: number
    duration_seconds: number
  }
  isolation: { storage: string; receiver: string; runtime_db_unchanged: boolean | null }
  totals: Record<ScenarioResult, number>
  scenarios: EvidenceScenario[]
  disclaimer: string
}

export interface EvidenceView {
  availability: 'available' | 'missing' | 'invalid'
  problem: string | null
  current_commit: string | null
  current_dirty: boolean | null
  freshness: 'current' | 'stale' | 'unknown'
  report: SecurityReport | null
  disclaimer: string
}

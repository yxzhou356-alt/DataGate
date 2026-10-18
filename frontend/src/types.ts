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
  outbound_payload: OutboundPayload | null
  preview_hash: string | null
  receiver_mode: string
  receiver_attempts: number
  receipt_available: boolean
  raw_view_allowed: boolean
  original_messages: string[] | null
  findings: Finding[]
  manual_spans: ManualSpan[]
  detector_status: DetectorStatus
  policy_explanations: PolicyExplanationRow[]
}

export interface Finding { id: string; message_index: number; start: number; end: number; category: string; replacement: string; mandatory: boolean; detector: string }
export interface ManualSpan { message_index: number; start: number; end: number }
export interface DetectorStatus { available: boolean; model: string; version: string | null; fingerprint: string }
export interface PolicyExplanationRow { field: string; result: 'included' | 'excluded' | 'redacted'; explanation: string; rule_id: string }

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
  prepared_payload_hash: string | null
  confirmed_sent_payload_hash: string | null
  receiver_mode: string
  receiver_attempts: number
  occurred_at: string | null
}

export interface ApiErrorBody {
  code: string
  message: string
  request_id: string | null
  action: string
}

export interface HistoryRow { request_id: string; dataset_id: string; purpose: string; destination: string; status: Status; decision: Decision; created_at: string; occurred_at: string | null; receiver_attempts: number; review_revision: number | null }
export interface HistoryResponse { requests: HistoryRow[]; total: number }
export interface AuditEvent { event_id: string; event_type: string; actor_kind: string; actor_id: string; occurred_at: string; metadata: Record<string, unknown> }
export interface AuditResponse { schema_version: '1.1'; request: HistoryRow; events: AuditEvent[]; receipt: Receipt | null }
export interface SecurityReport { schema_version: string; generated_at: string; source_revision: string | null; working_tree_dirty: boolean; source_fingerprint: string; total: number; passed: number; failed: number; skipped: number; duration_seconds: number; receiver_mode: string; controls: { id: string; title: string; status: 'passed' | 'failed' | 'not_run'; tests: number }[]; tests: { id: string; status: string; duration_seconds: number }[] }
export interface SecurityReportResponse { available: boolean; stale: boolean; source_fingerprint: string; report: SecurityReport | null }

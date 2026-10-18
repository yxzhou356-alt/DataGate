# DataGate API contract v1

Status: implemented baseline plus the human-assigned v1.1 six-feature extension. This is the authoritative wire contract. Section 12 defines additive v1.1 fields/routes; earlier examples are abbreviated baseline shapes. Coordinate changes across backend, frontend and tests.

## 1. Conventions

- Backend: http://127.0.0.1:8000 ; route prefix /api.
- Frontend: http://127.0.0.1:5173.
- Authenticated routes require Authorization: Bearer <demo-session-token>.
- JSON names are snake_case. Reject unknown fields in request bodies.
- Machine timestamps are ISO-8601 UTC. Display local time where useful.
- request_id is a server-generated opaque string.
- review_revision, dataset_revision and policy_version are positive integers.
- A preview_hash is 64 lowercase SHA-256 hex characters, computed by the server.
- All protected draft/review/send operations require the creator AND current dataset access.
- Metadata receipts are creator-only. The creator may still read their metadata receipt after dataset access is revoked.
- No route accepts a replacement authoritative outgoing payload, user role, permission grant, or destination URL.
- Error details must not echo raw tokens, source rows, or submitted personal values.

## 2. Enums

decision: allow | redact | block
status: ready | blocked | stale | sending | sent | send_failed
receiver_mode: local_demo in baseline.

ready means prepared and waiting for approval through Send.
blocked is a prohibited request.
stale requires a new preview.
sending has already claimed dispatch; do not dispatch again.
sent confirms adapter acknowledgement.
send_failed means completion was not confirmed; delivery may be uncertain for a future network adapter. No automatic retries.

## 3. Canonical receiver payload and hash

Every ready preview includes outbound_payload in exactly this shape:

```json
{
  "schema_version": "1.0",
  "purpose": "feedback_summary",
  "instruction": "Summarize the recurring product issues in the provided messages.",
  "messages": ["The reset link expired. Please contact [EMAIL]."]
}
```

Only the prepared message strings appear in messages. Do not include row dictionaries, IDs, names, source filenames, account values or original CSV bytes.

Canonical bytes are UTF-8 of JSON serialized with sorted keys, compact separators (comma and colon), and ensure_ascii=false. preview_hash is SHA256(canonical_bytes). The fixed instruction and schema version are included in this hash.

The adapter receives these same bytes. Changing the fixed template requires fresh previews. A payload hash is not a hash of secret authorization headers or a guarantee about a remote provider's storage.

## 4. Demo session

POST /api/demo/session

Request:
```json
{"account_id":"analyst_a"}
```

Only analyst_a and analyst_b are supported. Response 200:
```json
{
  "token":"<server-generated-session-token>",
  "token_type":"bearer",
  "account":{"account_id":"analyst_a","display_name":"MapleCo analyst"},
  "authentication_mode":"demo"
}
```

This is an intentional local account simulation, not production authentication. Keep the token in frontend memory. Tokens/drafts may expire on backend restart. Other API routes resolve account identity from the token and never from user_id/role fields.

## 5. Accessible datasets

GET /api/datasets

Response 200:
```json
{
  "datasets":[
    {
      "dataset_id":"feedback_a",
      "display_name":"MapleCo feedback",
      "dataset_revision":1,
      "passport":{
        "declared_owner":"MapleCo support",
        "allowed_purposes":["feedback_summary"],
        "allowed_destinations":["demo_receiver"],
        "outbound_fields":["message"],
        "required_redactions":["EMAIL","PHONE"],
        "sharing_mode":"redacted_only",
        "policy_version":1
      }
    }
  ]
}
```

analyst_a sees feedback_a only; analyst_b sees feedback_b only. Do not return another dataset's title, row content or policy. A later direct request to the forbidden ID must still be checked.

## 6. Create a preview

POST /api/requests/preview

Request:
```json
{
  "dataset_id":"feedback_a",
  "purpose":"feedback_summary",
  "destination":"demo_receiver"
}
```

Ready response 200:
```json
{
  "request_id":"<opaque-id>",
  "dataset_id":"feedback_a",
  "dataset_revision":1,
  "policy_version":1,
  "review_revision":1,
  "decision":"redact",
  "status":"ready",
  "reason_codes":["REDACTION_REQUIRED"],
  "dropped_fields":["ticket_id","customer_name","email","phone","plan_tier","account_value","product_area"],
  "redaction_counts":{"EMAIL":1,"PHONE":0},
  "hidden_message_indices":[],
  "outbound_payload":{
    "schema_version":"1.0",
    "purpose":"feedback_summary",
    "instruction":"Summarize the recurring product issues in the provided messages.",
    "messages":["The reset link expired. Please contact [EMAIL]."]
  },
  "preview_hash":"<computed-sha256>",
  "receiver_mode":"local_demo",
  "receiver_attempts":0,
  "receipt_available":false
}
```

The hash placeholder is illustrative; compute a real digest. All clean retained messages still pass the configured transformation pipeline. If no sensitive patterns require hiding, decision=allow; approval is still required.

A known authenticated analyst requesting an unauthorized dataset receives 403 DATASET_ACCESS_DENIED with no preview. A nonexistent ID may return 404 DATASET_NOT_FOUND.

A permitted dataset with a prohibited purpose/destination/sharing policy returns 200 with decision=block, status=blocked, reason_codes, a server request_id, zero receiver_attempts, outbound_payload=null, preview_hash=null, and receipt_available=true. Do not run a receiver to create this response. Requests may name model_training to demonstrate a denied operation; no training is implemented.

Check basic CSV validity. Invalid source gets 422 DATASET_INVALID and zero dispatch. Baseline requires ticket_id and nonempty message; extended duplicate-ID checks are a later layer.

## 7. Review choices

PATCH /api/requests/{request_id}/review

Request:
```json
{"expected_review_revision":1,"hide_message_indices":[0]}
```

Indices are zero-based positions in the registered source under its fixed revision. Only additional whole-message hiding is supported. Deduplicate/sort valid indices. Replace selected messages with [HIDDEN_BY_USER]; never restore mandatory-redacted text from client input.

Return the full ready-preview shape with incremented review_revision, new payload/hash and hidden_message_indices. A stale expected revision gets 409 REVIEW_CHANGED. Invalid/out-of-range indices get 422 INVALID_REVIEW. Refuse to prepare a request with all messages hidden: 422 NO_CONTENT_TO_SEND, leaving the existing review unchanged.

A policy-locked action cannot be relaxed: there is no field for unredact, allow_email, include_account_value or arbitrary outgoing text. Unknown fields receive 422 INVALID_REQUEST.

Require creator/current access. Recheck source/policy state when editing; changed source/policy produces a stale result requiring POST preview again. Already blocked/stale/dispatched requests cannot be reviewed.

## 8. Approve and send

POST /api/requests/{request_id}/send

Request:
```json
{
  "approve":true,
  "expected_review_revision":1,
  "preview_hash":"<hash-shown-in-preview>"
}
```

approve must be true. Do not accept raw replacement messages.

Process:
1. Authenticate and verify request creator.
2. Require status=ready and matching approval revision/hash.
3. Read current dataset access and policy. Revoked/forbidden access blocks without a call.
4. Compare fresh source bytes/hash/revision and fresh policy/fingerprint/version with the draft. Still-permitted changes require a fresh preview.
5. Rebuild from backend source plus stored allowed choices and compare canonical bytes/hash.
6. Atomically transition ready→sending using expected status/revision/hash. Exactly one competing Send may win.
7. Invoke the sole adapter once, with request_id and canonical payload bytes. No automatic retry.
8. Persist final outcome and metadata receipt.

Success 200:
```json
{
  "request_id":"<opaque-id>",
  "decision":"redact",
  "status":"sent",
  "receiver_mode":"local_demo",
  "receiver_attempts":1,
  "receiver_result":{
    "mode":"local_demo",
    "acknowledged":true,
    "message_count":1,
    "note":"Local test receiver; no external AI model was called."
  },
  "receipt_available":true
}
```

Do not return a canned response labeled as AI-generated analysis.

Repeated/concurrent calls after dispatch was claimed: 409 ALREADY_DISPATCHED, no extra invocation. Do not automatically resend a failed/uncertain dispatch; a new reviewed request is required.

Revoked permission: 403 ACCESS_REVOKED, stored status=blocked, decision=block, reason_codes=["ACCESS_REVOKED"], zero attempts. If another current owner rule now forbids the operation, use its applicable denial code and the same blocked decision/status. The final metadata receipt must reflect this denial, not the earlier preview's allow/redact decision.
Still-permitted source/policy changes: 409 DATASET_CHANGED or POLICY_CHANGED, stored status=stale, zero attempts.
Mismatched approval revision/hash: 409 REVIEW_CHANGED or PREVIEW_CHANGED, no call; the current ready draft may remain ready.
Receiver exception: 502 RECEIVER_FAILED, stored status=send_failed, attempts=1 if the adapter was invoked, metadata receipt available. Completion is not claimed.

The local baseline performs a final current check immediately before dispatch. Do not claim globally atomic distributed revocation or cancellation of in-flight calls.

## 9. Metadata receipt

GET /api/requests/{request_id}/receipt

Creator-only response 200 after a blocked or final outcome:
```json
{
  "schema_version":"1.0",
  "request_id":"<opaque-id>",
  "account_id":"analyst_a",
  "dataset_id":"feedback_a",
  "dataset_revision":1,
  "policy_version":1,
  "preview_policy_version":1,
  "review_revision":1,
  "purpose":"feedback_summary",
  "destination":"demo_receiver",
  "decision":"redact",
  "status":"sent",
  "reason_codes":["REDACTION_REQUIRED"],
  "redaction_counts":{"EMAIL":1,"PHONE":0},
  "additional_hidden_messages":0,
  "prepared_payload_hash":"<computed-sha256>",
  "confirmed_sent_payload_hash":"<same-hash-for-acknowledged-success>",
  "receiver_mode":"local_demo",
  "receiver_attempts":1,
  "occurred_at":"<UTC-ISO8601>"
}
```

In this receipt, policy_version is the current policy evaluated for the final dispatch/denial decision. preview_policy_version is the policy version bound to the prepared preview, or null if no preview was prepared. On a revoked request these versions may differ; preserve the prepared payload hash as metadata while confirmed_sent_payload_hash remains null.

confirmed_sent_payload_hash is null when delivery is not acknowledged. A blocked request can have no prepared hash if no preview was prepared. Never include source values, complete prompts/payloads, filenames, tokens, credentials, or other accounts' content.

Before a final/block outcome return 409 RECEIPT_NOT_READY. Another creator receives 403 REQUEST_ACCESS_DENIED. Source access revocation does not prevent the creator reading this metadata-only record.

## 10. Error envelope

All error responses should have:
```json
{
  "error":{
    "code":"ACCESS_REVOKED",
    "message":"Dataset access is no longer permitted.",
    "request_id":"<id-or-null>",
    "action":"Choose another dataset or contact its owner."
  }
}
```

Use stable machine codes and plain messages. Default validation errors should be adapted to INVALID_REQUEST without echoing submitted sensitive values.

Core codes: AUTH_REQUIRED, INVALID_SESSION, DATASET_NOT_FOUND, DATASET_ACCESS_DENIED, REQUEST_NOT_FOUND, REQUEST_ACCESS_DENIED, PURPOSE_NOT_ALLOWED, DESTINATION_NOT_ALLOWED, SHARING_PROHIBITED, DATASET_INVALID, INVALID_REQUEST, INVALID_REVIEW, NO_CONTENT_TO_SEND, REVIEW_CHANGED, PREVIEW_CHANGED, DATASET_CHANGED, POLICY_CHANGED, ACCESS_REVOKED, ALREADY_DISPATCHED, REQUEST_NOT_READY, RECEIPT_NOT_READY, RECEIVER_FAILED.

Policy codes appear in blocked-preview reason_codes; transport/auth/state errors use the error envelope.

## 11. Demonstration controls and tests

No public permission-edit API is required. Provide a local owner CLI/helper:

```text
python -m app.demo_control revoke --account analyst_a --dataset feedback_a
python -m app.demo_control grant --account analyst_a --dataset feedback_a
```

It edits the shared runtime SQLite policy and increments policy_version. The running backend reloads current policy at protected operations. CLI has local operator authority; it is not an analyst form.

Tests inject isolated fixtures/store and a capturing or failing receiver. Inspect actual adapter invocations and captured bytes. Do not expose a global unauthenticated payload-capture endpoint.

## 12. Future contract changes

Layer tasks preserve v1 by default. Changes to routes, names, states, payload template, database schema or startup behavior require one coordinated update to this file, backend schema, frontend types and tests. No assistant invents a parallel API version independently.


## 12. Implemented v1.1 extension

The user explicitly assigned all six layers on top of `base-line` commit `21f5abc`. Existing v1 request bodies remain accepted. Receiver payload and metadata receipt retain schema_version `1.0`; audit exports/security reports use `1.1`. API application version is `1.1.0`.

### Preview and review response additions

Every preview response includes:

```typescript
raw_view_allowed: boolean
original_messages: string[] | null
findings: {
  id: string; message_index: number; start: number; end: number;
  category: string; replacement: string; mandatory: boolean; detector: string;
}[]
manual_spans: {message_index: number; start: number; end: number}[]
detector_status: {
  available: boolean; model: string; version: string | null; fingerprint: string;
  // Additional metadata-only version/artifact descriptor fields are allowed.
}
policy_explanations: {
  field: string; result: 'included' | 'excluded' | 'redacted';
  explanation: string; rule_id: string;
}[]
```

Raw review requires both current dataset-processing access and a separate owner raw-message grant. Fresh seeds authorize raw review only for analyst_a/feedback_a. Without it, `original_messages=null`, `findings=[]`, and manual source-span selections are forbidden; transformed processing and whole-message hiding remain possible. Excluded CSV columns are never sent to the browser. Blocked previews contain no original/outbound content or findings.

Finding/manual offsets are zero-based Unicode **code points in the original retained message**, not UTF-16 or offsets in the pseudonymized text. The browser converts DOM selections accordingly. Finding text/identity mappings are not separate API fields; originals may be returned only with raw access.

Current supported owner redactions are EMAIL, PHONE, PERSON. Required unknown detectors or configured unsupported operations/field templates produce a recorded 200 blocked preview with reason `UNSUPPORTED_POLICY`. Required PERSON unavailability/inference failure returns the fixed error envelope, HTTP503 `DETECTOR_UNAVAILABLE`; no dispatch is performed. Fresh policies require all three types. EMAIL/PHONE use baseline tokens; equal case-folded, whitespace-normalized PERSON surfaces share `[PERSON_001]`-style tokens across a request, assigned before optional hiding. Aliases are not resolved, and state resets between requests. Overlap resolution must preserve the coverage of mandatory detections.

### Review body additions

```json
{
  "expected_review_revision": 1,
  "expected_preview_hash": "<current 64-char lowercase sha256>",
  "hide_message_indices": [],
  "manual_spans": [{"message_index":0,"start":5,"end":13}]
}
```

Both new fields are optional for old clients; the new frontend always supplies both. Omitted `manual_spans` preserves stored choices; an explicit `[]` clears optional spans only. It cannot remove mandatory detections. Spans are strict nonboolean integers, in-bounds and nonempty; at most1000 spans and10000 whole-message indices. Invalid spans yield422 `INVALID_REVIEW` (malformed schemas422 `INVALID_REQUEST`) without changing the draft. Nonempty manual choices require raw access or403 `RAW_ACCESS_DENIED`. Overlapping spans are unioned by the backend; it rebuilds payload from source and never accepts replacement outgoing text.

A supplied mismatching expected hash yields409 `PREVIEW_CHANGED`. Review revision still increments on every accepted review. Changes to source/policy/raw grants/detector implementation/model invalidate prior approval. Detector and transformation implementation fingerprints augment baseline binding; old drafts without this fingerprint require regeneration.

### History, events and export

All routes require a valid demo token and expose metadata only:

- `GET /api/history?dataset_id=&decision=&user_id=` returns `{requests: HistoryRow[], total:number}`. At most the latest200 matching rows, creator only; total is the number returned. user_id is optional and must equal the authenticated account or403 `REQUEST_ACCESS_DENIED`. No admin/global user browsing is implemented. Dataset/decision strings use parameterized SQL and unknown values simply match no rows.
- `GET /api/requests/{request_id}/timeline` returns `{request_id, events: AuditEvent[]}`.
- `GET /api/requests/{request_id}/audit` returns `{schema_version:'1.1', request:HistoryRow, events:AuditEvent[], receipt:Receipt|null}`.

```typescript
type HistoryRow = {
  request_id:string; dataset_id:string; purpose:string; destination:string;
  status:string; decision:string; created_at:string; occurred_at:string|null;
  receiver_attempts:number; review_revision:number|null;
}
type AuditEvent = {
  event_id:string; event_type:string; actor_kind:string; actor_id:string;
  occurred_at:string; metadata:Record<string, unknown>;
}
```

Events are recorded with actual request transitions in the same SQLite transaction: preview, review, send_claimed, send, send_failed, blocked, approval_invalidated. Local owner CLI permission/source changes use actor_kind `local_operator`, actor_id `demo_control`; never impersonate an analyst. Relevant dataset/operator changes during the request lifetime appear in that creator's timeline. Logs contain only allowlisted IDs/counts/reasons/hashes/versions, never selected strings or mapping tables. Earlier baseline requests have no fabricated historical events.

Creator ownership is checked for timeline/audit/receipt even after source access revocation. Reading metadata history does not grant source-preview access. Another creator receives403. Unfinished requests export `receipt:null`.

### Security test dashboard

`GET /api/security/report` returns:

```typescript
{
  available:boolean; stale:boolean; source_fingerprint:string;
  report:null | {
    schema_version:'1.1'; generated_at:string; source_revision:string|null;
    working_tree_dirty:boolean; source_fingerprint:string;
    total:number; passed:number; failed:number; skipped:number; duration_seconds:number;
    receiver_mode:'local_demo';
    controls:{id:string; title:string; status:'passed'|'failed'|'not_run'; tests:number}[];
    tests:{id:string; status:'passed'|'failed'|'skipped'; duration_seconds:number}[];
  }
}
```

There is no HTTP test-execution route. `python -m app.security_report` runs the fixed test suite in a subprocess with isolated temporary storage and writes sanitized metadata. Parameterized test input strings and failure/stdout content are stripped. Source fingerprint covers backend code/tests/fixtures/dependencies and frontend source/dependencies/config. A change during execution prevents report publication; subsequent changes set `stale=true`. Missing reports return availablefalse/reportnull, never invented passing results. Runtime report is preferred, committed sanitized report is a fallback. These are editable local artifacts, not signed attestations. Receiver call claims refer to the tested adapter in isolated synthetic scenarios, not external model traffic.

### Owner CLI and storage migration

New local operator commands: `raw-grant`, `raw-revoke` (account/dataset), `require-person` (dataset). Each bumps the policy version and records a metadata change. Existing grant/revoke/sharing/bump-policy/edit-source also record changes. No analyst permission-edit route exists.

Startup additively creates raw_grants and audit_events and adds request manual_spans/pipeline_fingerprint fields. Existing policies/permissions/source copies remain untouched; new raw access is never silently granted to an existing runtime DB.

# DataGate API contract v1

Status: implementation target, not an existing running API. This is the authoritative wire contract. Change it only through the human/integration owner, with coordinated frontend/backend/tests updates.

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
  "custom_redactions":[],
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

Indices are zero-based positions in the registered source under its fixed revision. Requesters may hide whole messages and redact parts of messages (below); nothing else. Deduplicate/sort valid indices. Replace selected messages with [HIDDEN_BY_USER]; never restore mandatory-redacted text from client input.

Return the full ready-preview shape with incremented review_revision, new payload/hash and hidden_message_indices. A stale expected revision gets 409 REVIEW_CHANGED. Invalid/out-of-range indices get 422 INVALID_REVIEW. Refuse to prepare a request with all messages hidden: 422 NO_CONTENT_TO_SEND, leaving the existing review unchanged.

### 7.1 Custom redactions (v1.1, additive)

Coordinated contract change: requested by the human in the Oct 18, 2026 chat; backend schema, frontend types and tests updated together. Payload template and schema_version are unchanged.

Optional request field:
```json
{"expected_review_revision":2,"hide_message_indices":[],
 "custom_redactions":[{"message_index":1,"start":6,"end":19}]}
```

- Each span refers to the **mandatory-redacted text** of one message (the text the preview showed before any requester choice), in Unicode code points, end-exclusive. The client sends offsets only, never text.
- The backend replaces each span with `[REDACTED_BY_USER]` after mandatory redaction, then applies whole-message hiding. Spans can only remove more content; they never restore anything.
- Omitting `custom_redactions` keeps the stored spans; `[]` clears them. `hide_message_indices` keeps its complete-replacement meaning.
- Overlapping or touching spans in one message are merged; the response echoes the normalized, sorted list as `custom_redactions` (empty on blocked previews).
- A span may cover a mandatory placeholder such as `[EMAIL]` completely but may not cut through one. `redaction_counts` still reports the owner-rule counts.
- Spans on a hidden message are kept, so restoring the message restores them.
- 422 INVALID_REVIEW: index or offsets out of range, `start >= end`, a span cutting through a placeholder, more than 20 spans in one message or more than 200 in total. Wrong types or unknown span fields: 422 INVALID_REQUEST.
- 422 NO_CONTENT_TO_SEND also applies if, after hiding and custom redaction, no message contains anything besides `[REDACTED_BY_USER]`, `[HIDDEN_BY_USER]` and whitespace. The existing review is left unchanged.
- Drafts store spans as offsets (no text). Send rebuilds the payload from the source plus stored spans and compares the hash as usual.

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
  "additional_custom_redactions":0,
  "prepared_payload_hash":"<computed-sha256>",
  "confirmed_sent_payload_hash":"<same-hash-for-acknowledged-success>",
  "receiver_mode":"local_demo",
  "receiver_attempts":1,
  "occurred_at":"<UTC-ISO8601>"
}
```

additional_custom_redactions counts normalized custom spans on messages that were not hidden. It is a count only; the receipt never contains span text or offsets.

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

## 13. Security evidence report (additive, read-only)

GET /api/evidence/security-report

No Authorization header: the response contains no dataset content, identities or tokens. It reads the report file written by `python -m app.security_report` (default `backend/var/reports/security-report.json`, override with DATAGATE_REPORT_PATH). It never runs tests and never touches the demo database. Response 200, `Cache-Control: no-store`:

```json
{
  "availability":"available",
  "problem":null,
  "current_commit":"<40-hex or null>",
  "current_dirty":false,
  "freshness":"current",
  "report":{"schema_version":"1.0","report_type":"datagate-security-regression","generated_at":"<UTC>",
    "git":{"commit":"<40-hex or null>","dirty":false},
    "suite":{"id":"backend-pytest","command":"python -m app.security_report","run_status":"complete",
             "pytest_exit_code":0,"tests_collected":79,"tests_passed":79,"tests_failed":0,"tests_not_run":0,"duration_seconds":1.5},
    "isolation":{"storage":"...","receiver":"...","runtime_db_unchanged":true},
    "totals":{"passed":14,"failed":0,"not_run":0},
    "scenarios":[{"id":"SEC-01","title":"...","claim":"...","result":"passed","duration_seconds":0.02,
                  "tests_total":3,"tests_passed":3,"tests_failed":0,"tests_not_run":0,
                  "evidence":["test_flow.py::test_..."],"failure_summary":null}],
    "disclaimer":"..."},
  "disclaimer":"..."
}
```

- availability: `available | missing | invalid`. A malformed file, an unsupported `schema_version`/`report_type`, an unknown result or run status, or a file that fails the prohibited-content scan is `invalid`, with a safe `problem` and `report: null`.
- freshness: `current` (report commit == running commit), `stale` (differs) or `unknown` (either commit unavailable).
- result: `passed | failed | not_run`; run_status: `complete | interrupted | error`. Totals are recomputed by the server from the scenarios. A catalogue scenario that is absent from the file is returned as `not_run`.
- failure_summary contains only a test name, a phase and an exception class name. Reports never contain messages, customer values, tokens, payloads or tracebacks.

## 14. Creator-only receipt timeline (additive)

GET /api/receipts

Requires `Authorization: Bearer <demo-session-token>`. The account is always the token's account; there is no account parameter. The single-receipt route (§9) is unchanged.

Query parameters (all optional; anything else, including `account_id`, or a repeated parameter returns 422 INVALID_REQUEST without echoing the value):

| Parameter | Values |
| --- | --- |
| `limit` | 1–100, default 20 |
| `cursor` | opaque `next_cursor` from a previous page |
| `status` | `blocked`, `stale`, `sent`, `send_failed` |
| `decision` | `allow`, `redact`, `block` |
| `dataset_id` | identifier; only narrows the caller's own records |
| `since`, `until` | ISO-8601 with a timezone; `since` inclusive, `until` exclusive, `since < until` |

Response 200:
```json
{"receipts":[{"...single receipt fields (§9)...":"", "recorded_at":"<UTC>"}],"next_cursor":"<opaque or null>","limit":20}
```

- Items are the caller's own requests with an outcome: `blocked`, `stale`, `sent` or `send_failed`. Drafts (`ready`) and in-flight `sending` rows are not listed. Each item has exactly the single-receipt fields plus `recorded_at`.
- `recorded_at` is `occurred_at`, or `created_at` for older rows recorded without one. Requests that become `stale` now record `occurred_at`. The single-receipt route still answers 409 RECEIPT_NOT_READY for stale requests, as before.
- Order: `recorded_at` descending, then `request_id` descending (stable for identical timestamps). `next_cursor` is null when there is no further item, so a boundary never yields an empty extra page.
- Not gated on current dataset access: a revoked creator still lists their receipts but cannot preview again.
- Another account's records are never returned. A `dataset_id` the caller never used, or another account's cursor, yields the same empty page as an unknown value, so nothing can be inferred.
- Metadata only: never message text, payloads, prompts, detected values, redaction spans or mappings, tokens, file names or paths.

## 15. PERSON redaction and numbered pseudonyms (additive)

Coordinated change requested by the human on Oct 18, 2026. Backend schema, frontend types, tests and docs were updated together. The payload template and `schema_version` are unchanged.

- `required_redactions` may include `PERSON` (supported: `EMAIL`, `PHONE`, `PERSON`). The passport (§5) adds `person_style`: `generic` → `[PERSON]`, `numbered` → `[PERSON_1]`, `[PERSON_2]`, …
- Precedence inside a message: EMAIL > PHONE > PERSON. PERSON spans are trimmed to exclude EMAIL/PHONE ranges, and overlapping PERSON spans merge. Replacement is by offset; no character is transformed twice.
- Numbering is request-scoped and backend-only: source order over all messages, before hiding, keyed by normalized name (NFC, trimmed, whitespace collapsed, case-folded). The mapping is never stored, returned, logged or put in receipts. `redaction_counts.PERSON` counts replaced spans.
- Source-authored placeholder-like tokens (`[EMAIL]`, `[PHONE]`, `[PERSON]`, `[PERSON_n]`, `[HIDDEN_BY_USER]`, `[REDACTED_BY_USER]`, any case) are rewritten with parentheses before redaction. Square-bracket tokens in outbound text therefore always come from DataGate.
- Custom redaction spans (§7.1) may cover a `[PERSON]`/`[PERSON_n]` token completely but may not cut through one.
- No request field accepts a mapping, pseudonyms or replacement text (unknown fields: 422 INVALID_REQUEST).
- New errors: `503 DETECTOR_UNAVAILABLE`: PERSON is required but detection failed. Nothing is prepared at preview. At review or send the draft becomes `stale` with that reason and the receiver is not called. `409 TRANSFORM_CHANGED`: the transformation or detector version differs from the one that built the preview. The draft becomes `stale`, with zero receiver calls.
- Approval freshness now also covers `person_style` (policy fingerprint) and the transformation/detector pipeline id.

## 12. Future contract changes

Layer tasks preserve v1 by default. Changes to routes, names, states, payload template, database schema or startup behavior require one coordinated update to this file, backend schema, frontend types and tests. No assistant invents a parallel API version independently.

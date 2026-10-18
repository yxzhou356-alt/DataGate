# DataGate — authoritative project context

Status: planning packet; baseline implementation has not started as of this packet's preparation. All human work assignments are UNASSIGNED.

## 1. Team, event, and goal

Team: Priyanka, Ishita, Yuxin, Aishwarya. All have programming experience; this is their first hackathon.

Event: USC ACM TrojanHacks, October 17–18, 2026. Track: AI Data Governance. Submission deadline: Sunday October 18, noon America/Los_Angeles; target submission 11:15 a.m. Presentations: four minutes, then one minute Q&A in preliminaries; finalists have three minutes Q&A.

The packet conflicts about Saturday venue closing (7 p.m. versus 10 p.m.). Follow organizer clarification and prepare to relocate by 7 p.m. No overnight room access is promised.

Goals: a meaningful company workflow, an honest working demo, learning, and a portfolio artifact for software/AI/data roles. No company/judge interest or winning outcome is guaranteed.

The supplied judging rubric is 25% problem/impact, 25% technical execution/completeness, 25% UX/design, 15% innovation and 10% demo/presentation. This favors a complete, understandable workflow and demonstrated behavior over a long list of unfinished features.

The team's supplied judge list names Kaushal Patel (OpenAI), Franck Leveneur (Data-Sleek; formerly Hulu), Saty Raghavachary (USC) and Chris Lin (Cylier; formerly Uber). These affiliations are event context supplied by the team, not independently verified hiring leads. Explain concrete value and tradeoffs; do not infer individual judges' preferences.

## 2. Final product direction

DataGate combines:
- DataGate: dataset rules, purpose/destination policy, minimized outbound data.
- Bouncer: reviewable content and additional permitted hiding.
- AccessCheck-inspired checks: authorization, revocation, stale approvals, repeatable regression evidence.
- Light input validation only, not the full BatchGuard model-impact product.

Tagline: Permission, review, and evidence before data reaches AI.

Problem statement:
A support analyst wants AI to summarize customer complaints. The source contains identifying information and customer-specific records. The company needs to control who may use each dataset, for what task and destination, what content leaves, and whether permission still exists when sending.

The prototype governs its configured gateway path. It does not monitor all employee traffic or control recipients after delivery.

## 3. People and access

- Dataset owner/admin: registers source data and configures policies. Baseline setup is seeded on the backend; no administration website is required.
- Analyst: uses the interface to choose an authorized dataset, choose a task, inspect an outbound preview, and approve sending.
- DataGate backend: holds source CSVs, authoritative policies, sessions, transformations and dispatch state.
- Receiver: receives only the prepared payload, never the original spreadsheet.

The AI service has no direct spreadsheet/database access. Analysts receive no unauthorized dataset content. Two customer datasets are separate server-held fixtures.

Baseline identity is a clearly labeled demo account selector that obtains a server-issued token for one of two seeded accounts. Anyone running this local demo can select a demo account: this is not production authentication. Subsequent authorization checks use the token's backend identity, not caller-supplied user_id/role.

## 4. Frozen baseline stack

- Frontend: React + TypeScript + Vite, one small application, no routing/UI framework required.
- Backend: Python + FastAPI + Pydantic.
- Persistence: Python sqlite3 for metadata, requests and receipts; raw synthetic CSVs in backend-accessible fixtures.
- Transformations: Python csv, re, json and hashlib.
- Tests: pytest + FastAPI TestClient/httpx.
- Receiver: local capturing adapter, no external API key.
- One backend worker; short-lived sessions/draft payloads may be in memory. Restarted/expired drafts require a new preview.

Use compatible installed runtimes and record actual dependency versions in manifests/lockfiles. Inspect the environment before installing. Do not invent version requirements or rewrite the stack independently.

Keep useful module boundaries for later parallel work: backend policy evaluation, transformations, storage, request workflow and receiver adapter should be identifiable without reading one giant file. Separate frontend API/types from review and outcome components. The baseline owner chooses the small concrete layout and documents its actual files and extension points in the handoff; do not build a generic plugin framework.

## 5. Frozen data and identifiers

Accounts:
- analyst_a: MapleCo analyst; may use feedback_a.
- analyst_b: RiverCo analyst; may use feedback_b.

Datasets:
- feedback_a: MapleCo feedback, initially 10 synthetic rows.
- feedback_b: RiverCo feedback, initially 10 synthetic rows.

Fixture columns:
ticket_id, customer_name, email, phone, plan_tier, account_value, product_area, message.

Read values as strings. At minimum ticket_id and nonempty message must be present. Unexpected columns must never be forwarded automatically. Preserve quoted CSV fields and Unicode. Never silently repair/drop rows.

Purpose: feedback_summary. A model_training request may be submitted as a blocked demonstration, but no training operation is implemented.

Destination: demo_receiver, a backend-configured identifier. No caller-provided destination URL.

Both sample policies authorize only the corresponding analyst, feedback_summary and demo_receiver, with message as the only outbound field. Supported required redaction types are EMAIL and PHONE; PERSON (local name detection, optionally numbered per request) was added as a human-assigned post-baseline layer on Oct 18, 2026 and is off in the default policies. See API_CONTRACT.md §15.

Example:
Input message: The reset link expired. Please contact emma@example.com.
Outbound message: The reset link expired. Please contact [EMAIL].

Customer name, account value, email column, etc. are excluded regardless of whether their particular values are detected inside a message. Scan the retained message for embedded supported identifiers. Baseline does not automatically detect all names, health information, addresses, or arbitrary secrets.

## 6. Owner policy

Configure for each dataset:
- dataset ID, declared owner/source, source revision.
- allowed account IDs.
- allowed purposes.
- allowed destination IDs.
- purpose-specific outbound fields.
- sharing_mode: redacted_only or none.
- required redaction types.
- policy_version plus an internal fingerprint of the current policy.

redacted_only means the configured minimization/redaction pipeline must be applied; it does not promise complete anonymity. none blocks any sharing, even after redaction.

Owner rules always win. Requester choices may hide additional content, not add excluded fields or reverse mandatory hiding.

Baseline review choices are deliberately simple: optionally hide selected whole message entries after mandatory redaction. Use zero-based message indices under the immutable source revision. Replace these entries with [HIDDEN_BY_USER]. No second purpose is needed.

Post-baseline layer (human-assigned Oct 18, 2026): analysts may also redact selected parts of any number of messages. The browser sends only code-point offsets into the mandatory-redacted text; the backend replaces those spans with [REDACTED_BY_USER]. This supplements, and never relaxes, the owner's EMAIL/PHONE rules. See API_CONTRACT.md §7.1.

## 7. End-to-end flow

1. Owner setup seeds source fixtures and rules.
2. Analyst selects a demo account and receives a token.
3. GET datasets lists only their accessible metadata.
4. Analyst requests feedback_summary through demo_receiver.
5. Backend checks identity, dataset access, purpose/destination, sharing mode and minimum input validity.
6. Backend retains message only, then redacts supported email/phone spans.
7. Backend returns the exact receiver payload preview, hash, reason codes, counts and review revision.
8. Additional hiding changes the preview and increments review_revision.
9. Analyst approves the current revision/hash and presses Send.
10. Backend rechecks current access, source bytes/revision, current policy/fingerprint, review and payload. Changed data/policy requires a fresh preview; revoked access blocks.
11. Backend atomically marks a ready request sending. Only the winning dispatch may invoke the adapter.
12. Local receiver captures the prepared content and returns an acknowledgement labeled local_demo.
13. Backend records sent or send_failed and a metadata-only receipt.

Source/policy checks must use current data, not only startup-cached metadata. The policy version is incremented for legitimate changes, while fingerprints also detect an out-of-band change.

Permission revocation applies to future dispatch checks. It cannot recall already sent content or erase a previously viewed preview. This is not a distributed atomic-revocation system.

## 8. Actual local receiver

Use one adapter entry point: send(request_id, payload_bytes).

The local adapter really receives/captures those bytes in memory and records request-scoped invocations. It returns an acknowledgement such as:
mode=local_demo, acknowledged=true, message_count=10, note=No external AI model was called.

Do not label this canned acknowledgement as generated AI analysis. No public endpoint should expose all captured payloads. Tests inspect the injected capturing adapter directly.

All future provider integration must use this same dispatch boundary. Count actual adapter invocations, not a manually set dashboard value. Failed/uncertain delivery still counts an invocation; do not call it zero attempts.

## 9. States and interface authority

Wire formats, enum spellings, routes, hashes and errors are defined ONLY in API_CONTRACT.md.

Policy decision: allow, redact, block.
Request status: ready, blocked, stale, sending, sent, send_failed.

ready means prepared and awaiting explicit approval, not previously authorized forever.

The backend owns source, identity, policies, transformed payload and dispatch state. The frontend owns display/interaction only. Send submits approval of an existing draft, not raw replacement content.

## 10. Baseline definition of done

A second teammate must be able to start the app from README instructions and demonstrate:
1. Authorized dataset selection and a real transformed preview.
2. Message-only outbound fields with supported email/phone spans hidden.
3. Approved content reaches the local receiver exactly once and matches the preview hash/content.
4. Other accounts cannot access the dataset, draft, review or receipt.
5. Forbidden purposes/destinations/sharing mode make zero adapter calls.
6. Mandatory redaction cannot be undone via request-body tampering.
7. Revocation after preview blocks Send.
8. Changed source/policy/review makes the previous approval invalid.
9. Duplicate/concurrent Send makes no second invocation.
10. Receiver errors produce an honest failure outcome.
11. Receipts exclude raw values/full messages/prompts and state the real receiver mode.
12. Backend tests pass, frontend builds, and actual startup/verification commands are documented.

Use isolated temporary databases/fixtures in tests; never mutate the team's demonstration database during tests.

## 11. Deferred layers

Only after accepting the baseline:
- Better review cards and additional hiding UX.
- More policy tests and a factual regression summary.
- Duplicate-ticket/readiness checks and clear row-level errors.
- One real provider, if a human assigns a provider/credentials.
- One pretrained person-name detector with a labeled evaluation.
- Hash-chain receipts with verification and a separately retained checkpoint.

Defer: full BatchGuard scoring pipeline, bank lineage/FinGuard, invoice matching, RAG/vector database, generic file uploads, OCR/PDFs, free-form SQL/policy generation, custom training, enterprise authentication and deployment infrastructure.

Purpose-specific field selection and user review do not establish regulatory compliance. Analyst approval is not automatically customer consent. A receipt/hash is evidence about this gateway's processing, not proof of complete privacy or recipient behavior.

## 12. Team status

Names: Priyanka, Ishita, Yuxin, Aishwarya.
All implementation assignments: UNASSIGNED.
Baseline assistant owner: UNASSIGNED.
Integration owner: UNASSIGNED.
Accepted baseline commit: NOT YET AVAILABLE.

The human team will decide ownership. Use TEAM_WORKFLOW.md and the prompts directory. No assistant may infer an assignment from an older document.

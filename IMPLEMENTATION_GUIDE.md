> Historical planning guide. The implemented six-feature branch is documented in README.md, PROJECT_CONTEXT.md, API_CONTRACT.md, TEAM_WORKFLOW.md and FEATURE_HANDOFF.md. Those current files take precedence over older phase/status/assignment statements below.

# DataGate implementation guide — current baseline-first version

This guide has been updated for the team's latest decision: ONE coding assistant builds the complete baseline, then teammates' assistants add bounded layers or debug it. Human responsibilities are UNASSIGNED.

No application implementation is implied by this document.

## Authoritative information

- AGENTS.md: repository instructions and edit boundaries.
- PROJECT_CONTEXT.md: product, actors, scope and definition of done.
- API_CONTRACT.md: exact v1 routes, JSON, states and errors.
- TEAM_WORKFLOW.md: ownership, baseline acceptance and parallel workflow.

These replace the older provisional named assignments, optional framework choices and afternoon schedules.

## 1. Understand the application

The owner registers customer feedback and rules. An analyst requests a summary, reviews permitted outgoing content and approves. DataGate checks access before preview and again before sending. Only the prepared payload reaches the receiver; the original spreadsheet stays on the backend.

Baseline stack: React/TypeScript/Vite + Python/FastAPI/Pydantic + sqlite3 + standard-library CSV/regex/hash functions + pytest/httpx. No external API key, model training or vector database.

## 2. Choose the baseline owner

One human/member and their coding assistant claim the baseline task. Give that assistant prompts/BASELINE_AGENT_PROMPT.md and the authoritative documents. It should build the working app, not generate another plan.

Other assistants can read/review the contract but should not independently scaffold applications. Task ownership remains unassigned until the human chooses it.

## 3. Build one complete local path

1. Seed two 10-row synthetic CSVs and two demo identities.
2. Map tokens to backend accounts; list only accessible datasets.
3. Implement one purpose, feedback_summary, and one destination, demo_receiver.
4. Keep message only and redact supported email/phone spans inside retained text.
5. Return the exact canonical receiver payload, counts, reason codes, preview hash and review revision.
6. Support simple additional whole-message hiding while keeping mandatory masking intact.
7. Accept explicit approval of the current draft/revision/hash.
8. Check current access, source/policy fingerprints and review again.
9. Atomically claim dispatch and call the sole capturing adapter once.
10. Produce an actual local acknowledgement and metadata-only receipt.

ready is not a permanent approval. Requests that changed or lost access cannot dispatch from an old preview.

Use the API contract exactly. Draft payloads may remain in short-lived backend memory; metadata is in a local runtime SQLite DB. Restarted drafts require a fresh preview. Use one backend worker.

## 4. Verify before handoff

Required: allowed request, forbidden dataset, forbidden purpose/destination, mandatory-redaction tampering, revocation, stale source/policy/review, duplicate/concurrent Send, receiver failure, receipt privacy and ownership.

Inspect actual captured canonical bytes and request-scoped adapter calls. The local test receiver is not an external AI model. Backend tests and frontend build must run. Another teammate should reproduce the UI journey from README.

The baseline assistant records actual commands/results and known limits. It does not mark unverified work complete.

## 5. Accept and share the baseline

Use one shared Git repository. Record the accepted commit and startup instructions in README and TEAM_WORKFLOW.md. Do not invent a remote URL.

Before other assistants implement layers, each uses a separate clone or worktree starting at the same accepted commit. Never let multiple chats switch branches in one checkout.

## 6. Add bounded layers

Use prompts/LAYER_AGENT_PROMPT.md with a human-assigned goal, owned files, baseline commit and acceptance condition.

Possible unassigned workstreams:
- Review/UX polish.
- Expanded authorization/regression evidence.
- Input-quality feedback.
- One real provider behind the adapter.
- Local pretrained name detection and honest evaluation.
- Optional receipt integrity.
- Demo/docs/reliability.

The integration owner coordinates shared schemas, routes, dependency manifests/lockfiles, storage structure and startup changes. Keep the v1 contract unless a coordinated change is approved.

## 7. Priority and scope

Purpose minimization, access controls, mandatory redaction, Send rechecks and zero-call tests are baseline requirements. They must not be postponed while decorative dashboards are built.

A model_training request is a denied policy demonstration, not an implemented training pipeline.

Defer full BatchGuard model impact, banking lineage, invoice matching, general uploads/PDF/OCR, custom training, vector search, full enterprise authentication and deployment infrastructure.

Sharing choices do not establish legal consent. Passing synthetic tests do not guarantee complete detection/security. Receipts record the gateway's real actions; they are not compliance certificates.

## 8. Next handoff

Follow TEAM_WORKFLOW.md for the live owner/status table and prompts/REVIEW_OR_DEBUG_PROMPT.md for independent review. Replace this planning status with actual implementation evidence only after it exists.

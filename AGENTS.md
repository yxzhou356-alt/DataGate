# DataGate repository instructions for coding assistants

## Read first

1. Read PROJECT_CONTEXT.md for the agreed product and baseline.
2. Read API_CONTRACT.md for the frozen v1 interfaces.
3. Read TEAM_WORKFLOW.md for the current phase, ownership, and handoff process.
4. Read the human's assigned task and its permitted files.

System/developer instructions and the human's current directions take precedence. Within the project, API_CONTRACT.md owns wire formats and PROJECT_CONTEXT.md owns scope. IMPLEMENTATION_GUIDE.md and TROJANHACKS_TEAM_ROADMAP.md are navigation/build summaries, not alternative specifications.

## Current project state

At preparation of this packet, the workspace contained planning documents only: no application, tests, dependencies, or local Git repository. Update README.md and TEAM_WORKFLOW.md when this changes. Never claim planned features or checks are implemented/passing.

Team members are Priyanka, Ishita, Yuxin, and Aishwarya. Task assignments are UNASSIGNED. Prior suggested assignments are not commitments.

## Baseline-first workflow

- One designated assistant builds ONE complete baseline first.
- During that phase, other teammates' assistants may review the specification or design tests without changing application files.
- After the baseline is verified and shared, layer/debug assistants start from the same accepted baseline commit.
- Use separate clones or worktrees for simultaneous assistants. Do not switch branches from multiple chats sharing one checkout.
- Claim a bounded task through the human/team coordinator before editing. Respect file ownership.
- Coordinate changes to API schemas, routes, dependencies, lockfiles, database structure, and startup commands with the integration owner.
- Do not independently replace the scaffold, change frameworks, or build another application.
- Coordinate through Git and the human team; do not autonomously message other chats.

## Frozen baseline

React + TypeScript + Vite; Python + FastAPI/Pydantic; Python sqlite3; standard-library CSV, regex, JSON and SHA-256; pytest/httpx.

Two backend-held synthetic datasets, two seeded demo analyst identities, one implemented purpose (feedback_summary), one destination (demo_receiver), message-only field selection, supported email/phone redaction, reviewed preview, send-time checks, local capturing receiver, ordinary metadata receipt.

Demo identity selection is intentionally simulated authentication. Backend authorization must still derive identity from the issued token rather than user_id/role in request bodies. Do not describe this as production login.

No API key is required for the baseline. The local receiver is NOT an external AI model. Label it explicitly.

## Non-negotiable behavior

- Owner/company rules win over requester choices.
- No-sharing policy blocks even redacted data. Redacted-only sharing must be explicitly permitted.
- Check access before exposing a preview, when reviewing, and immediately before dispatch.
- Restrict fields on the backend, then scan retained text.
- Build the authoritative payload on the backend. Never forward a browser-supplied sanitized payload.
- Bind review to account, dataset, source hash, policy version/fingerprint, purpose, destination, review revision, and canonical payload hash.
- Reject stale approval. Atomically claim a ready request before dispatch so duplicate/concurrent Send cannot invoke the receiver twice.
- Route every receiver call through one adapter; no automatic dispatch retries.
- Receipts contain metadata, not raw customer values, complete messages, whole prompts, or credentials.
- Restrict draft and receipt access to their creator. A creator may read their metadata receipt after access revocation, but not regenerate/access revoked source previews.
- Use synthetic fixtures only. Keep runtime DBs, credentials and payload captures out of Git.

## Verification and reporting

Run meaningful backend tests and the frontend build. Smoke-test the documented UI if browser tools are available; otherwise state that visual verification was not performed. Use isolated test storage. Do not fabricate test outputs, coverage, latency, provider calls, or user validation.

A handoff must include changed files, exact commands run/results, startup instructions, working scenarios, remaining limits, contract changes, and the branch/commit if available.

## Deferred features

Do not add a real provider, NER, hash chains, uploads, editable admin UI, vector search, custom training, deployment infrastructure, or another task unless the human explicitly assigns that layer after baseline acceptance.

An analyst's sharing choices are not verified customer consent. A hash chain is not tamperproof storage. Passing fixtures are not universal security/privacy guarantees.

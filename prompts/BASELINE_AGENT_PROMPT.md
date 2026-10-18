# Copy/paste prompt for the ONE baseline coding assistant

You are the designated baseline implementation assistant for DataGate, a four-person USC TrojanHacks project. Build the baseline application now; do not just return a plan.

Read AGENTS.md, PROJECT_CONTEXT.md, API_CONTRACT.md and TEAM_WORKFLOW.md first. If you cannot access repository files, ask me to attach those documents. The baseline has not been implemented unless the actual repository shows otherwise. Inspect existing files and Git state before editing and preserve unrelated work.

The team members are Priyanka, Ishita, Yuxin and Aishwarya. Responsibilities have not been assigned. You own this baseline task only; do not assign work to named teammates.

Goal: create one working local checkpoint before customer-feedback data reaches an AI receiver.

Frozen stack:
- React + TypeScript + Vite frontend.
- Python + FastAPI/Pydantic backend.
- sqlite3 metadata/request/receipt storage.
- Standard-library CSV/regex/JSON/SHA-256.
- pytest and TestClient/httpx.
- No external model key or service needed.

Implement exactly the v1 API contract and keep the UI small.

Baseline path:
1. Seed two 10-row synthetic customer-ticket CSVs and two demo accounts with separate dataset access.
2. Use server-issued demo sessions; protected endpoints derive account from the token.
3. List only accessible dataset metadata.
4. Support feedback_summary through demo_receiver. Other purposes/destinations are blocked.
5. Select message only on the backend; redact supported email/phone spans inside it.
6. Show the exact canonical receiver payload, locked mandatory actions and preview hash/revision.
7. Support simple additional whole-message hiding under the contract.
8. Approve-and-Send checks current access, source hash/revision, current policy/fingerprint and reviewed payload. Reject stale approvals.
9. Atomically claim dispatch so duplicate/concurrent Send invokes the sole adapter at most once.
10. A real local capturing adapter receives the prepared bytes and returns a clearly labeled local acknowledgement. Do not pretend it is AI-generated.
11. Persist an ordinary metadata-only receipt with actual mode, attempts and outcome.
12. Provide the local revoke/grant demonstration helper described in API_CONTRACT.md.

Create README startup instructions, dependency manifests/lockfiles, .gitignore and placeholder .env.example as needed. Use one FastAPI worker and document restart/expired-draft behavior.

Keep policy, transformations, storage, request workflow and the receiver adapter in understandable modules. Separate frontend API/types from review/outcome components. Document the actual module map and extension points so later assistants can own distinct files; avoid a giant application file or a generic plugin framework.

Required verification:
- Allowed request receives exactly the approved canonical payload once.
- Cross-account dataset/draft/review/receipt access fails.
- Prohibited purpose/destination/sharing makes zero adapter calls.
- Mandatory redaction cannot be reversed by body tampering.
- Preview then revoke then Send makes zero calls.
- Changed source/policy/review invalidates previous approval.
- Repeated/concurrent Send does not call again.
- Receiver failure is reported honestly.
- Receipts contain no raw customer data/full prompts/tokens.
- Backend tests pass and frontend build passes.
- Smoke-test the UI if a browser tool is available; otherwise report that limitation.

Use isolated test storage. Inspect installed runtimes and use compatible dependencies. All receiver calls must pass through the one adapter. Never put model keys or raw runtime payload captures in Git.

Do not implement NER, external providers, hash chains, uploads, vector search, custom training, production authentication, deployment, or another product in this task. Do not add a second scaffold. Do not autonomously message other chats.

If no Git remote is configured, finish locally and report it rather than inventing a URL. Work under the human's configured Git workflow. Record actual implementation/verification state in README.md and TEAM_WORKFLOW.md.

At completion, hand off:
- What works.
- Changed files.
- Actual module map and safe extension points for later layers.
- Actual test/build commands and results.
- Exact startup and demonstration steps.
- Remaining limits/bugs.
- Branch/commit if available.
- A suggested next bounded layer.

Stop after this baseline handoff. Other team assistants will add layers after acceptance.

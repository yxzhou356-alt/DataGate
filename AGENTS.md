# DataGate instructions for coding assistants

Read PROJECT_CONTEXT.md, API_CONTRACT.md, TEAM_WORKFLOW.md and the human's bounded assignment first. System/developer/human directions take precedence. API_CONTRACT owns wire formats; PROJECT_CONTEXT owns scope; older guides/roadmaps are historical navigation.

## Current state

Teammate baseline `21f5abc` on GitHub `base-line` was reviewed and extended on `codex/six-governance-features`, per Priyanka's explicit assignment of all six features. Preserve this existing React/TypeScript/Vite + FastAPI/SQLite application. README and FEATURE_HANDOFF record actual checks and limits. Human teammate acceptance is still separate from automated verification.

Team: Priyanka, Ishita, Yuxin, Aishwarya. Priyanka requested this integration; future human work assignments are unassigned. Use separate clones/worktrees for simultaneous assistants. Claim bounded files with the team coordinator; coordinate schemas/routes/dependencies/database/startup changes. Do not independently re-scaffold or switch branches in a shared checkout. Coordinate via Git and the human team; do not autonomously message other chats.

## Required invariants

- Identity derives from the issued demo token; selection is simulated authentication, not production login.
- Owner rules win. No-sharing blocks even redacted data. Only backend-held synthetic sources are used.
- Check dataset access before source preview, on review, and immediately before dispatch. Raw-message display requires a separate raw grant too. No excluded columns in raw comparison.
- Minimize fields on backend before scanning. Unsupported required detectors/templates fail closed. Required PERSON model failures block.
- Manual selections use original Unicode code-point positions; validate, deduplicate and union coverage. Mandatory findings cannot be undone. Never accept browser replacement payloads.
- Bind review to account, dataset/source revision+hash, policy/raw-grant version+fingerprint, detector/model/transform fingerprint, purpose/destination, review revision and canonical payload hash.
- Atomically claim ready->sending before the sole receiver adapter call. No automatic retries. Local checks do not establish distributed atomic revocation.
- Creator-only history/receipt/timeline/audit, including metadata access after source revocation. Never use that to expose source content.
- DB/audit/export/test reports contain metadata, not raw values, complete messages/prompts, mapping tables or credentials. Receiver captures/runtime DBs stay ignored.
- Dashboard reads real recorded test evidence and marks changed code stale. No test-running HTTP endpoint or fabricated metrics.
- NER is a local pretrained English model with measured misses/false positives; pseudonyms are linkable and are not anonymization. Analyst approval is not customer consent.

## Verification/handoff

Use backend/.venv. Run meaningful isolated backend tests, frontend lint/build, and documented UI smoke checks when browser tooling is available. `python -m app.security_report` writes sanitized real results; NER evaluation has a separate labeled corpus/report. Report exact commands/results, changed files, branch/commit, startup instructions, schema changes and limits. Do not claim planned or unrun checks pass.

## Scope remaining deferred

The human explicitly authorized the six review/dashboard/audit/pseudonym/explanation/NER features. No real external AI provider, enterprise login, editable admin UI, generic uploads, hash chains, vector search, custom training or deployment infrastructure has been assigned. Local receiver acknowledgements are not generated AI analysis. Ordinary audit storage is not tamperproof.

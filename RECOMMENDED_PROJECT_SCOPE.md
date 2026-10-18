# DataGate — current scope summary

This summary has been updated for the team's baseline-first decision. All task assignments are UNASSIGNED. No baseline application is present merely because these documents exist.

## Authoritative handoff

Read AGENTS.md, PROJECT_CONTEXT.md, API_CONTRACT.md and TEAM_WORKFLOW.md. Use prompts/BASELINE_AGENT_PROMPT.md for the first implementation.

## Product

Permission, review, and evidence before data reaches AI.

User: a support analyst requesting a summary of customer complaints.
Owner: company dataset owner/admin who preconfigures access and sharing rules.
DataGate: backend-controlled access, purpose/destination policy, message-only field selection, supported redaction, exact review, Send-time recheck and receipt.

Original source data stays on the backend. The receiver gets only approved transformed content.

## Baseline

- React + TypeScript + Vite.
- FastAPI/Pydantic + Python sqlite3.
- Two synthetic backend datasets and two demo analyst identities.
- One purpose, feedback_summary.
- One destination, demo_receiver.
- Email/phone rules and simple additional whole-message hiding.
- Local capturing adapter with truthful local acknowledgement.
- Ordinary metadata receipts.
- Meaningful allowed/denied/stale/duplicate/failure tests.

No external API key required. No actual model training in baseline. Identity selection is a local demo, not production authentication.

## Combination

Use DataGate's policy workflow, Bouncer's constrained review, AccessCheck-inspired authorization tests, and basic data validity checks. Do not add the complete BatchGuard model-impact, banking lineage or invoice-matching products.

Owner restrictions prevail over requester choices. A no-sharing policy cannot be bypassed by redaction. Preview approval is bound to the actual account/source/policy/review/payload and checked at Send.

## Layers after acceptance

UX, broader regression evidence, quality diagnostics, one real provider, optional pretrained NER/evaluation, optional chained receipts. Choose bounded tasks from TEAM_WORKFLOW.md; do not build all optional layers automatically.

## Claims

Describe implemented coverage and measured tests. User review is not verified legal consent. Detection is incomplete. Hashes/receipts do not guarantee privacy, immutable history or recipient behavior.

The GoCalma reference already demonstrates interactive redaction/audit features; do not claim those alone are unique. The project focus is the enforced, inspectable decision path.

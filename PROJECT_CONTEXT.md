# DataGate — authoritative project context

Status: teammate baseline `base-line`/`21f5abc` reviewed and extended in `codex/six-governance-features` under Priyanka's explicit six-feature assignment. This document owns scope; API_CONTRACT owns interfaces. Earlier planning guides are historical. Human acceptance on a second laptop remains to be recorded.

## Team and purpose

Priyanka, Ishita, Yuxin and Aishwarya are USC MSCS students building their first hackathon project. The aim is a sensible company workflow, useful engineering experience and an honest portfolio demo. The team's event packet names the AI Data Governance track at USC ACM TrojanHacks. No hiring or winning outcome is promised.

Problem: a support analyst wants an AI service to summarize complaints. The source contains identifying information and irrelevant business fields. A company needs to decide who may use it, for which purpose and destination, minimize what leaves, let the requester hide more, check again before dispatch, and retain inspectable evidence.

The analyst uses the DataGate UI. The backend has the synthetic source CSVs and owner policies. The receiving service has no direct spreadsheet/database access. This prototype governs its own gateway path, not all employee traffic or recipient behavior.

## Existing app and the assigned six layers

Preserve React + TypeScript + Vite, Python FastAPI/Pydantic, sqlite3, standard CSV/regex/JSON/SHA-256 and pytest. Added local spaCy `en_core_web_sm` PERSON inference; no training/vector database. No external AI receiver/API key is part of this assignment.

1. Interactive review: separate raw-message authorization, source/outbound comparison, highlighted detections, optional manual source spans and whole-message hiding, locked mandatory redactions.
2. Security dashboard: actual recorded isolated pytest evidence, six control groups, source fingerprints and stale/missing state. No HTTP test runner or invented zero-call count.
3. Creator-scoped history, real metadata events, filters and JSON audit export, including operator permission changes. No raw values/mapping in events or receipts.
4. Request-scoped stable pseudonyms for equal detected name surfaces. Baseline EMAIL/PHONE generic markers remain. Names are case-folded/whitespace-normalized, not aliases resolved.
5. Explanations from actual field-minimization policy, mandatory redaction counts and additional hiding choices.
6. Local pretrained English PERSON detector, explicit missing/inference failure handling and a held-out hand-labeled synthetic evaluation.

## Demo data, access and owner configuration

- analyst_a / MapleCo may process feedback_a; fresh seed also grants raw retained-message review.
- analyst_b / RiverCo may process feedback_b; raw original text is not authorized by default.
- Each dataset starts with10 synthetic rows. Fields: ticket_id, customer_name, email, phone, plan_tier, account_value, product_area, message.
- Implemented purpose feedback_summary requires message only; destination demo_receiver. model_training/public_chatbot are blocked demonstrations, not implemented operations.
- Fresh policies require EMAIL, PHONE and PERSON; unsupported mandatory detectors/templates fail closed. sharing_mode none blocks even transformed data; redacted_only permits only the configured pipeline, without promising anonymity.

Owner setup is backend seed plus local demo_control CLI. There is no analyst grant-edit route or owner admin website. Demo token selection is simulated authentication: anyone running the local demo can select either account. Protected operations derive identity from the backend-issued token, not caller role/user fields.

Raw-message grants are distinct from processing access and require it. Only message originals may be returned; dropped columns remain backend-held. A transformed-only analyst can hide whole messages, but cannot submit source-offset manual selections. Existing runtime grants/policies are preserved by migration, not silently expanded; see README upgrade commands.

## Authoritative flow and binding

1. Authenticate demo session; list authorized dataset metadata.
2. On preview, check access, purpose/destination/sharing and supported processing. Strictly parse UTF-8 CSV; reject missing/nonempty required columns, malformed quoting and ragged rows without echoing values.
3. Minimize fields first, then detect EMAIL/PHONE/PERSON in retained messages. Resolve overlaps without losing mandatory coverage. Equal detected names receive request-scoped tokens before optional hiding.
4. Return canonical outbound payload/hash, findings and explanations. Include original messages only with separate current raw access.
5. Review validates complete optional source spans and message hides, reconstructs on backend, increments revision/hash. It cannot accept arbitrary outgoing text or unredact owner rules.
6. Send checks creator/current access, current source revision/hash, full policy/raw-grant version/fingerprint, detector/model/transformation fingerprint, review revision and canonical payload hash.
7. A conditional atomic ready->sending claim permits only one adapter invocation. No automatic retries.
8. Local receiver captures exactly the approved bytes in memory and acknowledges them, explicitly stating no external AI model was called.
9. Metadata transitions/events/receipt are recorded. The creator can read metadata after dataset revocation, without renewed source-preview access.

Policy is reread on protected steps, not startup cached. Changed content/policy/model requires a new preview. Required detector failures block with no dispatch. Owner changes and request events use actual transactions; older baseline rows have no fabricated event history.

## Evidence and limits

Tests use isolated temporary databases/sources and inspect the capturing adapter, including allowed and blocked cases, tampering, revocation, source/policy/model staleness, duplicate/concurrent Send and metadata privacy. The dashboard records actual statuses/times and sanitized test IDs; it does not stream model traffic. Reports are local editable artifacts, not signed attestations.

The held-out synthetic corpus has40 examples/25 PERSON gold spans. The recorded English model run gives PERSON precision87.5%, recall84% (exact span/category). It can miss names or redact product terms/Spanish words. The sample is small; no broad detection/privacy claim follows. Addresses, arbitrary secrets, multilingual coverage and entity alias resolution are outside scope.

Pseudonyms are linkable within a request, not anonymous identities. Analyst approval is not verified customer consent. Metadata hashes/logs do not establish regulatory compliance or tamperproof storage. Local revocation checks cannot retract content already viewed/sent and are not distributed atomic cancellation.

## Remaining work and collaboration

Follow TEAM_WORKFLOW, README and FEATURE_HANDOFF for the branch, actual verification and clean setup. Another teammate should reproduce the demo before merging/submitting. Human future assignments are not preselected. Each assistant needs a bounded task and separate clone/worktree.

Deferred unless explicitly assigned: real provider, enterprise login, editable admin UI, uploads, hash-chain receipts, RAG/vector search, full BatchGuard scoring, banking lineage, custom training and deployment infrastructure. All real provider calls, if later assigned, must use the existing sole receiver adapter boundary.

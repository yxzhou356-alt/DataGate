# Six-feature implementation handoff

Assigned by Priyanka: review teammate baseline from GitHub `base-line`, implement all six proposed features, and push a separate branch. Baseline: `21f5abcb69a5962c84335559bf723f18b74e6b17`. Integration branch: `codex/six-governance-features`. See Git history for ending commits; do not use the older parent-directory prototype as this branch's app.

## Baseline review and fixes

The original teammate baseline passed all43 supplied backend tests before modification. Core token-derived authorization, field minimization, creator isolation, send-time checks, canonical hash matching and single-dispatch conditional update were sound in those scenarios.

Three reproduced gaps were fixed:

1. Unknown mandatory detector types were silently skipped. Unsupported policy processing now records a blocked result without dispatch; missing/failing required PERSON inference produces503 and a blocked metadata receipt.
2. A configured but unimplemented purpose/template could raise500. Supported operations/field templates are now checked before preparing data.
3. An unterminated quoted CSV field could be accepted. Strict CSV parsing now rejects malformed quoting with a metadata-only validation error.

Extension review also found/fixed partial overlap between a PERSON detection and an EMAIL/PHONE span: resolution now preserves the union of mandatory coverage. Added a current authorization/source/policy/model recheck after expensive payload rebuilding, immediately before the dispatch claim. A regression revokes permission during rebuilding and proves zero receiver invocations.

Frontend fixes: changed form choices invalidate the old preview; dismissing stale notices cannot unlock it; async responses cannot cross account switches; ambiguous network delivery locks the old draft and reads any receipt instead of enabling a retry.

## All six delivered

| Layer | Implemented behavior | Main files |
| --- | --- | --- |
| Interactive redaction review | Authorized originals/outbound comparison, source highlights, selectable manual spans, remove optional spans, whole-message hiding, mandatory locked findings | frontend/components/MessageComparison, ManifestReview; backend transform/schemas/workflow |
| Security test dashboard | CLI-recorded actual isolated pytest results, control groups, provenance/fingerprint, stale/missing state, metadata export, GET-only refresh | backend/app/security_report.py; frontend/components/GovernanceTests.tsx |
| Audit/receipt timeline | Creator-only history/filter/search, transaction-recorded request events, local operator changes, JSON export; readable after dataset revocation | storage/workflow/demo_control/main; AuditHistory/AuditDetail |
| Pseudonymization | Same detected normalized name surface uses same request-scoped PERSON token before optional hides; mappings remain ephemeral | transform/detection; comparison placeholders |
| Policy explanation | Included/excluded fields, rule IDs, mandatory counts and additional hiding explained from backend decisions | workflow; PolicyExplanation |
| Name detector/evaluation | Local pretrained English spaCy model, fail-closed required processing,56 manually labeled synthetic examples (16dev/40heldout) and exact-span metrics | detection; evaluation; detector tests |

The table's frontend paths are under `frontend/src/`. Shared routes/types/schemas were updated together; the existing receiver payload/receipt remain v1-compatible. API_CONTRACT section12 defines additions. The source originals are an explicit privileged review feature, not an expansion of ordinary processing access.

## Actual verification

Commands run from the isolated clone using its Python3.12.10 backend virtual environment and Node24.19.0/npm10.9.4:

- Before changes: `../../.venv/bin/python -m pytest -q` from backend, using the earlier environment: **43 passed**.
- After changes: `backend/.venv/bin/python -m pytest -q backend/tests` from repository root; subsequent complete CLI run below includes final added regressions.
- From backend: `.venv/bin/python -m app.security_report --output reports/security-report.json`: **87 passed,0 failed,0 skipped**, all six control groups passed. The report stores its actual duration, source fingerprint, git revision and dirty flag. It contains no stdout/assertion data or parameterized input values.
- From frontend: `npm run lint` and `npm run build` using the local npm CLI: **both exit0**; final build43 modules, JS265.17kB before gzip. No frontend dependency additions.
- Detector: `.venv/bin/python -m pytest -q tests/test_detection.py`: **16 passed**, including real installed-model recognition.
- From backend: `.venv/bin/python -m evaluation.run --split heldout --output evaluation/heldout-results.json`: actual40-example run. PERSON21TP/3FP/4FN: **precision87.5%, recall84%, F1≈0.8571**. Rules-only PERSON recall0. See evaluation README/report for all metrics/errors/model/corpus hashes.
- Four frontend utility assertions checked emoji/UTF-16 boundaries, split-surrogate rejection, accents/newlines and CRLF mapping. These were direct assertions, not a claim of complete frontend test coverage.
- `git diff --check`: clean.

Backend tests create temporary isolated databases/source copies. Security integration tests use a clearly labeled deterministic name-model double for authorization scenarios; detector tests and heldout evaluation use the actual pretrained model. No tests call an external AI model.

## Browser verification

Ran the actual new application on backend8001/frontend5174, with separate ignored storage at backend/var/browser-check. Tested in the Codex in-app browser:

- MapleCo login and authorized preview; actual source/outgoing comparison, name/email/phone highlights and field explanation table.
- A mouse-selected manual span was applied, review incremented1→2, hash changed, and required PERSON/EMAIL remained hidden. Approved Send succeeded with1 actual local adapter call and matching prepared/sent hashes.
- Opened creator history/timeline; actual ordered preview/review/send_claimed/send events displayed. Downloaded the audit JSON and parsed it: expected events/status/call count and no tested raw names/email or original/payload keys.
- Dashboard displayed87/87, six passed controls and matching current/report fingerprints. It also correctly showed a stale report after frontend source changed, clearing after regeneration/refresh.
- RiverCo preview showed transformed content with no original-source labels/manual source editor. Whole-message hiding remained available.
- Revoked RiverCo access after its preview, then clicked Send: the UI showed a blocked receipt, policy1→2, no confirmed hash, and0 actual calls. Restored the isolated demo grant afterward.
- Desktop1440×1000 and narrow/default layouts were inspected; responsive columns stack on narrow screens. Screenshot evidence is in docs/screenshots.

Automated tests additionally verify raw-grant removal, revoked Send, forbidden purposes/destinations, malformed CSV, unknown detectors/templates, manual bounds and source changes, overlaps, inference failure, creator-only export and duplicate/concurrent sends. Human teammate acceptance and Safari/Firefox testing remain pending.

## Setup, migrations and handoff

Follow README exactly: backend virtualenv + `pip install -r requirements.txt`, frontend `npm ci`, one backend worker, `python -m app.security_report`, then backend8000/frontend5173 defaults. The pinned local model installs during setup; runtime requests never download it. No API key is required.

New storage: raw_grants, audit_events, request manual_spans/pipeline_fingerprint. Startup additively migrates old runtime schema without replacing owner data. Existing old policies do not gain PERSON or raw access automatically: README documents explicit owner CLI require-person/raw-grant. Fresh seeds already configure both. Old drafts require a new preview. Resetting the local demo is optional and deletes its history.

Teammates should fetch this branch into separate clones/worktrees, install dependencies, reproduce the demo and review the diff before merging. Future feature ownership is unassigned; agree on bounded tasks with the human coordinator.

Known limits: demo authentication; local receiver only; English NER misses/false positives (including Spanish/product terms); name-surface matching rather than alias resolution; pseudonyms are linkable; history capped at latest200 matching rows; current-user-only user filter; ordinary editable local audit/report storage; no distributed atomic revocation or recall of prior content; analyst approval is not customer consent. These limits are visible in README/UI where relevant.

Suggested next priority: a second laptop run plus four-minute demo/backup recording. Only then consider a separately assigned real provider through the existing adapter or production identity/owner administration. Avoid expanding scope before that acceptance.

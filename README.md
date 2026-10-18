# DataGate

Permission, review, and evidence before data reaches AI.

A four-person USC TrojanHacks project for Priyanka, Ishita, Yuxin and Aishwarya. Implementation roles beyond the baseline are UNASSIGNED.

A support analyst wants AI to summarize customer complaints. DataGate controls who may use each dataset, for what purpose and destination, exactly what content leaves, and whether permission still holds at the moment of sending. The receiver gets only the approved, transformed messages, never the spreadsheet.

## Current state

**Baseline v1 is implemented locally; the existing checks pass** (October 17, 2026). Independent review found a malformed-CSV validation gap, and second-teammate acceptance is still pending. This checkout tracks `origin/feature` at candidate `21f5abc`; current UX changes are uncommitted. See [baseline/UX review](BASELINE_UX_REVIEW.md) and [TEAM_WORKFLOW.md](TEAM_WORKFLOW.md).

What works today, end to end through the UI and the API:

- Demo sign-in for two seeded analysts (`analyst_a` → MapleCo, `analyst_b` → RiverCo). Identity always comes from the server-issued token.
- Each analyst sees only their own dataset and its owner policy (the "passport").
- Preview builds the exact receiver payload on the backend: message column only, embedded emails and phone numbers replaced with `[EMAIL]` / `[PHONE]`, plus the SHA-256 preview hash.
- Review: the analyst can hide whole messages (`[HIDDEN_BY_USER]`). Every change bumps the review revision and hash. Mandatory redaction cannot be reversed.
- Approve & send rechecks access, source bytes and revision, policy version and fingerprint, review revision and payload hash. Then it atomically claims dispatch and calls the local receiver exactly once.
- Forbidden purpose (`model_training`), destination (`public_chatbot`) or `sharing_mode=none` are blocked with zero receiver calls.
- Revoking access after a preview blocks Send. Changed source or policy marks the draft stale.
- A metadata-only receipt (no message text, names or tokens) is available for blocked, sent and failed requests.

The receiver is a **local capturing test endpoint**. No external AI model is called and no API key is needed.

## Requirements

Versions this was built and verified with:

- Python 3.13 (3.11+ should work)
- Node.js 22 with npm 10
- Pinned backend dependencies: `backend/requirements.txt` (full freeze in `backend/requirements.lock`). Frontend: `frontend/package-lock.json`.

## Run it

Two terminals, from the repository root.

**Backend** (http://127.0.0.1:8000, one worker):

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

On first start the backend seeds `backend/var/` (git-ignored): the SQLite DB and runtime copies of the two fixture CSVs. Committed fixtures in `backend/fixtures/` are never modified. API docs: http://127.0.0.1:8000/api/docs.

**Frontend** (http://127.0.0.1:5173):

```bash
cd frontend
npm install
npm run dev
```

Vite proxies `/api` to the backend, so open http://127.0.0.1:5173.

Sessions and their tokens live in memory, so after a backend restart the UI will ask you to pick an account again. Drafts are rebuilt from the source on every step; an old draft still works only if nothing changed.

## Verify

```bash
cd backend && .venv/bin/python -m pytest -q      # 43 passed
cd frontend && npm run lint && npm run build     # clean lint, build OK
```

Tests use a fresh temporary DB and source copies per test. They never touch `backend/var/`.

Latest review: 43 tests passed, lint/build passed, and Chrome UI checks covered preview, extra hiding, approved local send, readable receipts, blocked purpose and 390px layout. The existing tests do not catch an unclosed CSV quote merging records; see B1 in [the review](BASELINE_UX_REVIEW.md). This remains a baseline validation issue, not a passing claim.

## Demo script (≈4 minutes)

Keep a third terminal in `backend/` with the venv active for the owner controls.

1. **Choose.** Open the UI and pick *MapleCo analyst*. Only MapleCo feedback is listed, with its owner rules.
2. **Review.** Click *Prepare preview*.
   - Seven columns are removed.
   - Two emails and two phone numbers inside messages are shown as solid redaction bars.
   - Expand *Technical verification details* to inspect the content fingerprint if needed.
3. **Hide.** Hide one message. The review revision goes from 1 to 2 and the hash changes.
4. **Send.** Tick the approval and click *Approve and send*. You get a green *Sent* stamp, the local receiver's acknowledgement ("no external AI model was called") and a receipt where the confirmed hash equals the prepared hash.
5. **Revoke mid-flight.** Click *Start a new request*, then *Prepare preview*. Before sending, run:
   ```bash
   python -m app.demo_control revoke --account analyst_a --dataset feedback_a
   ```
   Then click *Approve and send*. Result: *Blocked*, "access was revoked before sending", receiver calls 0. Restore access with `python -m app.demo_control grant --account analyst_a --dataset feedback_a`.
6. **Stale policy.** Prepare a preview, run `python -m app.demo_control bump-policy --dataset feedback_a`, then send. You'll see "The owner policy changed after the preview" and nothing is sent.
7. **Forbidden use.** Under *What do you want to do?*, choose *Train a model on this data* and prepare a preview. It is blocked immediately with no preview and zero calls. Changing a form choice clears any prior preview/approval.

Other owner controls:
- `python -m app.demo_control sharing --dataset feedback_a --mode none` (then `--mode redacted_only` to restore)
- `python -m app.demo_control edit-source --dataset feedback_a` (appends a synthetic row and bumps the dataset revision)
- `python -m app.demo_control status`

Failure demo: start the backend with `DATAGATE_RECEIVER=fail`. Send then returns *Not confirmed*, with 1 receiver call recorded and no confirmed hash.

Reset the demo data at any time: stop the backend, then run `python -m app.seed --reset`.

## Module map and extension points

```
backend/
  app/
    config.py        Settings (data dir, receiver mode). Env: DATAGATE_DATA_DIR, DATAGATE_RECEIVER
    errors.py        Error codes + envelope; validation errors never echo input
    storage.py       SQLite schema and access (accounts, datasets, policies, grants, requests)
    seed.py          Owner setup: accounts, datasets, default policy; `python -m app.seed [--reset]`
    policy.py        evaluate() access/purpose/destination/sharing; fingerprint()
    transform.py     CSV read+validate, field minimization, EMAIL/PHONE redaction, canonical payload+hash
    receiver.py      ReceiverAdapter protocol; LocalCapturingReceiver; FailingReceiver; build_receiver()
    workflow.py      preview / review / send / receipt state machine and send-time rechecks
    auth.py          Demo sessions (in-memory tokens) + current_account dependency
    schemas.py       Request bodies (extra fields rejected)
    main.py          create_app(): routes only, thin layer over Workflow
    demo_control.py  Owner CLI: revoke, grant, sharing, bump-policy, edit-source, status
  fixtures/          Two synthetic 10-row CSVs (committed, never mutated)
  tests/             test_flow.py, test_send_safety.py, test_transform.py, conftest.py
frontend/src/
  api.ts, types.ts   API client and wire types (mirror API_CONTRACT.md)
  labels.ts          Human-readable labels for purposes, destinations, decisions
  App.tsx            App state and flow orchestration
  components/        AccountGate, RequestForm, ManifestReview, ApprovalPanel, OutcomePanel
  index.css          Design tokens and styles
```

Where later layers plug in (see the backlog in TEAM_WORKFLOW.md):

- **L4 real provider:** implement `ReceiverAdapter.send(request_id, payload_bytes)` in `receiver.py` and select it in `build_receiver()`. `workflow.Workflow.send` is the only caller; keep it that way.
- **L5 name detection:** add a pattern or detector to `transform.redact()` and `PATTERNS`, plus a policy redaction type. This changes previews and hashes, so coordinate the contract.
- **L3 input quality:** extend `transform.read_source()` validation (duplicate `ticket_id`, row-level errors).
- **L6 receipt integrity:** derive chained receipts from the `requests` rows in `storage.py` and `Workflow.receipt()`.
- **L1 UX:** components only; the API surface is `api.ts`.
- **L2 regression evidence:** add tests beside `tests/test_send_safety.py`, using the `conftest.py` fixtures (isolated store plus capturing receiver).

## Implementation choices worth knowing

- **No payload text in the DB.** A draft stores only choices (dataset, hidden indices) plus hashes and versions. The payload is rebuilt from the current source on every preview, review and send, and the send compares the rebuilt hash with the approved one.
- **Atomic dispatch claim.** A conditional `UPDATE … WHERE status='ready' AND review_revision=? AND preview_hash=?` decides which Send wins. Losers get `409 ALREADY_DISPATCHED`. A test fires 6 concurrent sends and checks there is exactly 1 receiver call.
- **Policy fingerprint** covers every policy field, including the allowed-account list. Editing the DB directly without a version bump still invalidates approvals.
- **Revocation and owner-policy denials checked at send** are recorded as `blocked` with the receipt's `policy_version` reflecting the decision-time policy. Still-permitted changes are recorded as `stale`.
- **Review** sends the complete set of hidden indices each time (sorted and deduplicated). Sending `[]` includes everything again; mandatory redaction is unaffected either way.

## Known limits

- Demo sign-in is simulated authentication, not production login. Anyone running the app can pick either account.
- Detection covers emails and North-American 10-digit phone formats only. Names, addresses, health details and other secrets inside messages are **not** detected. The synthetic fixture messages deliberately contain no names.
- CSV validation currently accepts an unclosed quoted field and may merge later records. This needs a bounded backend fix before claiming the no-silent-repair requirement is fully met; see B1 in [the review](BASELINE_UX_REVIEW.md).
- Analyst approval is not customer consent. Receipts and hashes are evidence of this gateway's actions, not proof of privacy or recipient behavior.
- Revocation applies at the next protected step. It cannot recall content already sent, and it isn't distributed or atomic across services.
- The UI loads Public Sans and JetBrains Mono from Google Fonts and falls back to system fonts offline.
- Verified in headless Chromium (desktop 1440px and phone 390px). Not tested in Safari or Firefox, or by a second teammate yet.

## Project documents

1. [Repository instructions](AGENTS.md)
2. [Project context and scope](PROJECT_CONTEXT.md)
3. [Frozen v1 API contract](API_CONTRACT.md)
4. [Baseline-first collaboration workflow](TEAM_WORKFLOW.md)
5. [Implementation guide](IMPLEMENTATION_GUIDE.md) and [team roadmap](TROJANHACKS_TEAM_ROADMAP.md)
6. Prompts: [layer addition](prompts/LAYER_AGENT_PROMPT.md), [review/debug](prompts/REVIEW_OR_DEBUG_PROMPT.md), [baseline (done)](prompts/BASELINE_AGENT_PROMPT.md)
7. [Mentor brief](MENTOR_BRIEF_AND_TEAM_PLAN.md)

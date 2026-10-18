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
- Review: the analyst can hide whole messages (`[HIDDEN_BY_USER]`) and select parts of any message to redact (`[REDACTED_BY_USER]`, applied on the backend). Every change bumps the review revision and hash. Mandatory redaction cannot be reversed.
- Approve & send rechecks access, source bytes and revision, policy version and fingerprint, review revision and payload hash. Then it atomically claims dispatch and calls the local receiver exactly once.
- Forbidden purpose (`model_training`), destination (`public_chatbot`) or `sharing_mode=none` are blocked with zero receiver calls.
- Revoking access after a preview blocks Send. Changed source or policy marks the draft stale.
- A metadata-only receipt (no message text, names or tokens) is available for blocked, sent and failed requests.
- *My history* (`#history`, after sign-in): a creator-only timeline of your own sent, blocked, out-of-date and unconfirmed requests (`GET /api/receipts`). It shows dataset, purpose, destination, outcome and redaction counts, and whether the receiver was not called, called without confirmation, or acknowledged. Technical details expand per entry. It stays readable after access is revoked; filter by outcome or source; older entries load in pages of 20.

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

While developing, add `--reload` to the uvicorn command, or restart the backend after pulling or editing backend code. Vite hot-reloads the frontend but not the backend, so a newer page talking to an older backend shows "Route not found" or "The request body is invalid". The history and evidence pages say "restart the backend" in that case.

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
cd backend && .venv/bin/python -m pytest -q      # 176 passed
cd frontend && npm run lint && npm run build     # clean lint, build OK
cd frontend && node --experimental-strip-types --test tests/*.test.ts   # 28 passed; display helpers, no extra deps
```

Tests use a fresh temporary DB and source copies per test. They never touch `backend/var/`: a conftest guard refuses the runtime data directory and points `DATAGATE_DATA_DIR` at throwaway storage, even if you exported it.

### Person names: local detection and numbered pseudonyms

An owner can require `PERSON` redaction. The default policies do not, and the committed fixtures contain no names. Demo setup:

```bash
cd backend
.venv/bin/python -m app.demo_control redactions --dataset feedback_a --types EMAIL,PHONE,PERSON --person-style numbered
.venv/bin/python -m app.demo_control add-named-row --dataset feedback_a   # appends one synthetic row that mentions people
```

The next preview turns `Ana asked Liam O'Brien … Liam O'Brien said Ana should email ana.souza@example.com; Dr. Patel will follow up with Ana.` into `[PERSON_1] asked [PERSON_2] … [PERSON_2] said [PERSON_1] should email [EMAIL]; Dr. [PERSON_3] will follow up with [PERSON_1].` Use `--person-style generic` for plain `[PERSON]`. The CLI refuses to drop EMAIL or PHONE.

How it works:
- **Detector:** `app/detectors.py`, local only, no new dependency. A versioned lexicon-and-context detector: committed given-name list (`app/data/person_given_names.txt`), honorifics, surname extension, organization guard. It sits behind a `PersonDetector` interface (typed spans with code-point offsets and confidence), so a pretrained local NER model can replace it later as a coordinated dependency change.
- **Precedence:** EMAIL > PHONE > PERSON. A PHONE match inside an email is ignored. PERSON spans are trimmed to exclude EMAIL/PHONE ranges, so no name fragment survives next to an address. Overlapping PERSON spans are merged. Every replacement is by offset, right to left, and each character is replaced at most once.
- **Numbering (`numbered` style):** decided on the backend in source order over all messages, before hiding, by normalized name (Unicode NFC, trimmed, whitespace collapsed, case-folded). Hiding a message never renumbers later people. The mapping exists only in memory while a payload is built, and is rebuilt identically at preview, review and send. It is never stored, logged, returned or put in receipts.
- **Token collisions:** placeholder-like strings already in the source (`[PERSON_1]`, `[EMAIL]`, …, any case) are rewritten to `(PERSON_1)` first, so square-bracket tokens in outbound text only ever come from DataGate.
- **Fail closed:** if a policy requires PERSON and the detector is missing, errors or returns invalid offsets, preview/review/send return `503 DETECTOR_UNAVAILABLE` and nothing is prepared or sent. Datasets without PERSON are unaffected. Demo: start the backend with `DATAGATE_PERSON_DETECTOR=unavailable`.
- **Freshness:** the draft stores the policy fingerprint (which includes `person_style`) plus a pipeline id (transformation version + detector version, which includes a hash of the lexicon). A change to either makes the approval stale (`POLICY_CHANGED` / `TRANSFORM_CHANGED`). A detector that returns different output on rebuild is caught by the payload-hash comparison (`PREVIEW_CHANGED`). Nothing best-effort is ever sent.

Evaluation (synthetic, limited):

```bash
cd backend && .venv/bin/python -m app.person_eval --show-errors
```

Actual result on the committed set (`backend/eval/person_eval.jsonl`: 70 synthetic messages, 63 gold spans), detector `lexicon-1.2`, run Oct 18, 2026:

| Match | Precision | Recall | F1 | tp / fp / fn |
| --- | --- | --- | --- | --- |
| Exact span | 0.980 | 0.778 | 0.867 | 49 / 1 / 14 |
| Overlap | 1.000 | 0.794 | 0.885 | 50 / 0 / 13 |

Misses are names absent from the lexicon (5 of 5 unseen names), non-Latin scripts, initials, a lowercase surname, an unknown particle name, and ambiguous names such as "Grace" or "Jordan" without a surname. The set was written by the same team as the detector, and one particle bug was fixed after seeing it, so treat it as a development set. These numbers describe this set only. They are not a real-world accuracy claim, and no result proves a message contains no personal data.

What pseudonymization does and does not do:
- It reduces exposure while keeping "who said what to whom" for summarization. It is not anonymization, not reversible, and not proof that all PII is gone.
- Two different people with the same name share a number.
- "Emma" and "Emma Lawson" get different numbers, and so do initials or nicknames. There is no coreference or alias resolution.
- Numbers are per request, derived from that source's order. There is no global person table, though the same unchanged source produces the same numbers.

### Security evidence dashboard

Generate the report. This runs the whole backend suite with temporary storage and injected test receivers:

```bash
cd backend && .venv/bin/python -m app.security_report
```

It writes `backend/var/reports/security-report.json` (git-ignored) atomically and prints the totals. Exit codes:
- 0: all 15 scenarios passed.
- 1: a scenario failed.
- 2: incomplete (a scenario was not run, or the run was interrupted or errored).
- 3: another generation is already running.
- 4: the report failed the prohibited-content check, so nothing was written.

Override the path with `--out` or `DATAGATE_REPORT_PATH`; the backend reads the same variable.

View it: start the backend and frontend as above, then open http://127.0.0.1:5173/#evidence. You can also use *View the security test evidence* on the sign-in page, or *Security evidence* in the top bar. The page reads `GET /api/evidence/security-report`. That endpoint only reads the file: it never runs tests or touches the demo DB.

What the dashboard shows:
- **Totals:** 15 scenarios (SEC-01 … SEC-15), each `passed`, `failed` or `not_run`. A scenario passes only if every test mapped to it with `@pytest.mark.scenario("SEC-xx")` ran and passed.
- **Labels:** *Missing*, *Unusable* (malformed, unsupported schema, or prohibited content), *Failed*, *Partial* (not run, interrupted or error), *Stale* (generated for another commit), *Commit unknown* (no Git), *Uncommitted changes* and *Demo DB changed*.
- **Run metadata:** generation time and commit, run status, test counts, isolation details, and whether the runtime demo DB was unchanged.

The report contains metadata only:
- **Not included:** messages, customer values, tokens, payloads or tracebacks.
- **Failure summaries:** test name, phase and exception class only.
- **Content check:** the report is scanned for email/phone-like values, credential-like text and fixture values before it is written, and again before it is served.

**Commit before generating** if you want a non-stale, clean report for the demo. A report generated on an older commit is labelled stale, not hidden.

Passing these fixture tests is evidence that the listed cases are implemented and behaved as described. It is not a universal security or privacy guarantee.

Latest review: 43 tests passed, lint/build passed, and Chrome UI checks covered preview, extra hiding, approved local send, readable receipts, blocked purpose and 390px layout. The existing tests do not catch an unclosed CSV quote merging records; see B1 in [the review](BASELINE_UX_REVIEW.md). This remains a baseline validation issue, not a passing claim.

## Demo script (≈4 minutes)

Keep a third terminal in `backend/` with the venv active for the owner controls.

1. **Choose.** Open the UI and pick *MapleCo analyst*. Only MapleCo feedback is listed, with its owner rules.
2. **Review.** Click *Prepare preview*.
   - Seven columns are removed.
   - Two emails and two phone numbers inside messages are shown as solid redaction bars.
   - Note the payload hash.
3. **Hide.** Each message is a review card showing its position, outbound text, locked owner-policy redactions and include/hide state. Click *Hide from send* on one card. The review revision goes from 1 to 2, and *Technical verification details* shows the new fingerprint plus the previous one, which is no longer approvable. *Restore redacted version* brings back only the server's redacted text.
   - **Redact part of a message.** Select words in any card (e.g. "charged twice") and choose *Redact selection*. The words become a hatched "you" marker, which you can click to undo. Selecting into an `[EMAIL]` marker expands to cover all of it. The receipt counts these as *Text redacted by you*.
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
- `python -m app.demo_control redactions --dataset feedback_a --types EMAIL,PHONE,PERSON [--person-style numbered]` and `add-named-row --dataset feedback_a` (see *Person names* above)
- `python -m app.demo_control status`

Failure demo: start the backend with `DATAGATE_RECEIVER=fail`. Send then returns *Not confirmed*, with 1 receiver call recorded and no confirmed hash.

Reset the demo data at any time: stop the backend, then run `python -m app.seed --reset`.

## Module map and extension points

```
backend/
  app/
    config.py        Settings (data dir, receiver mode, report path). Env: DATAGATE_DATA_DIR, DATAGATE_RECEIVER, DATAGATE_REPORT_PATH
    evidence.py      Security scenario catalogue, report validation, atomic write, prohibited-content scan
    security_report.py  `python -m app.security_report`: runs the suite, writes the evidence report
    errors.py        Error codes + envelope; validation errors never echo input
    storage.py       SQLite schema and access (accounts, datasets, policies, grants, requests)
    seed.py          Owner setup: accounts, datasets, default policy; `python -m app.seed [--reset]`
    policy.py        evaluate() access/purpose/destination/sharing; fingerprint()
    transform.py     CSV read+validate, field minimization, EMAIL/PHONE redaction, canonical payload+hash
    receiver.py      ReceiverAdapter protocol; LocalCapturingReceiver; FailingReceiver; build_receiver()
    workflow.py      preview / review / send / receipt state machine and send-time rechecks; list_receipts()
    timeline.py      Receipt timeline query validation (filters, limit) and opaque keyset cursors
    detectors.py     PersonDetector interface, validation/chunking, local LexiconPersonDetector (data/person_given_names.txt)
    person_eval.py   `python -m app.person_eval`: precision/recall/F1 on eval/person_eval.jsonl (synthetic)
    auth.py          Demo sessions (in-memory tokens) + current_account dependency
    schemas.py       Request bodies (extra fields rejected)
    main.py          create_app(): routes only, thin layer over Workflow
    demo_control.py  Owner CLI: revoke, grant, sharing, bump-policy, edit-source, status
  fixtures/          Two synthetic 10-row CSVs (committed, never mutated)
  tests/             test_flow.py, test_send_safety.py, test_transform.py, test_review_ux.py,
                     test_custom_redactions.py, test_evidence.py, test_receipt_timeline.py,
                     conftest.py (isolation guard, scenario marker)
frontend/src/
  api.ts, types.ts   API client and wire types (mirror API_CONTRACT.md)
  labels.ts          Human-readable labels for purposes, destinations, decisions
  redaction.ts       Display-only parsing of server placeholders; selection-to-offset helpers for custom redactions
  evidence.ts        Evidence verdicts and labels (missing/invalid/failed/partial/stale), derived from the report
  timeline.ts        Receipt timeline wording: receiver not called / not confirmed / acknowledged, redaction summary
  App.tsx            App state and flow orchestration
  components/        AccountGate, RequestForm, ManifestReview, ApprovalPanel, OutcomePanel, EvidenceDashboard, ReceiptTimeline
  index.css          Design tokens and styles
```

Where later layers plug in (see the backlog in TEAM_WORKFLOW.md):

- **L4 real provider:** implement `ReceiverAdapter.send(request_id, payload_bytes)` in `receiver.py` and select it in `build_receiver()`. `workflow.Workflow.send` is the only caller; keep it that way.
- **L5 name detection:** add a pattern or detector to `transform.redact()` and `PATTERNS`, plus a policy redaction type. This changes previews and hashes, so coordinate the contract.
- **L3 input quality:** extend `transform.read_source()` validation (duplicate `ticket_id`, row-level errors).
- **L6 receipt integrity:** derive chained receipts from the `requests` rows in `storage.py` and `Workflow.receipt()`.
- **L1 UX:** components only; the API surface is `api.ts`.
- **L2 regression evidence:** add tests beside `tests/test_send_safety.py`, using the `conftest.py` fixtures (isolated store plus capturing receiver). Tag them `@pytest.mark.scenario("SEC-xx")` to count toward a dashboard scenario. Add new scenarios to `SCENARIOS` in `app/evidence.py`. An unknown id marks the run as an error.

## Implementation choices worth knowing

- **No payload text in the DB.** A draft stores only choices (dataset, hidden indices) plus hashes and versions. The payload is rebuilt from the current source on every preview, review and send, and the send compares the rebuilt hash with the approved one.
- **Atomic dispatch claim.** A conditional `UPDATE … WHERE status='ready' AND review_revision=? AND preview_hash=?` decides which Send wins. Losers get `409 ALREADY_DISPATCHED`. A test fires 6 concurrent sends and checks there is exactly 1 receiver call.
- **Policy fingerprint** covers every policy field, including the allowed-account list. Editing the DB directly without a version bump still invalidates approvals.
- **Revocation and owner-policy denials checked at send** are recorded as `blocked` with the receipt's `policy_version` reflecting the decision-time policy. Still-permitted changes are recorded as `stale`.
- **Review** sends the complete set of hidden indices each time (sorted and deduplicated). Sending `[]` includes everything again; mandatory redaction is unaffected either way.
- **Custom redactions** are offsets (code points) into the mandatory-redacted text, stored in `requests.custom_redactions` (added automatically to older runtime DBs). The UI rebuilds each message from the server's base text plus spans and allows selection only when that reproduces the server's outbound text exactly.

## Known limits

- Demo sign-in is simulated authentication, not production login. Anyone running the app can pick either account.
- Detection covers emails and North-American 10-digit phone formats, plus person names when an owner requires PERSON. The name detector is lexicon-based: see its measured limits above. Addresses, health details and other secrets inside messages are **not** detected. The committed fixture messages contain no names; `add-named-row` appends synthetic ones for demos.
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

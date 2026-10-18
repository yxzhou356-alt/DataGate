# DataGate

Permission, review, and evidence before data reaches AI.

DataGate is a local USC TrojanHacks prototype for Priyanka, Ishita, Yuxin and Aishwarya. A support analyst chooses an authorized dataset and purpose, reviews a minimized payload, hides additional content, and approves delivery. The backend checks current permissions again and records metadata evidence.

This branch extends teammate baseline `21f5abc` on `base-line`; it preserves the React/TypeScript/Vite + FastAPI/SQLite application. See [FEATURE_HANDOFF.md](FEATURE_HANDOFF.md) for review findings, verification and collaboration steps.

**The receiver is local. No external AI model is called and no API key is needed.** Demo account selection simulates authentication; it is not production login.

## Six features

1. **Interactive review:** authorized original/outbound comparison, highlighted EMAIL/PHONE/PERSON findings, whole-message hiding and manual source selections. Owner-required redactions are locked; the browser never supplies replacement outgoing text.
2. **Security dashboard:** displays actual recorded pytest results, code fingerprints, run time and six control groups. Refresh reads results; it does not execute tests. Changed source marks old evidence stale.
3. **Audit history:** creator-only requests, filters, actual preview/review/permission-change/send/blocked events and metadata-only JSON export. No source messages, raw selections or identity mapping enters audit storage.
4. **Context-preserving pseudonyms:** repeated detected person-name surfaces use stable request-scoped `[PERSON_001]` tokens. EMAIL/PHONE retain `[EMAIL]` / `[PHONE]`. Name aliases are not resolved; pseudonyms do not establish anonymity.
5. **Policy explanations:** field inclusion/exclusion and required redactions explained from the applied rules and counts.
6. **Pretrained name detection:** local spaCy `en_core_web_sm`, with a hand-labeled synthetic evaluation. On 40 held-out examples: PERSON precision **87.5%**, recall **84%**. See [evaluation results and limits](backend/evaluation/README.md).

## Setup

Verified runtime: Python **3.12.10**, Node **24.19.0**, npm **10.9.4**. Dependencies and the 12.8 MB pretrained model install during setup, never during a preview. Backend versions are pinned in `requirements.txt`; `requirements.lock` records the actual environment. Frontend uses `package-lock.json`.

From repository root, backend terminal:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m app.security_report
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

Frontend terminal, starting from repository root:

```bash
cd frontend
npm ci
npm run dev
```

Open **http://127.0.0.1:5173**. API docs: http://127.0.0.1:8000/api/docs. Use one backend worker. Session tokens live in memory; select an account again after a restart.

First startup seeds two synthetic datasets into ignored `backend/var/`. Fresh MapleCo (`analyst_a`) has both processing and raw-message grants. RiverCo (`analyst_b`) has processing access only: it sees the transformed preview and can hide whole messages, but receives no original messages or source-position findings. Raw access is separately configured by the owner, and still requires dataset access. Only the retained `message` field can appear in the comparison; excluded columns never reach it.

Existing baseline runtime DBs are migrated additively. Owner policies/grants are not silently replaced. Old previews require regeneration. To enable PERSON and authorize raw review in an existing local demo:

```bash
python -m app.demo_control require-person --dataset feedback_a
python -m app.demo_control raw-grant --account analyst_a --dataset feedback_a
```

Use `require-person` for `feedback_b` too if it has an old policy. Fresh databases already require EMAIL, PHONE and PERSON for both datasets. To return to the seeded synthetic state, stop the backend and deliberately run `python -m app.seed --reset`; this deletes local demo history and runtime source edits.

## Verify

Run from `backend/` with the virtual environment active:

```bash
python -m pytest -q
python -m app.security_report
python -m evaluation.run --split heldout --output var/ner-evaluation.json
```

Run from `frontend/`:

```bash
npm run lint
npm run build
```

Tests use temporary databases/source copies. They do not mutate the live demo database. The dashboard reads `backend/var/security-report.json` first, with a committed metadata report as a fallback. It shows missing/stale evidence explicitly. Regenerate after changing code or dependencies; test evidence does not guarantee general security or detection coverage.

For a shareable sanitized report: `python -m app.security_report --output reports/security-report.json` from `backend/`. Do not commit JUnit failure output, runtime databases or receiver captures.

If default ports are occupied, backend `--port 8001` and frontend `DATAGATE_API_TARGET=http://127.0.0.1:8001 npm run dev -- --port 5174` work together through the Vite proxy.

## Four-minute demo

1. Choose **MapleCo analyst**, prepare feedback summary. Explain the seven excluded columns in the policy table.
2. Compare originals with outbound text. Repeated **Alice Jones** becomes the same pseudonym. EMAIL/PHONE/PERSON findings are locked. Select part of an original message and add a manual redaction; save the review. The revision/hash changes.
3. Approve and send. The local receiver acknowledges one call. Open History, inspect actual events and download the metadata-only JSON.
4. Prepare another preview, then use the owner terminal:
   ```bash
   python -m app.demo_control revoke --account analyst_a --dataset feedback_a
   ```
   Send now fails with zero receiver attempts. History includes the operator permission change and blocked decision. Restore with `grant` using the same arguments.
5. Open Security tests. Show actual run provenance and controls; explain that tests use isolated synthetic data. Show RiverCo's transformed-only review to demonstrate the separate raw permission.

Additional owner controls (backend terminal):

```bash
python -m app.demo_control raw-revoke --account analyst_a --dataset feedback_a
python -m app.demo_control bump-policy --dataset feedback_a
python -m app.demo_control sharing --dataset feedback_a --mode none
python -m app.demo_control sharing --dataset feedback_a --mode redacted_only
python -m app.demo_control edit-source --dataset feedback_a
python -m app.demo_control status
```

Owner CLI runs with local operator authority, not analyst authority. It records metadata changes in the same DB transaction. Revocation cannot erase a previously viewed preview or recall sent content. For receiver failure, start with `DATAGATE_RECEIVER=fail`; one attempted call and uncertain delivery are reported honestly.

## Boundaries and limits

- Backend derives identity from the issued token. Dataset/draft/review/send/receipt/audit ownership is enforced there.
- Source fields are minimized before scanning. Review binds account, dataset, source revision/hash, complete policy/raw grants, detector implementation/model, purpose/destination, revision and exact canonical payload hash.
- Manual spans use original Unicode code-point offsets, not UTF-16. The backend validates/rebuilds them and unions overlaps with mandatory spans. Requester choices only hide more.
- Atomic conditional dispatch prevents duplicate/concurrent Send from invoking the adapter twice. There are no automatic dispatch retries. Local pre-dispatch checks are not distributed atomic revocation.
- Model absence or inference failure blocks required PERSON processing. NER can miss names, confuse product terms/Spanish text with people, and over-redact. English-only model; no address, SSN, arbitrary-secret or global PII coverage claim.
- The original text can remain visible in an already-authorized browser after revocation until the next interaction. The server rejects subsequent protected operations. It cannot retract knowledge already received.
- Audit logs/reports are ordinary local SQLite/filesystem records, not tamperproof or hash-chained storage. A local operator can edit them.
- The UI's remote Google Fonts fall back to system fonts offline. No model or provider network requests occur during analysis.
- Analyst review is not verified customer consent. This prototype is not a compliance certification or production data-loss prevention service.

## Modules and team handoff

Backend modules: `policy.py` (owner rules), `transform.py` (strict CSV, minimization, findings, canonical payload), `detection.py` (local NER), `workflow.py` (state machine), `storage.py` (metadata/migration/events), `receiver.py` (single adapter boundary), `security_report.py` (isolated tests), `demo_control.py` (local owner changes).

Frontend: `App.tsx` orchestrates state; `api.ts`/`types.ts` mirror [API_CONTRACT.md](API_CONTRACT.md); `components/` contains comparison, policy, approval, history and security views. [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) owns scope; [TEAM_WORKFLOW.md](TEAM_WORKFLOW.md) records this assignment; [AGENTS.md](AGENTS.md) guides assistants.

Use a separate clone/worktree for each teammate and start from the shared feature branch. Do not have multiple assistants switch branches in one checkout. Agree on bounded files/tasks before further changes.

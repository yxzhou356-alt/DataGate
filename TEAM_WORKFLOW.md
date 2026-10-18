# DataGate — baseline-first team workflow

Team: Priyanka, Ishita, Yuxin, Aishwarya. Assignments are not decided.

## 1. Current state and owners

| Item | Current value |
| --- | --- |
| Baseline human/assistant owner | Aishwarya (requested the build) with Claude; team to confirm |
| Integration human/assistant owner | UNASSIGNED |
| Accepted baseline commit | NOT YET ACCEPTED; candidate `21f5abc` on local `feature` (tracks `origin/feature`) |
| Baseline status | IMPLEMENTED_LOCALLY: CSV validation finding B1 outstanding; second-person run and acceptance pending |
| Repository URL | Local checkout has origin tracking; remote availability/permissions not checked in this review |
| Application implementation | Present: backend/ (FastAPI) and frontend/ (React + Vite) |

Baseline verification as of Oct 17, 2026, ~7 p.m. PT: `pytest` 43 passed; `npm run lint` clean; `npm run build` OK; headless-Chromium smoke run of sent, hidden-message, revoked, stale-policy and blocked-purpose flows plus a 390px mobile layout check. Not yet run by a second teammate.

Oct 17 independent review/UX follow-up: existing 43 tests passed again, lint/build and whitespace check passed. Chrome verified preview, extra hiding, local send/receipt, form-change invalidation, blocked purpose and 390px layout. Found B1: an unclosed CSV quote is accepted and can merge records; backend was reviewed only and is unchanged. See [BASELINE_UX_REVIEW.md](BASELINE_UX_REVIEW.md) for evidence, scope, checks and handoff. This does not mark baseline acceptance complete.

Current bounded task: requested by the human in this chat, implemented by Codex on existing `feature` at base `21f5abc`; scope is frontend labels/components, their UX state/styles and review/handoff docs. Goal: remove unnecessary machine identifiers from the main flow while retaining inspectable verification, with the existing appearance. Status: REVIEW, uncommitted. No API, backend, schema, dependency or startup changes. The pre-existing package-lock edit is preserved. No other teammate work is assigned by this entry.

A human must claim ownership. Earlier suggested named assignments are not binding. Update this table after real progress, not in anticipation.

Oct 18 data task (explicit current human request / Codex, `feature` at base `418ec0e`): both fixtures have 18 customer reviews containing PII-like details. All message texts now express product/service opinions and customer pain points, rather than support requests or bare identifiers. Related PII categories are combined, conspicuous test labels are absent and the unwanted category remains removed. Ticket IDs and non-message columns, schema, detector/policy behavior, grants and receipts are unchanged. Runtime MapleCo has 19 reviews/revision 5 (the prior extra named row is also rewritten as a review); RiverCo has 18/revision 4. Chrome verified all review bodies fit within three text lines at desktop and 390px widths, with no horizontal overflow. No UI Send was performed. Checks: 176 backend tests passed in 2.56s; frontend build passed. Status: REVIEW, uncommitted. See [fixture coverage and handoff](backend/fixtures/README.md). Other ownership/acceptance is unchanged.

## 2. Phase A — one assistant builds the baseline

1. The group picks one member and their coding assistant as baseline owner.
2. Give that assistant AGENTS.md, PROJECT_CONTEXT.md, API_CONTRACT.md, this file, and prompts/BASELINE_AGENT_PROMPT.md.
3. That assistant builds one complete application and verifies it.
4. Other members/assistants read the same context, review the contract, prepare demo questions or inspect the finished baseline. They do not start competing scaffolds.
5. Baseline owner produces actual README startup instructions, manifests/lockfiles, tests and a handoff.
6. A second human runs the app from those instructions.
7. Share/push the accepted baseline and record its commit in this file.

The baseline owner is a useful integration-owner candidate afterward, but that assignment is also a human decision.

## 3. Phase B — bounded parallel layers/debugging

Each assistant starts from the same accepted baseline commit in a distinct clone or worktree. Four chats must not change branches in the same checkout.

The humans choose tasks and one coordinator records claims. Do not rely on unmerged branch-local ownership notes to coordinate everyone.

Before editing, fill:
- Task ID/title.
- Human owner and coding assistant.
- Base commit/branch.
- Goal and acceptance condition.
- Owned files.
- Shared files that require coordination.
- Checks to run.
- Status: available, claimed, in_progress, review, merged.

Use prompts/LAYER_AGENT_PROMPT.md for additions and prompts/REVIEW_OR_DEBUG_PROMPT.md for debugging/review.

## 4. Unassigned layer backlog

These are options, not instructions to implement all of them.

| ID | Workstream | Status | Completion condition |
| --- | --- | --- | --- |
| L1 | Review/UX polish | Bounded terminology/information-layer changes in REVIEW (current human request / Codex); wider work unassigned | Clear locked actions, extra message hiding, stale/error states, responsive layout; same API |
| L2 | Authorization/regression evidence | IMPLEMENTED on `feature` (human request, Oct 18; Claude): 14-scenario evidence report + `#evidence` dashboard; review pending | Broader isolated allowed/denied/revocation tests and factual result summary |
| L8 | Creator-only receipt timeline | IMPLEMENTED on `feature` (human request, Oct 18; Claude): `GET /api/receipts` + `#history` view; review pending | Creator-only, metadata-only, paginated; existing receipt route unchanged |
| L3 | Input quality | UNASSIGNED | Duplicate-ticket and clear row-level errors; no silent data removal |
| L4 | One real receiver/provider | UNASSIGNED | Only approved canonical content reaches assigned provider; honest failures; regression suite preserved |
| L5 | Person-name detector/evaluation | IMPLEMENTED on `feature` (human request, Oct 18; Claude): local lexicon detector behind a detector interface + synthetic labeled evaluation (no pretrained model; no new dependency); review pending | Local pretrained detector plus labeled baseline comparison; measured limitations |
| L10 | Structured PII rules | IMPLEMENTED on `feature` (human request, Oct 18; Claude): SSN, CREDIT_CARD (Luhn), US ADDRESS, IP_ADDRESS (ipaddress), DOB (with cue); owner opt-in; review pending | Context-aware, deterministic, local; documented precedence and misses |
| L9 | Context-preserving pseudonymization | IMPLEMENTED on `feature` (human request, Oct 18; Claude): request-scoped `[PERSON_n]`, owner `person_style`; review pending | Backend-only deterministic mapping; stale on source/policy/detector change; no mapping persisted |
| L6 | Receipt integrity | UNASSIGNED | Append-only chain, verifier and separately retained checkpoint; limited claims |
| L7 | Demo/docs/reliability | UNASSIGNED | Another laptop runs it; four-minute script; backup recording; submission materials |

Three teammates can claim three disjoint tasks after baseline acceptance; the fourth can integrate or debug. None of these slots is preassigned to a particular person.

Prioritize regression evidence, understandable UX, and demo reliability. Add one real provider if credentials are ready. NER/hash chains are optional; do not expand into BatchGuard, banking lineage, or another product.

## 5. Shared-file ownership

The integration owner coordinates:
- API_CONTRACT.md, backend schemas/routes and frontend shared types.
- Dependency manifests, lockfiles and startup commands.
- Database schema/migrations and seed conventions.
- Receiver payload/template changes.
- Shared app state and main application shell.

Layer assistants may propose changes to these files but must not independently change their contracts. Routine bug fixes inside owned modules can proceed under the assigned scope. Test files should also have explicit ownership where branches overlap.

## 6. Git collaboration

Use one GitHub repository with all four humans as collaborators. One person sets up the initial repository; others clone the same accepted baseline. Repository URL and visibility are human choices; ensure judges can access the submitted code.

If no remote is configured, complete local work and report that fact. Do not invent URLs or credentials. Follow the actual repository workflow authorized/configured by the human.

Typical bounded task:
```bash
git switch main
git pull --ff-only
git switch -c feature/review-polish
```

Make a small change, inspect status/diff, run relevant checks, commit and push your task branch. Open a small pull request for review. Keep main runnable and merge working slices frequently.

If the feature branch must absorb newer main, commit current work, fetch origin, then merge origin/main into the feature branch. Resolve conflicts with the integration owner. Do not reset, overwrite or force-push another member's work.

Ignore .env files, credentials, node_modules, virtual environments, runtime databases, payload captures and build output. Commit placeholder-only .env.example and synthetic fixtures. Each developer has their own local runtime DB.

## 7. Timebox and deadline

At approximately 6:28 p.m. Saturday October 17, 2026 (America/Los_Angeles), about 17.5 elapsed hours remained until Sunday noon. This includes rest, meals, travel and submission; it is not 17.5 hours of coding.

Suggested relative plan, based on the actual current start:
- Next 15–20 minutes: choose baseline owner, read contract, prepare repository.
- Next approximately 1.5–2 hours: one reviewable end-to-end local baseline. This is a target, not a reason to skip essential checks.
- Next 30 minutes: second-person run and baseline acceptance.
- Then 1–2 hours: bounded layers/debugging in separate clones.
- Preserve rest and morning stabilization. If baseline takes longer, remove enhancements.
- Sunday morning: freeze interfaces/features, reproduce demo, finalize README/results/slides.
- Submit/upload around 11:15 a.m.; hard deadline noon.

The packet conflicts about Saturday room closing at 7/10 p.m.; prepare relocation and follow organizer clarification. Do not assume overnight venue availability.

## 8. Required handoff from every assistant

Return:
1. Task, branch and base/ending commit if available.
2. Implemented behavior and changed files.
3. Exact commands actually run and pass/fail results.
4. Startup/demo steps and environment variables (names only, never secrets).
5. Contract/dependency/schema changes, if coordinated.
6. Working scenarios, limitations, unverified areas and known bugs.
7. What another teammate should do next.

No fabricated tests, benchmarks, user feedback or provider results. A local receiver acknowledgement is not an LLM-generated answer.

## 9. Sharing with Codex, ChatGPT, Claude or another assistant

Use the repository files directly when the assistant has filesystem access. Otherwise attach AGENTS.md, PROJECT_CONTEXT.md, API_CONTRACT.md, TEAM_WORKFLOW.md and the relevant prompt; explicitly ask it to read all attachments. AGENTS.md contains repository instructions, but do not assume every product automatically loads it.

Share the accepted repository/commit, not only screenshots or a copied chat summary. Include the assigned task boundary and actual current state. Do not send credentials in the prompt.

The original conversation is not required once these documents and the actual baseline are available.

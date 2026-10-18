> Historical planning guide. The implemented six-feature branch is documented in README.md, PROJECT_CONTEXT.md, API_CONTRACT.md, TEAM_WORKFLOW.md and FEATURE_HANDOFF.md. Those current files take precedence over older phase/status/assignment statements below.

# TrojanHacks DataGate team roadmap — current

Team: Priyanka, Ishita, Yuxin, Aishwarya.
All implementation roles: UNASSIGNED.

This is the current baseline-first roadmap. Earlier three-person/afternoon/named-role plans are superseded. Product scope and interfaces are defined in PROJECT_CONTEXT.md and API_CONTRACT.md.

## Phase A: choose and build one baseline

- Human team chooses one baseline assistant owner.
- Read AGENTS.md, PROJECT_CONTEXT.md, API_CONTRACT.md and TEAM_WORKFLOW.md.
- Use prompts/BASELINE_AGENT_PROMPT.md.
- One assistant creates the full small application; others may review without editing its source.
- No external model key is needed. The receiver is a clearly labeled local capture/acknowledgement.
- Preserve access, minimization, mandatory redaction, exact review, final recheck, single-use dispatch and truthful receipts.

## Phase B: acceptance

- Run actual backend tests and frontend build.
- Have another person start the app from README.
- Demonstrate one allowed and one blocked request, then revocation after preview.
- Share the baseline through the agreed Git repository and record its commit.
- Choose an integration owner.

## Phase C: bounded additions and debugging

- Team claims tasks from TEAM_WORKFLOW.md; no names are preassigned.
- Every assistant starts from the same baseline commit in its own clone/worktree.
- Each task has owned files and acceptance conditions.
- Coordinate API/types/dependency/database changes centrally.
- Use small branches and reviewable merges; keep main runnable.
- Use prompts/LAYER_AGENT_PROMPT.md or prompts/REVIEW_OR_DEBUG_PROMPT.md.

## Remaining-time plan

Prepared around 6:28 p.m. Saturday October 17, 2026, Los Angeles time: roughly 17.5 elapsed hours until Sunday noon, including rest and logistics.

Use relative targets from the actual current time:
1. 15–20 minutes: owner selection and repository preparation.
2. Approximately 1.5–2 hours: reviewable complete baseline.
3. 30 minutes: second-person run and acceptance.
4. 1–2 hours: highest-value bounded layers/debugging.
5. Preserve rest and morning stabilization; cut optional layers if baseline takes longer.
6. Sunday morning: freeze interfaces/features, rehearse, finalize actual results.
7. Submit/upload around 11:15 a.m.; hard deadline Sunday noon.

Follow organizers' clarification of Saturday room closing; packet says both 7 and 10 p.m. No overnight venue is promised.

## Submission and demo

Required: name + one vertical, four team members, accessible GitHub repository reflecting event work, brief description and requested presentation uploads. Prepare slides and working demo/backup.

Four-minute demo:
- User/problem.
- Permitted dataset and reviewed minimal payload.
- Actual controlled send and receipt.
- Revocation or denied request with zero adapter calls.
- Real test results, actual coverage and limitations.

Preliminary Q&A: one minute; finalist Q&A: three minutes.

Do not claim the local receiver generated an AI answer. Do not claim future layers or unrun checks as complete.

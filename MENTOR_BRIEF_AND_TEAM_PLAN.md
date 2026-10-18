> Historical planning guide. The implemented six-feature branch is documented in README.md, PROJECT_CONTEXT.md, API_CONTRACT.md, TEAM_WORKFLOW.md and FEATURE_HANDOFF.md. Those current files take precedence over older phase/status/assignment statements below.

# DataGate mentor brief and current team approach

Team: Priyanka, Ishita, Yuxin, Aishwarya.
Roles: UNASSIGNED.

This brief replaces earlier provisional named assignments and old afternoon schedules. Read PROJECT_CONTEXT.md, API_CONTRACT.md and TEAM_WORKFLOW.md for implementation and coordination.

## One-minute mentor explanation

“We are building DataGate, a checkpoint before company data reaches an AI service. A support analyst wants to summarize customer complaints, but the source contains identifiers and customer-specific records.

“The backend checks the analyst's dataset access, task and destination. It keeps only the needed fields, hides supported restricted information, and shows the exact outgoing content for review. The analyst can hide more but cannot override owner restrictions.

“At Send, permissions and the approved source/policy/content are checked again. Revoked or stale requests do not dispatch. A receipt records the real outcome without raw ticket text.

"Our planned baseline is two synthetic datasets, two demo analysts, one task and a local capturing receiver. We will test that allowed calls work and forbidden calls do not occur. We would like feedback on the workflow and the most important case to demonstrate."

## Concrete example

An owner registers MapleCo feedback in the backend. MapleCo's analyst can request its summary; RiverCo's analyst cannot preview it.

The summary needs message only, so name/email/account columns are excluded. An email embedded inside message is replaced with [EMAIL]. The analyst reviews that payload and approves. The receiver gets only those prepared bytes.

Revoke access after preview and press Send: the final check blocks it. This controls future dispatch, not information already viewed or sent.

## Questions for a mentor

1. Is this a clear, useful support-analytics workflow?
2. Is the small baseline sufficient for an end-to-end four-minute demonstration?
3. Are access-before-preview and access-before-send sensible boundaries?
4. What important allowed/denied scenario is missing?
5. After the baseline, should we prioritize evaluation, a real receiver/provider, or detector coverage?

## How the group will work

One chosen member's coding assistant builds the baseline first. Other assistants can review the contract but do not independently scaffold applications.

After a second person verifies and the baseline commit is shared, teammates claim distinct additions/debug tasks in separate clones/worktrees. No implementation area is preassigned to a named member.

Use prompts/BASELINE_AGENT_PROMPT.md, prompts/LAYER_AGENT_PROMPT.md and prompts/REVIEW_OR_DEBUG_PROMPT.md.

## Shared repository

Use one GitHub repository with four collaborators. One owner prepares it; others clone the accepted baseline. Keep main runnable and merge small reviewed slices. Never let several chats switch branches in the same checkout.

Keep .env/keys, runtime SQLite files, payload captures and dependencies/build output out of Git. Commit only synthetic fixtures and placeholder configuration.

## Deadline and priorities

Sunday October 18 noon, America/Los_Angeles; aim to submit/upload by 11:15 a.m. Use the current relative plan in TROJANHACKS_TEAM_ROADMAP.md instead of an obsolete afternoon timetable.

Baseline first, then bounded layers. Preserve rest, demo reliability and submission buffer. Only report implemented behavior and actual verification.

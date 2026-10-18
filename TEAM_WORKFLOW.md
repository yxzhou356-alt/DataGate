# DataGate team workflow

Team: Priyanka, Ishita, Yuxin, Aishwarya.

| Item | Current value |
| --- | --- |
| Repository | https://github.com/yxzhou356-alt/DataGate |
| Baseline | teammate branch `base-line`, commit `21f5abc` |
| Current assignment | Priyanka explicitly assigned baseline review + all six proposed features |
| Integration branch | `codex/six-governance-features` |
| Human acceptance | A second teammate's run remains to be done |
| Future ownership | Team must claim bounded next tasks; no names inferred from old suggestions |

This integration uses one isolated clone, preserving the teammate's app. Internal assistants were assigned disjoint frontend, detector/evaluation, and regression-test files; the main assistant coordinated shared backend/contracts/dependencies. This is not an instruction for teammates to run competing scaffolds.

## Teammates start here

After this branch is available:

```bash
git fetch origin
git switch --create my-review-work origin/codex/six-governance-features
```

Pick your own branch name; if it already exists, switch to it without recreating. Each human/assistant uses a separate clone or worktree. Follow README setup; run the tests and reproduce the demo on another laptop. Record actual acceptance or issues.

Before changing anything, agree with the team on: task/owner, base commit, permitted files, goal and acceptance checks, shared contract files requiring coordination. Keep PRs bounded. Do not force-push or overwrite another member's work.

Shared files needing coordination: API_CONTRACT, schemas/routes/types, dependency locks, DB migration, App state, receiver template and startup commands. Do not use old phase-A prompts to generate a second baseline.

## Suggested remaining work

1. A second teammate follows README from a clean checkout and validates both accounts, manual review, revocation, audit export and real dashboard evidence.
2. Prepare a four-minute demo/backup recording and a short architecture explanation. Show failure cases and measured NER limitations honestly.
3. Have another teammate review the PR/diff before team merge. Choose the integration owner together.
4. Optional later assignments need explicit scope: enterprise authentication, owner administration, a real provider through the existing adapter, broader data/detection evaluation. They are not included in the six-feature assignment.

Keep node_modules, virtual environments, runtime DBs/sources/captures, .env and credentials out of Git. Commit only synthetic fixtures and sanitized aggregate evidence. If code changes, rerun the relevant checks and regenerate dashboard evidence; old reports must remain visibly stale until replaced.

Every handoff includes branch/commit, changed behavior/files, exact checks/results, setup, contract/schema/dependency changes and remaining limits. Use README, PROJECT_CONTEXT, API_CONTRACT, AGENTS and the human task as the shared assistant context. Earlier implementation summaries/roadmaps are historical, not alternate specifications.

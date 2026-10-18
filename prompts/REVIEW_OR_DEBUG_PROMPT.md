# Copy/paste prompt for baseline review or bounded debugging

Read AGENTS.md, PROJECT_CONTEXT.md, API_CONTRACT.md and TEAM_WORKFLOW.md. Review the existing DataGate baseline; do not scaffold or redesign it.

Mode: [READ_ONLY_REVIEW or BOUNDED_BUGFIX]
Baseline/task commit: [FILL IN]
Reported symptom or review target: [FILL IN]
Owned files for fixes: [FILL IN if bugfix]
Integration owner: [FILL IN]

In READ_ONLY_REVIEW, do not edit files. Run relevant checks if permitted and return prioritized, reproducible findings.

In BOUNDED_BUGFIX, reproduce the assigned issue, fix its root cause within the file boundary, and add a meaningful regression test where appropriate. Preserve unrelated changes. Do not rewrite the frontend, framework, API or database without coordination.

Prioritize:
- Does the allowed path actually reach the local receiver with the exact reviewed bytes?
- Are dataset/draft/receipt permissions enforced by backend identity?
- Can the browser bypass mandatory hiding or replace the outbound payload?
- Do revocation/stale source/policy/review stop Send?
- Can duplicate/concurrent Send call twice?
- Are receipt outcome and receiver mode truthful?
- Do metadata logs/receipts expose raw customer content or tokens?
- Can another teammate run the application from README?

Use isolated test storage. Do not claim tests you did not run. State any environment blocker and continue independent checks.

Return findings or changes with reproduction, impact, file references, actual verification results, remaining limits and next action. Do not autonomously message another chat.

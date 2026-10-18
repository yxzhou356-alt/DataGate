# Copy/paste prompt for a layer assistant

I am assigning you ONE bounded addition to the existing DataGate baseline.

Read AGENTS.md, PROJECT_CONTEXT.md, API_CONTRACT.md and TEAM_WORKFLOW.md. Inspect the real baseline and its README. Implement the assigned layer rather than scaffolding a new application.

Task ID/title: [FILL IN]
Accepted baseline commit: [FILL IN]
Task branch/clone: [FILL IN]
Human owner: [FILL IN]
Integration owner: [FILL IN]
Goal: [FILL IN]
Owned files/directories: [FILL IN]
Shared files requiring coordination: [FILL IN]
Acceptance condition: [FILL IN]
Relevant checks: [FILL IN]

Do not start editing until the human has supplied a task and file boundary. If the baseline is missing or does not run, report that and help diagnose it within the assigned scope; do not generate a competing scaffold.

Preserve the existing v1 API, status semantics, authorization, mandatory redaction, purpose minimization, source/policy/review binding, single-use dispatch and metadata receipts. No browser-supplied authoritative payload, role, permission grant or destination URL.

Work in a separate clone/worktree from other assistants. Do not switch another chat's branch or overwrite unrelated changes. Coordinate contract, dependency, database and startup changes with the integration owner before applying them.

For a provider layer, use only the human-assigned provider and environment-variable names. Keep all calls behind the existing adapter, preserve local mode, use test spies, and never include credentials in output.

For a NER layer, distinguish using a pretrained detector from training a model; report real supported categories and errors.

For a receipt-chain layer, preserve metadata-only events and explain dependence on a separately retained trusted checkpoint.

Run the baseline regression suite and checks relevant to your change. No fabricated verification, metrics or provider results. Do not add unrelated layers or autonomously message other chats.

Handoff:
1. Implemented behavior and changed files.
2. Exact checks actually run/results.
3. Contract/dependency changes and coordination.
4. Manual verification steps.
5. Limits, bugs and follow-up.
6. Branch/commit if available.

---
name: delivery-orchestration
description: Use for substantial implementation or remediation with multiple ownership areas, useful parallel work, integration, or delivery verification. Skip simple inline edits, read-only answers, and plan-only requests.
---

# Delivery Orchestration

Astra root owns the requested outcome, integration, and final engineering approval.
For substantial work, keep one short plan identifying the outcome, owned paths,
dependencies, and verification. Existing task authorization covers internal
planning and review; do not add methodology approval gates.

## Execute

- Inspect the baseline and preserve existing work. Reuse repository patterns.
- Delegate independent work when it improves completion cost, elapsed time,
  context, or evidence. Luna is the default; choose capability before price.
- Give each writer exclusive paths, interfaces, constraints, current depth, and
  focused verification. One live writer owns each file.
- Workstream workers may subdivide at depths 1 and 2 under the
  [delegation topology](references/delegation-topology.md). Every depth-3 agent
  is terminal. All descendants share the same six-thread ceiling.
- Parents suspend edits to delegated paths, integrate returned evidence within
  their scope, and report descendants and results upward. Root owns
  repository-wide generators, Git, external actions, and final integration.
- Reuse compatible agents and continue useful parent work while they run.
  Escalate directly when capability or uncertainty warrants it; a failed
  cheaper attempt is not a prerequisite.

## Verify And Deliver

Run focused checks for changed behavior and required repository gates.
Rerun only checks invalidated by changes, failures, or unresolved concerns.
Inspect the integrated result against the request, interfaces, and evidence.

The Astra root performs ordinary final review. Use one independent
`astra_advisor` for an explicit request or consequential unresolved risk,
following `adversarial-code-review`. Do not stack review stages by default.
Apply valid findings and continue without renewed methodology approval.

For authorized repository changes, finish with the task-only commit, push,
and remote-ref verification unless the user limits that terminal condition.
Preserve existing branch policy, unrelated changes, and external-action
boundaries. Report concrete blockers and unverified outcomes accurately.

Instruction corrections are optional, source-backed maintenance; use
`instruction-learning-loop` only when a durable instruction defect warrants it.

When routing configuration or profiles change, run the focused routing check:

```powershell
$env:CODEX_ROUTING_HOME = (Resolve-Path .).Path
python -B .\skills\delivery-orchestration\scripts\test_routing_policy.py
Remove-Item Env:CODEX_ROUTING_HOME
```

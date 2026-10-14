---
name: delivery-orchestration
description: Use for substantial implementation or remediation with multiple ownership areas, useful parallel work, integration, or delivery verification. Skip simple inline edits, read-only answers, and plan-only requests.
---

# Delivery Orchestration

GPT-6.1 Sol root owns the requested outcome, integration, and final engineering approval.
For substantial work, keep one short plan identifying the outcome, owned paths,
dependencies, and verification. Existing task authorization covers internal
planning and review; do not add methodology approval gates.

## Execute

- Inspect the baseline and preserve existing work. Reuse repository patterns.
- Run `scripts/provider_usage.py` from this skill folder before a dispatch batch.
  Check shared and model-scoped windows. Failed or stale reads remain unknown.
  Match the local CLI account to the selected provider instance.
- If Muse has no native observation, run `/usage` in the Muse terminal.
  Use the subscription windows and observation time, rather than session token counts.
- Delegate independent work when it improves completion cost, elapsed time,
  context, or evidence. Choose the least costly capable route from
  [model routing](references/model-routing.md); capability is mandatory. Native
  profiles are fallback presets, not global provider priority.
- Give each writer exclusive paths, interfaces, constraints, current depth, and
  focused verification. One live writer owns each file.
- Workstream workers may subdivide at depth 1 under the
  [delegation topology](references/delegation-topology.md). Every depth-2 agent
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

The GPT-6.1 Sol root performs ordinary final review. Use one independent advisor
for an explicit request or consequential unresolved risk, following
`adversarial-code-review`. Use Fable high when Claude is available; use
`astra_advisor` only when Claude is unavailable or usage-limited. Do not stack
review stages by default.
Apply valid findings and continue without renewed methodology approval.

For authorized repository changes, finish with the task-only commit, push,
and remote-ref verification unless the user limits that terminal condition.
Preserve existing branch policy, unrelated changes, and external-action
boundaries. Report concrete blockers and unverified outcomes accurately.

Instruction corrections are optional, source-backed maintenance. Skill Loop
captures durable corrections automatically; see the `skill-loop` skill.

When routing configuration or profiles change, run the focused routing check:

```powershell
$env:CODEX_ROUTING_HOME = (Resolve-Path .).Path
python -B .\skills\delivery-orchestration\scripts\test_routing_policy.py
Remove-Item Env:CODEX_ROUTING_HOME
```

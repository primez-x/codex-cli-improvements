# Codex Orchestration Kit

This repository contains a reusable, evidence-driven Codex orchestration
configuration. It keeps expensive models in supervisory roles while routing
bounded scanning and implementation work to faster models with explicit
ownership, depth, and verification gates.

The kit is intentionally generic. It contains no project instructions,
credentials, local runtime state, or machine-specific paths.

## Included

- `config.toml`: an orchestration-only configuration example.
- `agents/`: ten scanner, worker, coordinator, and advisor profiles.
- `skills/delivery-orchestration/`: adaptive implementation routing,
  ownership, integration, and completion gates.
- `skills/plan-review-ladder/`: independent multi-model plan review with
  frozen evidence, packet identity, deadlines, timeout handling, telemetry,
  and explicit sign-off.
- `skills/instruction-learning-loop/`: a bounded loop for turning durable
  corrections into the smallest verified instruction update.
- `hooks/plan_gap_goal_hook.py`: starts goal tracking when an approved plan
  moves into implementation.
- `hooks.json`: portable hook registration for plan-goal and instruction
  learning behavior.

## Model And Effort Matrix

| Role | Model | Effort | Typical use |
| --- | --- | --- | --- |
| Root | GPT-5.6 Sol | Medium | Routing, integration, final decisions |
| Spark scanner | GPT-5.3 Codex Spark | High | Exact low-context evidence |
| Spark worker | GPT-5.3 Codex Spark | XHigh | Small, mechanical edits |
| Luna scanner | GPT-5.6 Luna | Medium | Broader read-only evidence |
| Luna worker | GPT-5.6 Luna | High | Routine implementation |
| Luna coordinator | GPT-5.6 Luna | High | Bounded workstream supervision |
| Terra worker/coordinator | GPT-5.6 Terra | Medium | Ambiguous or cross-layer work |
| Sol worker | GPT-5.6 Sol | XHigh | Rare difficult implementation |
| Sol advisor/coordinator | GPT-5.6 Sol | Max | Adversarial review and supervision |

The configured effort is fixed per profile. When a task exceeds a profile's
capability, context, or risk boundary, routing escalates the model instead of
raising effort ad hoc.

## Delegation Topology

- Depth 0 is the root.
- Depth 1 can use any registered profile.
- Depth 2 uses Luna or Terra coordinators and bounded Spark, Luna, or Terra
  terminal agents.
- Depth 3 is terminal and limited to Spark or Luna scanners/workers.
- Coordinators reserve their own integration paths and assign disjoint
  ownership before concurrent edits.
- The root owns final integration, external actions, and the user response.

Most work should finish at depth 1. Depth 2 is used when decomposition improves
latency, quality, or context hygiene. Depth 3 remains available for genuinely
complex fan-out without becoming the default.

## Plan Review Routes

- **Standard:** Luna candidate, independent Luna validation, root residual-risk
  pass.
- **Expanded:** Standard plus Terra integration validation.
- **Full:** Standard plus an independent Sol challenge, with Terra when
  cross-layer integration is also material.

All reviewers receive the same frozen request, evidence, and candidate plan.
Reviewer-specific lenses are the only difference. The ladder distinguishes
existing authority, planned new artifacts, and implemented artifacts, so a
future file is not falsely reported missing before implementation. Required
stages have packet identities, deadlines, bounded descendants, timeout
handling, and evidence-limited telemetry.

## Install

Use this repository as a source package, not as a blind replacement for an
existing Codex home:

1. Back up the current Codex configuration.
2. Copy `agents/` and the three directories under `skills/` into the matching
   directories under `CODEX_HOME` (normally `~/.codex`).
3. Merge the root model, `[agents]`, `[agents.*]`, `[features]`, and
   `[[skills.config]]` entries from `config.toml` into the local config.
4. Merge `hooks.json` with any existing hook registrations and copy
   `hooks/plan_gap_goal_hook.py`. The registered commands honor `CODEX_HOME`;
   when it is unset they resolve the default `~/.codex` user profile home.
5. Restart Codex and begin a new task so hook registrations, model profiles,
   and skill routing reload.
6. In the new task, open `/hooks`, review the two user-level hook events and
   all three handler registrations, and approve them for this installation. Do
   not bypass trust controls; review and approve the user-level hooks instead.

Model availability and supported reasoning efforts can vary by account and
Codex release. Verify the local model catalog before enabling a profile.

## Validate

From the repository root in PowerShell:

```powershell
$env:CODEX_ROUTING_HOME = (Resolve-Path .).Path
python -B .\skills\delivery-orchestration\scripts\test_routing_policy.py
Remove-Item Env:CODEX_ROUTING_HOME

python -B .\skills\plan-review-ladder\scripts\test_plan_routing.py
python -B .\skills\instruction-learning-loop\scripts\test_instruction_learning.py
python -B -m unittest discover -s .\tests -v
```

After installation, use `/hooks` to confirm both registered events and all
three handlers are enabled, then run the unit-test commands above as a positive
smoke check.

The repository contract tests also reject machine-specific absolute paths and
project-specific material in the reusable package.

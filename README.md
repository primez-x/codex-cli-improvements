# Codex Orchestration Kit

This repository contains a reusable, evidence-driven Codex configuration built
around six terminal custom profiles. The Sol Medium root owns routing,
integration, authorized external actions, and final decisions; bounded leaves
handle discovery, implementation, and independent challenge.

The kit is intentionally generic. It contains no credentials, local runtime
state, machine-specific paths, or project instructions.

## Included

- `config.toml`: the portable root and six-profile routing projection.
- `agents/`: two Spark, two Luna, and two Sol terminal profiles.
- `skills/delivery-orchestration/`: adaptive implementation routing, ownership,
  Git completion, and terminal gates.
- `skills/plan-review-ladder/`: independent plan validation with frozen packet
  identity, deadlines, timeout handling, telemetry, and proportional Sol review.
- `skills/instruction-learning-loop/`: durable corrections converted into the
  smallest verified instruction update.
- `hooks/plan_gap_goal_hook.py`: goal tracking when an approved plan moves into
  implementation.
- `hooks.json`: portable hook registration for plan-goal and instruction-learning
  behavior.

## Weighted Model And Effort Matrix

| Role | Model | Effort | Typical use |
| --- | --- | --- | --- |
| Root | GPT-5.6 Sol | Medium | Routing, integration, final decisions, external actions |
| Spark scanner | GPT-5.3 Codex Spark | XHigh | Tiny exact read-only checks |
| Spark worker | GPT-5.3 Codex Spark | XHigh | Small mechanical edits |
| Luna scanner | GPT-5.6 Luna | High | Broad and context-heavy discovery |
| Luna worker | GPT-5.6 Luna | Max | Default substantial implementation |
| Sol worker | GPT-5.6 Sol | XHigh | Rare genuinely difficult implementation |
| Sol advisor | GPT-5.6 Sol | Max | Rare consequential adversarial review |

This removes redundant intermediate custom tiers. Spark wins the tiny-task lane
on latency and its separate consumption lane. Luna wins the routine and
large-context lanes on weighted cost, speed, and capability. Sol is reserved
for cases where difficulty or consequence justifies the jump.

The configured effort is fixed per profile. Routing escalates the model instead
of changing effort ad hoc.

## Context-Aware Routing

Spark's speed is useful only while its packet stays small. The current catalog
advertises about 128k tokens for Spark versus 272k for the GPT-5.6 family, with
lower usable limits after system overhead. Every Spark assignment therefore
uses `fork_turns = "none"` and a fresh self-contained packet with exact anchors,
expected evidence, and explicit stop conditions. Broad discovery, synthesis,
or inherited conversation history routes to Luna High instead.

Luna Max is the default writer. Sol XHigh is a rare implementation escalation;
Sol Max advice is risk-triggered for consequential architecture, compatibility,
migration, persistence, security, concurrency, data integrity, external impact,
or unresolved high-severity gaps.

## Delegation Topology

- Depth 0 is the Sol Medium root.
- All six custom profiles are terminal depth-1 leaves and report directly to
  the root.
- Leaves never spawn. The configured depth is `1`.
- Normal work uses one to three concurrent leaves. The ceiling of four applies
  to spawned threads and does not count the root.
- Writers receive disjoint ownership. The root owns integration, Git/external
  actions, and the user response.

## Plan Review Routes

- **Standard:** root candidate, independent Luna High validation, root
  residual-risk pass. No mandatory Sol for routine low-risk plans.
- **Expanded:** Standard plus one early risk-triggered Sol Max challenge.
- **Full:** Expanded plus a fresh final Sol Max challenge after synthesis and
  verification design.

All reviewers receive a frozen request, evidence bundle, candidate, and
reviewer-specific lens. Review packets have identity hashes, deadlines, zero
descendant budget, timeout handling, and evidence-limited telemetry.

## Install

Use this repository as a source package, not as a blind replacement for an
existing Codex home:

1. Back up the current Codex configuration.
2. Copy the six files under `agents/` into the matching `CODEX_HOME/agents`
   directory and remove retired custom-profile files from earlier versions.
3. Copy the three directories under `skills/` into `CODEX_HOME/skills`.
4. Semantically merge the root model/effort, `[agents]`, `[agents.*]`,
   `[features]`, and `[[skills.config]]` entries from `config.toml`; preserve
   machine-local plugin, MCP, trust, notification, and runtime settings.
5. Merge `hooks.json` with existing registrations and copy
   `hooks/plan_gap_goal_hook.py`. The commands honor `CODEX_HOME` and otherwise
   resolve `~/.codex`.
6. Restart Codex and begin a new task so the root model, profiles, skills, and
   hooks reload. Review and approve user-level hooks through `/hooks`; do not
   bypass trust controls.

Model availability, context limits, and supported efforts can vary by account
and release. Verify the local model catalog before enabling profiles.

## Validate

From the repository root in PowerShell:

```powershell
$env:CODEX_ROUTING_HOME = (Resolve-Path .).Path
python -B .\skills\delivery-orchestration\scripts\test_routing_policy.py
Remove-Item Env:CODEX_ROUTING_HOME

python -B .\skills\plan-review-ladder\scripts\test_plan_routing.py
python -B .\skills\plan-review-ladder\scripts\test_packet_integrity.py
python -B .\skills\instruction-learning-loop\scripts\test_instruction_learning.py
$env:CODEX_HOME = (Resolve-Path .).Path
python -B .\skills\instruction-learning-loop\scripts\test_global_autonomy_contract.py
Remove-Item Env:CODEX_HOME
python -B -m unittest discover -s .\tests -v
```

After installation, run the four installed skill-script suites against
`CODEX_HOME`, confirm the parsed TOML projection, and start a new task for the
effective runtime smoke check. Repository unit tests remain source-checkout
validation and are not copied into `CODEX_HOME`.

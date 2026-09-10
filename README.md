# Codex Orchestration Kit

This repository contains a reusable, evidence-driven Codex configuration built
around a GPT-6 Astra low root and bounded terminal depth-1 leaves. It registers
eight general-purpose routing profiles plus one on-demand read-only reviewer,
for nine registered profiles in total. The root owns routing, synthesis,
integration, Git and external actions, and the final response. Leaves perform
bounded assigned work and return evidence to the root.

The portable core contains no credentials, private user-profile paths, machine
runtime state, or project-specific settings and operating instructions.
Optional domain-specific source snapshots and patches live under
[`integrations/`](integrations/README.md); they are not part of the core
install or auto-installed by its review overlay. Review each optional change
against its canonical source before applying it.

## Included

- `config.toml`: the Astra-low root, nine registered profiles, concurrency and
  depth limits, and the four maintained skill entrypoints.
- `agents/`: Spark scanner and worker, Luna scanner, Luna fast worker, Luna
  worker, Sol fast worker, Astra medium worker, Astra-high advisor, and
  Astra-high reviewer profiles.
- `skills/delivery-orchestration/`: task-shape routing, ownership, completion,
  and root integration policy.
- `skills/plan-review-ladder/`: proportional plan validation and optional
  Astra-high challenge checkpoints.
- `skills/instruction-learning-loop/`: durable instruction corrections and the
  maintained installed-skill reconciliation policy.
- `skills/adversarial-code-review/`: risk-triggered independent review plus an
  optional legacy replay/evaluation contract.
- `hooks/plan_gap_goal_hook.py` and `hooks.json`: portable plan-gap and
  instruction-learning hooks for `UserPromptSubmit` and `Stop`.

## Model and effort matrix

The root is not a registered leaf. The eight general-purpose profiles are the
routing rows below; the reviewer is a separate ninth registered identity.

| Role | Profile ID | Model | Effort | Typical use |
| --- | --- | --- | --- | --- |
| Spark scanner | `spark_scanner` | GPT-5.3 Codex Spark | XHigh | Tiny exact read-only evidence from a bounded packet |
| Spark worker | `spark_worker` | GPT-5.3 Codex Spark | XHigh | Small localized mechanical edits with focused checks |
| Luna scanner | `luna_scanner` | GPT-5.6 Luna | Medium | Broad discovery, context-heavy evidence, and validation |
| Luna fast worker | `luna_fast_worker` | GPT-5.6 Luna | XHigh | Economical bounded routine implementation |
| Luna worker | `luna_worker` | GPT-5.6 Luna | Max | Default substantial implementation and verification |
| Sol fast worker | `sol_fast_worker` | GPT-5.6 Sol | Low | Simpler, tightly specified, low-ambiguity critical-path work |
| Astra medium worker | `astra_worker` | GPT-6 Astra | Medium | Difficult, ambiguous, security-sensitive, or cross-layer work |
| Astra high advisor | `astra_advisor` | GPT-6 Astra | High | Consequential architecture, plan, or integrated-delivery challenge |
| Astra high reviewer | `astra_reviewer` | GPT-6 Astra | High | On-demand independent post-verification review |

`astra_worker` is the current Astra-medium implementation profile.
`astra_reviewer` is an evidence-bound review identity, not a routine routing
tier. Profile names alone do not prove which model executed a task; use the
parsed registration and profile file as the authority.

## Routing decision method

Capability eligibility is the first gate. Do not choose a cheaper or faster
route if its context, write authority, ambiguity tolerance, or verification
strength cannot safely cover the packet. Once eligible candidates remain, choose
by total cost-to-verified-completion, including:

- packet preparation and context transfer;
- handoff and startup time;
- runtime and critical-path delay;
- retries and recovery;
- review and evidence collection; and
- root integration, correction, and rework.

Use the smallest capable route that preserves the quality bar. Spark handles
fresh, self-contained, tiny packets with `fork_turns = "none"`. Luna is the
primary delegated model: Medium scans broadly, XHigh handles bounded routine
work, and Max handles more substantial implementation. Use `sol_fast_worker`
for a clearly specified low-ambiguity packet that blocks the critical path.
Move directly to `astra_worker` when difficult work needs Astra medium; do not
require a failed cheaper attempt. Astra high advice or review is reserved for a
named consequential risk or an explicit independent-review request.

The root may handle a short command inline only when its context is already
available, the target and authorization are exact, one focused verification is
sufficient, and rollback is cheap. Delegation overhead is considered only after
those capability and safety gates pass.

## Illustrative benchmark snapshot

The values below are user-supplied illustrative workload observations. They are
not measured by this repository, are not official provider prices, and are not
universal model benchmarks. Cost is an example cost per task and time is an
example wall time per task; neither includes an implied promise for another
workload. The Sol-high row is comparison data only, not a routine route.

| Route | Illustrative intelligence score | Illustrative cost/task | Illustrative wall time/task |
| --- | ---: | ---: | ---: |
| Luna xhigh | 35 | $0.085 | 3.6 min |
| Luna max | 38 | $0.18 | 6.3 min |
| Sol low | 34 | $0.26 | 1.2 min |
| Sol high (comparison only) | 42 | $0.81 | 3.8 min |
| Astra low | 46 | $0.82 | 1.5 min |
| Astra high | 51 | $1.72 | 4 min |

No Astra-medium data was supplied. Do not infer its cost, quality, or latency
from adjacent rows. Revisit the matrix with actual task success, first-pass
quality, retry count, elapsed time, and measured cost when those observations
are available. Do not duplicate work merely to manufacture a benchmark.

## Delegation topology

- Depth 0 is the GPT-6 Astra low root.
- All nine registered profiles are terminal depth-1 identities. The eight
  general-purpose profiles are routing leaves; `astra_reviewer` is dispatched by
  the root only for an explicit or consequential review.
- `max_depth = 1` is both the configured and behavioral boundary. Leaves never
  spawn. Only the root creates or steers child work.
- `max_concurrent_threads_per_session = 6` is the ceiling for spawned terminal
  leaves and does not count the root. Normal work uses one to three active
  leaves; six is a limit, not a quota.
- Every writer receives exclusive owned paths, constraints, and focused
  verification. One live writer owns a file; overlapping work is serialized.
- Leaves do not commit, push, publish, deploy, perform destructive actions, or
  mutate external systems. The root owns integration, Git, external actions,
  and the user response.

## Whole-deliverable approval and independent review

Every whole deliverable receives engineering approval from the Astra-low root
or an Astra-high advisor. The on-demand reviewer supplies an independent
challenge when selected; the root or advisor remains accountable for
integration, finding disposition, and the final decision. Root review is
sufficient for ordinary low-risk work; review is not a mandatory step for every
task, file, or stage.

Dispatch an independent read-only Astra-high reviewer when explicitly requested
or when a consequential trigger warrants a separate challenge: security,
authentication, credentials, privacy, destructive or irreversible actions,
migrations, persistence, data integrity, concurrency, production or material
external impact, major architecture or compatibility, public-contract changes,
conflicting evidence, a stuck approach, or repeated failed verification. An
optional review failure is reported; only a required high-risk review failure
blocks delivery.

## Maintained skill policy

[`installed-skill-reconciliation.md`](skills/instruction-learning-loop/references/installed-skill-reconciliation.md)
is the maintained user-owned policy for reconciling vendor skill guidance with
the current task. Read the selected skill family alongside the applicable
section. The policy resolves methodology conflicts while preserving technical
preconditions, executable gates, scope, and evidence. Contextual vendor and
product names may appear in this reference or in integration material; private
profile paths, credentials, and runtime state do not belong in the package.

## Legacy historical replay

[`evaluation-replay-workflow.md`](skills/adversarial-code-review/references/evaluation-replay-workflow.md)
and the lifecycle/evaluator scripts preserve an optional, provenance-bound
historical Sol/max replay contract. Use it only for an explicit auditable
replay or reviewer-quality evaluation. It is not current routing, routine
delivery evidence, or a runtime hook, and a passing historical replay must not
certify current Astra execution or review quality.

## Windows process boundary

Preserve the user's interactive terminal, console, and application windows.
For non-interactive work, invoke the direct executable as a separate child with
redirected streams and `CREATE_NO_WINDOW` (or the equivalent native no-window
API). Do not use a shared-console `-WindowStyle Hidden` wrapper, hide or
minimize the user's terminal, or add a shell solely to suppress a child window.
Terminate the child shell after capturing its exit code.

## Install

The optional transactional installer is a review-overlay installer for the
managed skills, hooks, and review assets. It intentionally preserves the
machine-local root model and profile state; it is not a complete Astra root or
profile migration. To adopt the Astra matrix, review and semantically merge
`config.toml` and all registered profiles as described in the manual steps
below.

Use this repository as a source package, not as a blind replacement for an
existing Codex home. Prefer the transactional installer over manual copying or
merging. It uses an explicit production-file allowlist, previews raw copied
paths and exact managed TOML/JSON/instruction changes, writes a private staged
payload and recovery journal, authenticates backups, is idempotent, and can roll
back a transaction.

```powershell
$targetCodexHome = [Environment]::GetEnvironmentVariable("CODEX_HOME")
if ([string]::IsNullOrWhiteSpace($targetCodexHome)) {
    $targetCodexHome = Join-Path ([Environment]::GetFolderPath("UserProfile")) ".codex"
}
python -B .\skills\adversarial-code-review\scripts\install_review_gate.py preview --source-root . --codex-home $targetCodexHome
python -B .\skills\adversarial-code-review\scripts\install_review_gate.py install --source-root . --codex-home $targetCodexHome
python -B .\skills\adversarial-code-review\scripts\install_review_gate.py verify --source-root . --codex-home $targetCodexHome
Remove-Variable targetCodexHome
```

Incomplete-transaction recovery is compare-and-swap safe against its journal:
only `applied` paths and the in-flight `next_path` are rollback candidates,
untouched paths are never rewritten, and every live target must still equal an
authenticated preimage, postimage, or expected absence before recovery mutates
anything. Per-path `rolling_back` progress makes an interrupted rollback
restartable; unrecognized drift is preserved and blocks recovery.

The default instruction merge preserves unmarked global instructions and
reports `global_agents.mode` as `preserved_block`. When this repository's
generic `AGENTS.md` is intentionally authoritative for the whole Codex home,
add `--replace-global-agents` to `preview`, `install`, and strict `verify`. That
mode stages the byte-exact source file in the same authenticated transaction,
reports previous and source SHA-256 identities, and remains rollback-safe. Any
semantic destination that changes after planning aborts before live writes.

`install` and `verify` run installed skill validators plus static and semantic
configuration checks. They do not install or certify the optional legacy
Sol/max replay. They preserve unrelated hook groups, hook trust metadata,
agents, skills, config sections, and instructions. The package's `hooks.json`
registers only the plan-gap and instruction-learning handlers for
`UserPromptSubmit` and `Stop`; it does not register adversarial lifecycle hooks
or dynamic error-learning events.

After installation, restart Codex, open a new task, and use `/hooks` to confirm
the plan-goal and instruction-learning handlers and any intentionally preserved
unrelated hooks. Trust user-level hooks through the normal `/hooks` flow; the
installer never writes trusted hashes or bypasses trust controls.

If installing manually:

1. Back up the current Codex configuration.
2. Copy the eight general-purpose profiles under `agents/` plus
   `astra_reviewer.toml` into the matching `CODEX_HOME/agents` directory. Do not
   blindly remove existing profiles: inspect config references and provenance,
   then archive or remove only confirmed retired profiles owned by this
   installation. Preserve unrelated profiles and local additions.
3. Copy the four managed skill directories under `skills/` into
   `CODEX_HOME/skills`, including the maintained reconciliation reference.
4. Semantically merge the root model/effort, `[agents]`, `[agents.*]`,
   `[features]`, and `[[skills.config]]` entries from `config.toml`; preserve
   machine-local plugin, MCP, trust, notification, and runtime settings.
5. Reconcile the rewritten root `AGENTS.md` with the destination's current
   instructions, preserving private local additions and resolving stale Sol-era
   guidance in favor of the current Astra policy. Do not replace local
   instructions wholesale.
6. Merge `hooks.json` with existing registrations and copy
   `hooks/plan_gap_goal_hook.py`; the commands honor `CODEX_HOME` and otherwise
   resolve `~/.codex`.
7. Restart Codex and begin a new task so the root model, profiles, skills, and
   hooks reload.

Model availability, context limits, and supported efforts vary by account and
release. Verify the local model catalog before enabling profiles.

## Validate

From the repository root in PowerShell, run the focused current-package checks:

```powershell
$previousRoutingHome = $env:CODEX_ROUTING_HOME
$env:CODEX_ROUTING_HOME = (Resolve-Path .).Path
python -B .\skills\delivery-orchestration\scripts\test_routing_policy.py
if ($null -eq $previousRoutingHome) {
    Remove-Item Env:CODEX_ROUTING_HOME -ErrorAction SilentlyContinue
} else {
    $env:CODEX_ROUTING_HOME = $previousRoutingHome
}

python -B .\skills\plan-review-ladder\scripts\test_plan_routing.py
python -B .\skills\plan-review-ladder\scripts\test_packet_integrity.py
python -B .\skills\instruction-learning-loop\scripts\test_instruction_learning.py
$previousAutonomyHome = $env:CODEX_AUTONOMY_HOME
$env:CODEX_AUTONOMY_HOME = (Resolve-Path .).Path
python -B .\skills\instruction-learning-loop\scripts\test_global_autonomy_contract.py
if ($null -eq $previousAutonomyHome) {
    Remove-Item Env:CODEX_AUTONOMY_HOME -ErrorAction SilentlyContinue
} else {
    $env:CODEX_AUTONOMY_HOME = $previousAutonomyHome
}

python -B -m unittest discover -s .\tests -v
```

These source-checkout tests do not prove that a running Codex app loaded or
trusted the installed files. After installation, run the installed validators,
confirm the parsed TOML projection, restart Codex, and perform a fresh-task
runtime smoke check. Report source, installed, and runtime evidence separately.

The optional lifecycle health/evaluation commands and `install_review_gate.py
smoke` action belong to the explicit legacy replay workflow above. They remain
available for historical regression work and must not be presented as Astra
certification.

---
name: delivery-orchestration
description: >-
  Route material implementation through the canonical bounded multi-agent
  topology with explicit ownership, contracts, recovery, and verification.
---

# Delivery Orchestration

When an advisor packet is received, the root is the only party that dispositions
each advisor finding as accepted, rejected, or deferred, and each decision must
be explicitly grounded in primary evidence.

Start with the Luna max root. The root directly coordinates work, decisions,
integration, authorized external actions, Git, and final verification. The
canonical exact adjacency/depth matrix in `references/delegation-topology.md`
is the sole full model/effort/depth/adjacency authority.

## Routing

Use the direct root path only for one concern with no discovery, no conflicting
authority, no unapproved or consequential external side effect, one focused
verification, and a lossless rollback. Delegation overhead is not a reason to
route material work directly; reclassify immediately when any gate fails.
External mutation is explicitly authorized only for an exact target with a
low-impact boundary.

Use Spark fast path for tiny bounded localized checks or mechanical edits from
self-contained packets. Luna is the default for broad/context-heavy scans and
normal implementation. Escalate the model to Sol only for genuinely difficult
or consequential risk. Root-routed independent review is reserved for a
high-risk trigger such as security, privacy, migration, persistence,
data-integrity, external impact, public-contract change, conflicting evidence,
or repeated failed verification. If optional review infrastructure fails,
report the limitation and continue a verified localized, low-risk delivery;
only a required high-risk review failure blocks delivery.

## Assignment and ownership

Use compact `WORK_ASSIGNMENT_V1`, `WORK_RETURN_V1`, and `ADVISOR_REQUEST_V1`
contracts defined in the topology reference. Each writer has an exclusive
direct-parent-owned scope (`owned_paths`, owned resources, permitted actions).
The assignment ID contains root-session identity, owner, direct return target,
expected outcome, and checks. Serialize overlapping writers; direct parents own
returns and reconcile them before integration. Same warm worker revisions may
continue related work only with a fresh assignment and unchanged ownership.
The root owns Git, external actions, and repository-wide generators.

## Agent identity and roster

For every legal spawn, derive `d<depth>_<profile>_<purpose_slug>` and
`D<depth> · <family>/<effort> · <role> · <purpose>` from the parent depth,
selected registered profile, and normalized purpose defined in the topology
reference. Reject empty or untyped/default identities and live sibling
collisions. Same-agent revisions use `followup_task` with a fresh assignment ID
and unchanged ownership; authorized model/effort overrides affect only the
display label. Both work envelopes retain `task_name` and `display_label`.

Nested Luna parents send the root metadata-only `ROSTER_DELTA_V1` after a
successful spawn and after terminal reconciliation. It has only the canonical
task path, task name, display label, and active/completed/failed/terminated
status; it carries no work results, transfers no ownership, and cannot bypass
direct-parent `WORK_RETURN_V1` routing. The root publishes a compact roster on
start and material delegation changes; generated aliases are secondary.

An orchestrator makes no edits in an active child scope and integrates only
after writers are idle and returns are reconciled. A Sol advisor is a
risk-triggered sibling handoff from the root: drain and yield active work,
validate at root, then use same-agent resume. If that fails, send an explicit
rehydration fallback packet. Advice never creates a user approval gate; the
root owns disposition and continuation.

## Recovery and liveness

Reject old-session returns. A new root blocks overlapping writers until it
completes and reconciles the workspace/shared-resource/task-owned-background-process audit.
Leave unclear state unassigned and escalate it; there is no
persistent lease or state machine. Active tool use, running work with evidence,
or concrete progress stays alive indefinitely. A quiet interval triggers only a
status query; interrupt only idle, unanswered-through-grace, or demonstrably
stuck work, and reconcile before reclaim.

## Verification and Git

Inspect assigned paths before editing and preserve unrelated changes. Run the
focused test, TOML/skill validation, and applicable build or runtime checks;
report exact evidence and residual risks. For authorized implementation or
remediation that changes a Git repository, the standing terminal condition is
a safe local task-only commit and push: inspect ahead-of-upstream history, use
explicit paths or hunks, and use an isolated worktree or clone when needed.
On an existing task-aligned feature branch, commit the task-owned diff. On a
default, detached, mismatched, or unsafe branch, create `agent/<task-slug>`.
Never force-push; never push directly to the default branch. Perform remote-ref verification:
the remote head must equal the local SHA, or the task commit must be an
ancestor. Never bypass authentication, branch protection, hooks, or
non-fast-forward safeguards.

Explicit user constraints such as `do not commit`, `leave uncommitted`, `no
push`, `commit only`, or `keep local` override the standing Git default. Pull
requests, merges, releases, and deployments remain separately authorized.
Subagents never commit, push, publish, deploy, or mutate external systems.

Reversible startup-setting changes remain subject to the same focused
verification and rollback gates.

When this skill, `config.toml`, or a custom profile changes, run:

```powershell
$env:CODEX_ROUTING_HOME = (Resolve-Path .).Path
python -B .\skills\delivery-orchestration\scripts\test_routing_policy.py
Remove-Item Env:CODEX_ROUTING_HOME
```

---
name: delivery-orchestration
description: >-
  Use when implementing or remediating work that benefits from bounded quick
  edits, delegated evidence, multiple ownership areas, tests or generated
  artifacts, cross-layer integration, builds, packaging, deployment, or an
  independent failure or risk challenge. Skip read-only answers and plan-only
  requests.
---

# Delivery Orchestration

Keep the configured Sol Medium root focused on the outcome, routing, decisions,
integration, authorized external actions, and final verification. The root
directly coordinates terminal depth-1 leaves and chooses the cheapest profile
that preserves the required context, judgment, ownership, and evidence quality.

This skill explicitly requests proactive subagent delegation for material
delivery. Do not wait for the user to select models or manage routing.

## 1. Define The Delivery Contract

Before editing, record a compact working contract:

- requested outcome, acceptance criteria, and non-goals;
- in-scope systems, repositories, paths, and external targets;
- authorization boundaries and current dirty-worktree baseline;
- required source, test, build, generated-output, runtime, and release gates;
- terminal condition, current evidence, assumptions, and blockers.

Treat a plan, edit, passing focused test, commit, push, build, or artifact upload
as an intermediate state unless it satisfies the complete terminal condition.

## 2. Route Work By Task Shape

A task is material when it likely changes more than one file or concern, aligns
code with tests or generated output, crosses layers, requires a build/install or
runtime smoke, would fill root context with discovery/logs, or carries material
compatibility, security, persistence, concurrency, data-integrity, migration,
or external-impact risk.

For material delivery, dispatch at least one bounded terminal leaf. Keep normal
work to one to three active leaves and use the configured ceiling of four only
for genuinely independent packages. `max_concurrent_threads_per_session = 4`
counts spawned threads, not the root. Every leaf reports directly to the root
and must not spawn.

### Spark fast path

Use `spark_scanner`, xhigh, for a tiny exact read-only check and
`spark_worker`, xhigh, for a small mechanical edit only when every gate passes:

- the target, anchors, owned paths, deliverable, and expected evidence are
  explicit;
- the required context is small and localized;
- no architecture, product, compatibility, security, or ownership decision is
  unresolved;
- success is mechanically verifiable with a focused check;
- failure is cheap, reversible, and cannot silently damage adjacent behavior.

Spark has a materially smaller context window than the 5.6 family. The current
catalog advertises about 128k tokens for Spark versus 272k for 5.6 profiles,
with lower usable limits after system overhead. Always dispatch Spark with
`fork_turns = "none"` and a fresh self-contained bounded packet containing
exact anchors rather than inherited conversation history. Do not send broad
discovery or synthesis to Spark. If a gate fails, scope expands, or context
pressure appears, stop and escalate to Luna.

### Luna default

Luna is the default delegated model:

- use `luna_scanner`, medium, for broad or context-heavy read-only discovery,
  inventories, comparisons, history, logs, and independent validation;
- use `luna_worker`, max, for the default implementation path: substantial
  routine edits, debugging, tests, documentation, and multi-file integration.

The Medium scanner keeps Luna's larger context while prioritizing latency and
cost for reversible evidence work. It returns exact anchors, uncertainty, and
unexamined areas; the root owns conflicting evidence and consequential
interpretation. Escalate the model directly from Luna to Sol when difficulty or
consequential risk exceeds Luna; there is no intermediate custom model tier.

### Sol escalation

Use `sol_worker`, xhigh, only for genuinely difficult, ambiguous,
security-sensitive, cross-layer implementation or diagnosis that Luna cannot
reliably finish. Use `sol_advisor`, max, only for rare consequential
architecture, risk, plan, or final-diff challenge. Do not use either profile as
a routine throughput tier.

Only the depth-0 root dispatches `sol_advisor`. An early checkpoint is
risk-triggered when material architecture, compatibility, migration,
persistence, security, concurrency, data integrity, external impact, conflicting
authority, a stuck approach, or a material approach change is present. A final
checkpoint is risk-triggered after durable changes and fresh evidence when the
same risks remain or the delivery has four or more substantive stages. Sol is
not mandatory for localized, low-risk, mechanically prescribed work with
focused verification. A current Sol-reviewed immutable handoff may satisfy the
early checkpoint when scope and evidence are unchanged.

Give the advisor the checkpoint type, request and acceptance criteria,
authority boundaries, concise evidence anchors, hypothesis or diff,
uncertainties, and specific questions. Final-delivery packets include actual
applicable test, build, and runtime evidence. Disposition each actionable
finding as accepted, rejected, or deferred against primary evidence. Fix
accepted high-severity gaps and rerun affected gates. The advisor never edits,
expands authorization, owns the user response, or creates a user approval gate.

See [delegation topology](references/delegation-topology.md) for the canonical
profile matrix, context split, and terminal-leaf rules.

## 3. Assign Ownership Precisely

Give every writer a self-contained packet containing:

- exact exclusive `owned_paths`;
- requested behavior, non-goals, and authoritative anchors;
- applicable instructions and interfaces with root-owned work;
- focused verification, expected evidence, and output format;
- stop conditions and an explicit zero descendant budget.

One live writer owns a file. Serialize same-file work. Subagents never commit,
push, publish, deploy, perform destructive actions, or mutate external systems.
Inspect returned diffs and evidence before integrating or editing a returned
path.

## 4. Protect Root Context And Recover Deliberately

Delegate broad discovery, long logs, inventories, and repeated test monitoring
to Luna and require a distilled result. Prefer bounded commands and exact
anchors. Reuse a useful leaf for a related follow-up. After two repetitions of
the same command or wait path without new evidence, stop and replan.

For a failure, capture the exact stage and error, identify whether source,
generated state, environment, authorization, or an external dependency owns it,
then apply a source-grounded correction or materially different safe path.
Rerun the affected gate and every downstream gate invalidated by the change.

## 5. Git Completion

For authorized implementation or remediation that changes a Git repository,
scoped commit and push are a standing terminal condition. On an existing
task-aligned feature branch, commit the task-owned diff and push its configured
upstream. On a default, detached, mismatched, or unsafe branch, create
`agent/<task-slug>` from the correct base and push it. Never force-push, and
never push directly to the default branch without explicit instruction.

Before staging, inspect dirty files and ahead-of-upstream history. Use explicit
paths or hunks, never `git add -A` in a mixed tree. If ownership overlaps or
unrelated commits would be published, use an isolated worktree or clone and
apply only the task diff.

Completion requires a local task-only commit, successful push, and remote-ref
verification: the remote head must equal the local SHA, or, if it advanced
concurrently, the task commit must be an ancestor. Never bypass authentication,
branch protection, hooks, or non-fast-forward safeguards. Explicit `do not
commit`, `leave uncommitted`, `no push`, `commit only`, `keep local`, and
equivalent constraints override this default. Pull requests, merges, releases,
and deployments remain separately authorized.

## 6. Enforce Terminal Criteria

Before finalizing, require every applicable gate:

- intended source and only intended files changed;
- focused tests, lint, type checks, formatting, and `git diff --check` pass;
- generated artifacts, manifests, builds, packages, and runtime smoke match
  their source and target;
- realistic negative, compatibility, security, performance, and failure paths
  are covered in proportion to risk;
- durable corrections and instruction drift are classified through
  `instruction-learning-loop` and its disposition is reported;
- authorized external mutation and remote verification completed;
- residual risks and intentionally deferred work are explicit.

When this skill, `config.toml`, or a custom profile changes, run:

```powershell
$env:CODEX_ROUTING_HOME = (Resolve-Path .).Path
python -B .\skills\delivery-orchestration\scripts\test_routing_policy.py
Remove-Item Env:CODEX_ROUTING_HOME
```

Return a final answer only when the terminal condition is satisfied or a
concrete external blocker remains after safe recovery paths are exhausted.

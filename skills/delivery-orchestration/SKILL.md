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

The root coordinates on `gpt-6-astra`/`low` and owns routing, decisions,
integration, authorized external actions, and final verification. Choose the
least expensive route that preserves the context, judgment, ownership, and
evidence needed for a verified result. The root remains accountable for final
whole-deliverable engineering approval; Astra-high advisor/reviewer findings
are inputs to root disposition and sign-off.

## 1. Define the delivery contract

Before editing, record a compact contract covering outcome, acceptance
criteria, non-goals, owned paths and targets, authorization boundaries, dirty
baseline, required gates, terminal condition, assumptions, and blockers. A
plan, edit, focused test, build, upload, commit, or push is intermediate until
the terminal condition is met.

## 2. Route Work By Task Shape

At decomposition, when new evidence changes the work, at a bottleneck, and
before integration, check whether a bounded packet would materially improve
throughput, isolation, context use, or evidence. Parallelize only genuinely
independent useful packets. Keep tiny or serial cheaper work inline when
handoff, packet context, retries, review, or root rework costs more than it
returns; do not create artificial parallel work to fill a count.

For authorized external mutation, the root confirms the exact target, expected
effect, low-impact boundary, preflight, postcondition, rollback, and remote
verification. Leaves cannot mutate external systems.

For material delivery, dispatch a bounded terminal leaf when it protects root
context, advances independent work, or strengthens evidence. Normally use one
to three active leaves; six spawned threads is the ceiling and the root is not
counted. Every leaf reports directly to the root and has zero descendant
budget. Reuse an idle or completed same-purpose leaf before spawning a
replacement, and preserve the root-owned MCP boundary.

### Spark fast path

Use `spark_scanner`/`spark_worker` at xhigh only for tiny exact packets with
explicit anchors, exclusive ownership, focused checks, and cheap rollback.
Dispatch `fork_turns = "none"` with a fresh self-contained packet; do not send
broad discovery or synthesis to Spark. Consult the current model catalog for
context limits instead of hardcoding them. Escalate when scope, ambiguity, or
context pressure grows.

### Luna default

Luna is the default delegated model: use `luna_scanner` at medium for broad or
context-heavy read-only discovery and independent evidence, `luna_fast_worker`
at xhigh for bounded routine implementation, and `luna_worker`
at max for substantial implementation, debugging, tests,
documentation, and integration. Return exact anchors, uncertainty, and
unexamined areas; the root owns conflicting evidence and consequential
interpretation.

### Astra escalation and independent review

Use `astra_worker` (Astra medium) for genuinely difficult, ambiguous,
security-sensitive, or cross-layer work. Move directly when the task warrants
it; do not require a failed Luna attempt. Use the named `sol_fast_worker`
(`gpt-5.6-sol`/`low`) for simpler, tightly specified, low-ambiguity work blocking
the critical path with clear focused verification. Use a fresh self-contained
packet; never use `astra_worker` as that model selector. Root oversight does not
justify assigning work beyond the leaf's capability.

Only the depth-0 root dispatches `astra_advisor` or `astra_reviewer` (Astra high).
Use them for an explicit independent-review request or a named consequential
risk. An early or plan checkpoint reviews the approach without requiring
implementation evidence. Final-delivery checkpoints follow fresh verification
and include the integrated diff and
actual applicable test, build, and runtime evidence. Reviewers return findings
and an engineering verdict; the root owns disposition, authorization, and whole-deliverable
approval. Do not trigger review solely from file count, stage count, or an
instruction-file change.

See [delegation topology](references/delegation-topology.md) for the matrix,
cost observations, packet contract, and risk triggers.

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
anchors. Reuse a useful leaf for a related follow-up. Use bounded monitoring
and replan when progress stalls; do not stop productive long-running work
solely because a wait or observation repeated. Use the topology's
cost-to-complete model, including handoff, context, retries, review, root
rework, and critical-path delay, to choose foreground versus background work.

For a failure, capture the exact stage and error, identify whether source,
generated state, environment, authorization, or an external dependency owns it,
then apply a source-grounded correction or materially different safe path.
Rerun the affected gate and every downstream gate invalidated by the change.

Keep defects and failures required to make the current objective safe in the
same task. Once the current objective is safe, treat a genuinely distinct
objective as a fresh task boundary: recommend the boundary, but create a fresh
task only when the user explicitly requests it. Keep iteration evidence in
machine-readable verification receipts, not a diary entry for every iteration;
reserve diary entries for durable discoveries that will help later work.

## 5. Git Completion

For authorized implementation or remediation that changes a Git repository,
scoped commit and push are a standing terminal condition. First apply any
explicit user or repository branch policy; it takes precedence over this
generic routing. On an existing task-aligned feature branch, commit the
task-owned diff and push its configured upstream. Use `agent/<task-slug>` only
when no applicable policy permits direct default-branch work, or when the
branch is detached, mismatched, or otherwise unsafe; create it from the
correct base and push it. Never force-push or silently override a repository
policy. A policy-permitted default-branch delivery still requires the same
scoped diff, safeguards, commit, push, and remote-ref verification below.

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

Root-routed independent review is risk-triggered as defined in the topology.
After fresh verification, use the read-only Astra-high `astra_advisor` or
`astra_reviewer` for an explicit request or named consequential risk. Provide a
root-prepared evidence packet; the root owns finding disposition and final
whole-deliverable approval. Do not review solely for file/stage counts or an
instruction-file change. Optional review failure is reported; only a required
high-risk review failure blocks delivery.

When this skill, `config.toml`, or a custom agent profile changes, run:

```powershell
$env:CODEX_ROUTING_HOME = (Resolve-Path .).Path
python -B .\skills\delivery-orchestration\scripts\test_routing_policy.py
Remove-Item Env:CODEX_ROUTING_HOME
```

Return a final answer only when the terminal condition is satisfied or a
concrete external blocker remains after safe recovery paths are exhausted.

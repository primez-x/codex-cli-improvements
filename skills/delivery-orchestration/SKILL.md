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

Keep the configured Sol Medium root focused on the outcome, decisions,
integration, and final verification. Route each delegated task to the cheapest,
fastest model-effort profile that can satisfy its context, judgment, ownership,
and verification needs.

This skill explicitly requests proactive subagent delegation for every material
delivery task. Do not wait for the user to ask for agents or manage routing.

## 1. Define The Delivery Contract

Before editing, record a compact working contract:

- requested outcome and acceptance criteria;
- in-scope systems, repositories, and external targets;
- explicit authorization boundaries;
- current source and dirty-worktree baseline;
- required source, test, build, generated-output, runtime, and release gates;
- terminal condition and current blockers.

Treat the user's outcome as the active objective across turns. A plan, local
edit, passing unit test, Git push, package upload, or prior failed attempt is an
intermediate state unless it satisfies the terminal condition.

## 2. Route Work By Task Shape

A task is material when any of these is true:

- more than one file or one independent concern is likely to change;
- code and tests, generated output, documentation, or configuration must align;
- the task crosses UI, model, service, server, package, or deployment layers;
- a build, package, install, migration, release, or live smoke is required;
- discovery, logs, or repeated commands would materially pollute root context;
- failure recovery, compatibility, security, permissions, or data integrity
  needs independent challenge.

For a material task, dispatch at least one bounded agent before the root
accumulates bulk evidence or command output. A non-material quick edit may also
use the Spark fast path when dispatch is faster than retaining it on the root.

### Spark fast path

For fast-path work, use `spark_scanner` at high effort or `spark_worker` at xhigh effort only when
every gate is true:

- the question, deliverable, and target files or symbols are explicit;
- required context is small and localized;
- no architecture, product, compatibility, security, or ownership decision is
  unresolved;
- success is mechanically verifiable with a focused check;
- failure is cheap, reversible, and cannot silently damage adjacent behavior.

Spark never coordinates. If any gate fails, or its task discovers ambiguity or
expanding scope, it stops and returns the evidence to its parent.

### Default and escalation routes

Luna is the default for delegated work that is routine but needs multi-step
tool use, broader context, or judgment. For routine work, use `luna_scanner` at medium effort and `luna_worker` or `luna_coordinator` at high effort.

Use Terra at medium effort for ambiguous, multi-file, cross-layer, or
integration-heavy work that exceeds a bounded Luna assignment. Use
`sol_worker` at xhigh for rare difficult implementation or diagnosis. Use
`sol_advisor` or `sol_coordinator` at max only for consequential adversarial
review, architecture, security, concurrency, persistence, difficult failure
recovery, or a Sol-supervised subtree.

Profiles use their configured efforts; agents escalate the model rather than
making ad-hoc effort changes. Correct an otherwise sound task packet once; when
capability, context, or semantic risk is the constraint, escalate the model
from Spark to Luna, Luna to Terra, or Terra to Sol. Max effort is reserved for
the Sol advisor and coordinator profiles, not routine work.

Use a coordinator only when its bounded subtree clearly reduces root work.
The root chooses models, effort, and depth automatically and never asks the
user to manage routing.

If concurrent writing is unsafe, keep one writer and delegate a read-only
source comparison, test run, output verification, or failure analysis. A dirty
worktree is not a reason to avoid all delegation.

Keep normal work to one to three active children. Add depth or agents only for
distinct work packages with material value.

Follow [delegation topology](references/delegation-topology.md) for model,
effort, depth, subtree, and concurrency ceilings.

## 3. Assign Ownership Precisely

Give every writer a self-contained packet containing:

- exact exclusive `owned_paths`;
- requested behavior and non-goals;
- authoritative source and applicable instructions;
- expected interfaces with root- or sibling-owned work;
- focused verification;
- evidence and output format;
- stop conditions and subtree budget.

One live writer owns a file. Serialize same-file work. Reserve integration
files for the root or one coordinator. Subagents never commit, push, publish,
deploy, or perform destructive or external actions.

Scanner/advisor no-edit rules remain behavioral boundaries even when a parent
permission mode is not mechanically read-only. Use parent read-only mode when
isolation is required and inspect the worktree or external evidence afterward.

Inspect returned evidence and diffs. Reconcile conflicts, steer gaps, and
return ownership before editing a child-owned path.

## 4. Protect Root Context

Do not make the root consume long searches, build logs, repeated wait output,
or broad test traces when a scanner or worker can return a distilled result.

- Prefer bounded commands and focused output.
- Delegate long-running build/test monitoring when external action is not
  involved.
- After two repetitions of the same command or wait path without new evidence,
  stop and replan instead of continuing the loop.
- After a context compaction, reconstruct the delivery contract and current
  terminal state before acting.
- Reuse an existing agent for a related follow-up rather than spawning a fresh
  replacement.

## 5. Recover From Failure Without Goal Drift

Treat each failure as evidence:

1. Capture the exact failing stage, command, artifact, target, and current
   error.
2. Determine whether source, generated state, environment, authorization, or an
   external dependency owns the failure.
3. Delegate a bounded independent diagnosis when the cause is not immediate.
4. Apply a source-grounded correction or try a materially different safe path.
5. Re-run the affected gate and every downstream gate invalidated by the
   correction.

A failure from an earlier artifact or attempt is not proof that the current
artifact will fail. Re-attempt an authorized build/install/deploy after material
state changes. Do not retry unchanged operations indefinitely.

Stop only when completion requires new authority, unavailable user input, or an
external-state change and safe in-scope diagnostics and alternatives are
exhausted. Report the exact blocker and the evidence needed to resume.

## 6. Enforce Terminal Criteria

Before finalizing, compare the result with the delivery contract. Require all
applicable gates:

- intended source and only intended files changed;
- focused tests, lint, type checks, formatting, and diff sanity pass;
- generated artifacts and manifests match their source;
- build/package/output checks pass;
- compatibility, security, accessibility, performance, and failure paths are
  covered in proportion to risk;
- durable corrections, repeated failures, and instruction drift are classified
  through `instruction-learning-loop`, with its disposition reported;
- authorized external mutation completed on the named target;
- health check and representative no-save runtime or visual smoke pass;
- residual risks and intentionally deferred work are explicit.

When this skill, `config.toml`, or a custom agent profile changes, run:

```powershell
python "$HOME\.codex\skills\delivery-orchestration\scripts\test_routing_policy.py"
```

Cheap agents may execute and monitor tests, builds, and other verification.
The root validates their command scope, distilled evidence, and terminal-gate
disposition; it does not need to personally stream every log or wait loop.

For an authorized release, do not call the result live after only a commit, Git
push, build, archive upload, or package upload. Installation and live smoke are
separate required evidence. Name the target whenever saying that something was
pushed or deployed.

Return a final answer only when the terminal condition is satisfied or a
concrete external blocker remains after the recovery procedure.

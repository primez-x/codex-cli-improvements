# Delegation Topology

Root is depth 0 on GPT-6.1 Sol medium. The maximum absolute depth is 2, a ceiling
rather than a required hierarchy. Normally use one to three useful delegates.
All branches share six concurrently open spawned threads, excluding root;
honor any lower runtime limit.

Use root (depth 0) → workstream worker (depth 1) → terminal leaf (depth 2).
This ceiling matches the demonstrated runtime behavior. Keep `max_depth = 2`
for runtimes that honor the setting; instructions enforce the same limit.
Do not infer a universal product maximum from one client. If child spawning
is unavailable, return the bounded packet to root for direct dispatch.

Sol profiles use GPT-6.1 Sol. All Luna profiles use GPT-6 Luna. These bindings
express this kit's routing policy; dispatch only models available in the current
runtime. Select cross-provider targets with [model-routing.md](model-routing.md).
Without cross-provider Claude dispatch, use `astra_advisor` when the model is available to the current runtime.

## Roles

| Profile | Model | Effort | Depth | Delegation |
| --- | --- | --- | --- | --- |
| `luna_scanner` | gpt-6-luna | medium | 1–2 | Terminal discovery and evidence |
| `luna_fast_worker` | gpt-6-luna | xhigh | 1–2 | Terminal bounded implementation |
| `luna_worker` | gpt-6-luna | xhigh | 1–2 | May subdivide at depth 1 |
| `sol_fast_worker` | gpt-6.1-sol | low | 1–2 | Terminal bounded routine implementation on the critical path |
| `sol_worker` | gpt-6.1-sol | high | 1–2 | May subdivide at depth 1 |
| `sol_medium_worker` | gpt-6.1-sol | medium | 1–2 | Terminal bounded implementation needing GPT-6.1 Sol judgment |
| `astra_advisor` | gpt-6-astra | high | 1 | fallback when the applicable Claude advisor is unavailable, exhausted, or excluded from independent review; root-dispatched terminal critic |

Route by tier. Luna serves the lower tiers: medium for read-only discovery, and xhigh
for decided mechanical edits and partitioned workstreams. Sol serves routine and
substantial work. Use low for bounded routine implementation on the critical path,
medium for bounded judgment, and high for substantial or difficult implementation.
No profile uses Max. Use `luna_scanner` for small read-only checks and
`luna_fast_worker` for decided mechanical edits. Use a fresh self-contained packet
with `fork_turns = "none"` when isolation is useful, exact anchors, narrow reads, and a
short evidence return. Keep tiny serial work inline when handoff costs more. Use only
profiles and models actually available in the current runtime.

Partition independent work once and avoid duplicated discovery. Root or a capable
workstream owner reconciles cross-file relationships. Use `luna_worker` when
partitioning would repeat large context or hide dependencies. `sol_medium_worker`
supplies bounded GPT-6.1 Sol judgment without the high effort cost and is terminal.

## Ownership And Subdivision

- Give every assignment its current absolute depth, scope, exclusive paths,
  constraints, interfaces, and expected evidence. Unknown depth must be resolved
  with the parent before spawning.
- Only `luna_worker` and `sol_worker` may subdelegate at depth 1.
  Select the least expensive capable child for independent useful work;
  a narrower assignment may require terminal execution.
- Children receive subsets of the parent's scope and authority. The parent
  stops writing delegated paths until the child returns ownership. No live
  writers overlap. Do not build coordinator-only chains.
- Every depth-2 agent is terminal. Scanners and fast workers remain
  terminal at any depth. Advisor requests return to root for direct dispatch.
- Reserve capacity within the shared six-thread limit before spawning.
  Report child identities, ownership, progress, and evidence to the parent.
  If slots are unavailable, continue useful local work or await progress.
- Reuse compatible agents and monitor meaningful progress. Return distilled
  results rather than full logs; the root owns consequential synthesis.
- Root alone owns Git, destructive operations, repository-wide generators,
  final integration, publication, deployment, and external mutations.
  Child profiles keep root-owned local MCP servers disabled.

## Cost And Capability

Choose by total cost to a verified result: context preparation, handoffs,
runtime, retries, review, parent/root rework, and critical-path delay.
Delegate regularly when it improves time, cost, context, or quality. Keep tiny
serial work inline when handoff costs more. Root review does not justify
assigning a task beyond a child's capability.

The user selected GPT-6.1 Sol for root and difficult implementation based on observed cost and performance.
Use Claude Opus high for Sol/Codex and all other non-Opus roots. Reserve Fable high for Opus roots. Explicit user model requests take precedence within the capability, independence, effort, and Astra fallback rules. Use Astra high only when the applicable Claude advisor is unavailable, exhausted, or excluded from independent review, and Astra is dispatchable.
Earlier model benchmark snapshots
do not establish performance or pricing for these versions. Revisit routing
using actual first-pass quality, elapsed time, retries, and cost when available.

## Approval

GPT-6.1 Sol root reviews and approves every integrated outcome. Use one independent
advisor when requested or a concrete consequential risk warrants independent challenge,
following `adversarial-code-review`. Use Claude Opus high for Sol/Codex and all other non-Opus roots. Reserve Fable high for Opus roots. Explicit user model requests take precedence within the capability, independence, effort, and Astra fallback rules. Use Astra high only when the applicable Claude advisor is unavailable, exhausted, or excluded from independent review, and Astra is dispatchable. Do not add review solely for file count,
stage count, or instruction-file edits. A required high-risk review remains
a delivery gate; an optional review failure does not block verified low-risk work.

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

## Roles

| Profile | Model | Effort | Depth | Delegation |
| --- | --- | --- | --- | --- |
| `luna_scanner` | gpt-6-luna | medium | 1–2 | Terminal discovery and evidence |
| `luna_fast_worker` | gpt-6-luna | xhigh | 1–2 | Terminal bounded implementation |
| `luna_worker` | gpt-6-luna | max | 1–2 | May subdivide at depth 1 |
| `sol_fast_worker` | gpt-6.1-sol | low | 1–2 | Terminal clear critical-path work |
| `sol_worker` | gpt-6.1-sol | high | 1–2 | May subdivide at depth 1 |
| `sol_low_worker` | gpt-6.1-sol | low | 1–2 | Terminal bounded implementation needing Sol judgment |
| `sol_advisor` | gpt-6.1-sol | xhigh | 1 | Root-dispatched terminal independent critic |
| `spark_scanner` | gpt-5.3-codex-spark | xhigh | 1–2 | Preferred tiny exact or bounded instruction check |
| `spark_worker` | gpt-5.3-codex-spark | xhigh | 1–2 | Preferred small mechanical edit |

Luna is the default. Use xhigh for bounded routine work and max for substantial
implementation. Sol low is a latency option for tightly specified work blocking
progress. Use Sol high directly when difficult work needs its judgment.
Use Spark often for eligible bounded work, making productive use of the separate
allowance reported by the user. It needs a fresh self-contained packet with
`fork_turns = "none"`, exact anchors, narrow reads, and a short evidence return.
Do not give it broad discovery, full histories, or large logs. At context pressure
or scope growth, return the remaining gap for splitting or rerouting; avoid
repeated compaction or extending a nearly full Spark thread. Capability and
account availability still govern eligibility.
Use only profiles/models actually available in the current runtime.

Do not fork threads. Every new assignment receives a fresh self-contained packet. Continue or resume the same assignment only within its 30-minute cache window; after that, return to the owning parent for a new packet. Use registered profiles for every dispatch.
Only the two workstream profiles may fan out at depth 1; prefer capable Spark
or cheaper Luna children for bounded discovery and checks.

Broad coverage can use multiple bounded Spark packets when each is independently
understandable. Partition once and avoid duplicated discovery. Sol or a capable
workstream owner reconciles cross-file relationships. Use Luna when partitioning
would repeat large context or hide dependencies. `sol_low_worker` supplies
bounded Sol judgment without the high effort cost and remains terminal.

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
- Every depth-2 agent is terminal. Scanners, fast workers, and Spark remain
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

The user selected GPT-6.1 Sol for root, difficult implementation, and review
based on observed cost and performance. Earlier model benchmark snapshots
do not establish performance or pricing for these versions. Revisit routing
using actual first-pass quality, elapsed time, retries, and cost when available.

## Approval

Sol root reviews and approves every integrated outcome. Use one independent
`sol_advisor` when requested or a concrete consequential risk warrants it,
following `adversarial-code-review`. Do not add review solely for file count,
stage count, or instruction-file edits. A required high-risk review remains
a delivery gate; an optional review failure does not block verified low-risk work.

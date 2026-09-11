# Delegation Topology

Root is depth 0 on GPT-5.6 Luna XHigh. The maximum absolute depth is 2. Depth-1
agents may spawn useful depth-2 registered profiles; depth-2 agents are terminal
and no child may spawn beyond depth 2 or fork another thread. Continue or resume
the same assignment only within its 30-minute cache window; after that, the
owning parent dispatches a fresh packet. Normally use one to three useful
delegates per parent.
All branches share six concurrently open spawned threads, excluding root;
honor any lower runtime limit.

Use root at depth 0, then subagents at depth 1 and terminal subagents at depth
2. Keep `max_depth = 2` for runtimes that honor the setting, and enforce the
same limit in every profile.
Do not infer a universal product maximum from one client. If a task would
require another level, return the gap to the owning parent rather than
exceeding depth 2.

## Roles

| Profile | Model | Effort | Depth | Delegation |
| --- | --- | --- | --- | --- |
| `luna_scanner` | gpt-5.6-luna | medium | 1 or 2 | Discovery and evidence; terminal at depth 2 |
| `luna_fast_worker` | gpt-5.6-luna | xhigh | 1 or 2 | Bounded implementation; terminal at depth 2 |
| `luna_worker` | gpt-5.6-luna | max | 1 or 2 | Substantial implementation; terminal at depth 2 |
| `sol_fast_worker` | gpt-5.6-sol | low | 1 or 2 | Clear critical-path work; terminal at depth 2 |
| `astra_worker` | gpt-6-astra | medium | 1 or 2 | Difficult implementation or diagnosis; terminal at depth 2 |
| `astra_low_worker` | gpt-6-astra | low | 1 or 2 | Bounded Astra judgment; terminal at depth 2 |
| `astra_advisor` | gpt-6-astra | high | 1 or 2 | Independent critic; terminal at depth 2 |
| `spark_scanner` | gpt-5.3-codex-spark | xhigh | 1 or 2 | Preferred tiny exact check; terminal at depth 2 |
| `spark_worker` | gpt-5.3-codex-spark | xhigh | 1 or 2 | Preferred small mechanical edit; terminal at depth 2 |

The Luna XHigh root is the orchestrator. Use Astra medium as the default capable
code and diagnosis worker, and Astra high for an independent review when the
request or risk warrants it. Keep Luna xhigh for bounded routine work and Luna
max available for substantial work. Sol low is a latency option for tightly
specified work blocking progress. Use Spark often for eligible bounded work,
making productive use of the separate allowance reported by the user. Every
new assignment needs a fresh self-contained packet with `fork_turns = "none"`
and a short evidence return. Continue or resume an existing assignment only
within its 30-minute cache window. A depth-1 agent may spawn a depth-2 child
when useful, but every child must use a registered profile and these same rules;
depth-2 agents cannot spawn further. Prefer Spark or cheaper Luna profiles for
bounded fan-out before costly self-discovery when they are capable. Spark packets
additionally require exact anchors and narrow reads; do not give Spark broad
discovery, full histories, or large logs. At context pressure or scope growth,
return the remaining gap to the owning parent; avoid repeated compaction or
extending a nearly full thread. Capability and account availability still govern
eligibility.

The continuation window is 30 minutes for every profile, including Sol. A
continuation or resume must stay within that window; after it expires, the
owning parent sends a fresh packet.
Use only profiles/models actually available in the current runtime.

Broad coverage can use multiple bounded packets when each is independently
understandable. Partition once and avoid duplicated discovery. The owning parent
reconciles cross-file relationships. Use a fresh packet when another assignment
is needed; do not fork a child thread or continue past the cache window.
`astra_low_worker` supplies bounded Astra judgment without the medium effort cost.

## Ownership And Subdivision

- Give every assignment its current absolute depth, scope, exclusive paths,
  constraints, interfaces, and expected evidence. Unknown depth must be resolved
  with the parent before spawning.
- Depth-1 subagents may subdelegate to depth 2 when useful; depth-2 subagents
  may not subdelegate. No subagent may fork. Select the least expensive capable
  registered profile for each independent useful assignment and send a fresh
  packet.
- Children receive subsets of the parent's scope and authority. The parent
  stops writing delegated paths until the child returns ownership. No live
  writers overlap. Do not build coordinator-only chains.
- Every depth-2 agent is terminal. Depth-1 scanners, workers, fast workers, and
  Spark may return to their parent after optional depth-2 fan-out; advisor
  requests are dispatched by the root or an authorized depth-1 reviewer.
- Reserve capacity within the shared six-thread limit before spawning.
  Report child identities, ownership, progress, and evidence to the parent.
  If slots are unavailable, continue useful local work or await progress.
- Reuse compatible profiles, but start each new assignment with a fresh packet.
  Continue or resume only the same assignment within the 30-minute cache window.
  Monitor meaningful progress within that assignment and return distilled
  results rather than full logs; the owning parent synthesizes, with root owning
  consequential integration.
- Root alone owns Git, destructive operations, repository-wide generators,
  final integration, publication, deployment, and external mutations.
  Child profiles keep root-owned local MCP servers disabled.

## Cost And Capability

Choose by total cost to a verified result: context preparation, handoffs,
runtime, retries, review, parent/root rework, and critical-path delay.
Delegate regularly when it improves time, cost, context, or quality. Keep tiny
serial work inline when handoff costs more. Root review does not justify
assigning a task beyond a child's capability.

These are user-supplied workload observations, not official prices or universal
task-quality guarantees:

| Route | Intelligence score | Cost/task | Wall time/task |
| --- | ---: | ---: | ---: |
| Luna xhigh | 35 | $0.085 | 3.6 min |
| Luna max | 38 | $0.18 | 6.3 min |
| Sol low | 34 | $0.26 | 1.2 min |
| Astra low | 46 | $0.82 | 1.5 min |
| Astra medium | 50 | $1.54 | 3.6 min |
| Astra high | 51 | $1.72 | 4.0 min |
| Sol high (comparison only) | 42 | $0.81 | 3.8 min |

Astra high adds $0.18 and 0.4 minutes over medium in this snapshot. Keep high
for consequential independent judgment. Revisit routing using actual
first-pass quality, elapsed time, retries, and cost when available.

## Approval

The Luna XHigh root reviews and approves every integrated outcome. Use one independent
`astra_advisor` when requested or a concrete consequential risk warrants it,
following `adversarial-code-review`. Do not add review solely for file count,
stage count, or instruction-file edits. A required high-risk review remains
a delivery gate; an optional review failure does not block verified low-risk work.

# Delegation Topology And Cost Ceilings

The root coordinates at depth 0 on `gpt-6-astra`/`low`. Eight general-purpose
profiles remain terminal depth-1 leaves reporting directly to the root. The
on-demand `astra_reviewer` identity is also depth 1 and is dispatched only for
explicit or consequential review. `max_depth = 1` is both the configured and
behavioral boundary: leaves do not spawn.

## Model And Effort Matrix

| Profile | Named model | Effort | Allowed depth | Purpose |
| --- | --- | --- | --- | --- |
| Spark scanner | gpt-5.3-codex-spark | xhigh | 1 | Tiny exact read-only evidence from a bounded packet |
| Spark worker | gpt-5.3-codex-spark | xhigh | 1 | Small localized mechanical edits with focused checks |
| Luna scanner | gpt-5.6-luna | medium | 1 | Broad discovery, large-context evidence, and validation |
| Luna fast worker | gpt-5.6-luna | xhigh | 1 | Economical bounded routine implementation |
| Luna worker | gpt-5.6-luna | max | 1 | Default substantial implementation and verification |
| Astra worker | gpt-6-astra | medium | 1 | Rare difficult, ambiguous, security-sensitive, or cross-layer work |
| Sol fast worker | gpt-5.6-sol | low | 1 | Simpler, tightly specified, low-ambiguity critical-path packet with focused verification |
| Astra advisor | gpt-6-astra | high | 1 | Rare consequential adversarial challenge and sign-off |
| On-demand `astra_reviewer` | gpt-6-astra | high | 1 | Consequential post-verification review; not routine routing |

Active Astra roles use `astra_worker`, `astra_advisor`, and `astra_reviewer`.
Luna medium is the discovery route, Luna xhigh handles bounded routine work,
and Luna max handles more substantial implementation. Astra medium replaces the former Sol
xhigh worker tier; Astra high replaces former Sol max advice/review. The
`sol_fast_worker` identity provides the named Sol-low latency route without
changing the Luna default.
Former Sol-high work maps to the Astra-low root during migration; treat that
as a root-selected capability candidate, not a new leaf profile.

## Optional Leaf Identity Metadata

For observability or an audit packet, the root may attach deterministic identity
metadata to a direct depth-1 assignment. Use the pure helper in
`scripts/agent_identity.py` to normalize the purpose and derive a stable
`d1_<profile>_<purpose_slug>` task name plus a human-readable display label.
This metadata is optional, carries no ownership or work result, and must not be
treated as a runtime UI requirement. A roster update, when useful, is a
separate `ROSTER_DELTA_V1` envelope containing exactly
`canonical_task_path`, `task_name`, `display_label`, and `status`; statuses are
`active`, `completed`, `failed`, or `terminated`. Work and evidence still use
the ordinary direct-parent return path.

## Delegation Checkpoints And Cost

At decomposition, when new evidence changes the work, at a bottleneck, and
before integration, check whether a bounded packet can move useful independent
work off the critical path. Parallelize only actual independent packets. Keep a
tiny or serial cheaper step inline when handoff, context transfer, retries,
review, or root rework cost more than delegation returns.

Choose by total cost-to-complete: packet preparation and context, handoff,
runtime, retries, review, root rework, and elapsed critical-path delay all
count. Put independent evidence in the background only when it does not delay
integration. The root owns conflicting evidence, consequential synthesis, and
final decisions.

For a simpler, tightly specified, low-ambiguity packet with clear verification
blocking the critical path, dispatch the named
`sol_fast_worker` identity, whose explicit model is `gpt-5.6-sol` at `low`
effort. Use a fresh self-contained packet. The `astra_worker` identity
remains registered to Astra medium; do not use that alias as the model
selector. Luna max has the higher intelligence index in the user's data;
Sol low is not an interchangeable substitute for all Luna work. Root review
does not justify underqualified assignments.

The following are user-provided workload observations from 2026-09-10, starting
estimates rather than verified universal metrics. Comparable quality outside
these observations is unknown; the Sol-high row is comparison data, not a
routine route.

| Route | Observed intelligence score | Observed cost/task | Observed wall time/task |
| --- | ---: | ---: | ---: |
| Luna xhigh | 35 | $0.085 | 3.6 min |
| Luna max | 38 | $0.18 | 6.3 min |
| Sol low | 34 | $0.26 | 1.2 min |
| Astra low | 46 | $0.82 | 1.5 min |
| Astra medium | 50 | $1.54 | 3.6 min |
| Astra high | 51 | $1.72 | 4.0 min |
| Sol high (comparison only) | 42 | $0.81 | 3.8 min |

On this snapshot, Astra high adds $0.18 and 0.4 minutes over medium for one
index point. Prefer medium for difficult delegated implementation and reserve
high for consequential judgment or required review. These index differences
do not prove task-level quality or justify skipping capability checks. Luna
remains the primary implementation route; Astra low remains the root default.

## Context And Packet Rules

Spark has a smaller context window than larger profiles; consult the current
model catalog for usable limits instead of hardcoding sizes. Every Spark
dispatch uses `fork_turns = "none"` and a fresh self-contained bounded packet
containing:

- one exact question or small deliverable;
- explicit paths, symbols, or other anchors;
- exclusive owned paths for a writer;
- constraints and non-goals;
- the focused command or observable evidence expected; and
- stop conditions requiring Luna escalation when scope, ambiguity, or context
  grows.

Do not send broad discovery or synthesis to Spark. Use Luna medium for broad
read-only discovery, Luna xhigh for bounded routine work, and Luna max for
substantial work. Route directly to Astra medium when evidence indicates
difficult work needs that capability; do not require a failed cheaper attempt. Use Astra high
advice/review only for a named consequential risk, explicit request, or the
independent high-risk triggers: security, authentication, credentials, privacy,
destructive or irreversible action, migration, persistence, data integrity,
concurrency, production or external impact, major architecture, compatibility,
public-contract change, conflicting evidence, a stuck approach, or repeated
failed verification.

## Final Approval And Ownership

Every whole deliverable receives engineering approval from the Astra-low root or
an Astra-high advisor/reviewer. The root remains accountable for integration and
disposition even when independent review is used. Do not trigger review solely
for file count, stage count, or the presence of an instruction file. Optional
review infrastructure failure is reported; only a required high-risk review
failure blocks delivery.

- Normal work uses one to three active leaves.
- The ceiling is six spawned threads; the root is not counted.
- Every leaf has descendant budget zero and reports directly to the root.
- One live writer owns a file; serialize overlaps and reserve integration for
  the root.
- Leaves never commit, push, publish, deploy, perform destructive actions, or
  mutate external systems.
- Every writer receives a fresh self-contained packet with exclusive paths,
  constraints, expected evidence, and stop conditions.

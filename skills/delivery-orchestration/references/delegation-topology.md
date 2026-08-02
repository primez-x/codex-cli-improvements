# Delegation Topology And Cost Ceilings

The Sol Medium root is depth 0. The six general-purpose routing profiles are
terminal depth 1 leaves that report directly to the root. The gate-only
`sol_reviewer` identity is also depth 1 but is dispatched only by the managed
adversarial gate, not by normal routing. `max_depth = 1` is both the configured
and behavioral boundary: leaves do not spawn.

## Model And Effort Matrix

| Profile | Effort | Allowed depth | Purpose |
| --- | --- | --- | --- |
| Spark scanner | xhigh | 1 | Tiny exact read-only evidence from a bounded packet |
| Spark worker | xhigh | 1 | Small localized mechanical edits with focused checks |
| Luna scanner | medium | 1 | Broad discovery, large-context evidence, and validation |
| Luna worker | max | 1 | Default substantial implementation and verification |
| Sol worker | xhigh | 1 | Rare genuinely difficult implementation or diagnosis |
| Sol advisor | max | 1 | Rare consequential adversarial challenge and sign-off |
| Gate-only `sol_reviewer` | max | 1 | Mandatory post-verification review; not a routing profile |

The six general-purpose routing efforts are fixed per profile. The gate-only
reviewer is fixed at Sol/max and is not an escalation tier. Route by task shape
and escalate the model rather than changing effort ad hoc: Spark fast path, Luna
default, then Sol only for difficulty or consequential risk.

## Context And Packet Rules

Spark is optimized for latency but has materially less context than the 5.6
profiles. The current catalog advertises about 128k tokens for Spark and 272k
for 5.6, with effective usable limits reduced by system overhead. Never use
Spark as a repository explorer simply because it is fast.

Every Spark dispatch uses `fork_turns = "none"` and a fresh self-contained,
bounded packet containing:

- one exact question or small deliverable;
- explicit paths, symbols, or other anchors;
- exclusive owned paths for a writer;
- constraints and non-goals;
- the focused command or observable evidence expected;
- stop conditions requiring Luna escalation when scope, ambiguity, or context
  grows.

Use Luna Medium scanning for broad discovery and Luna Max for default delivery;
the scanner returns anchored facts while the root owns consequential synthesis.
Use Sol XHigh work only after Luna is genuinely insufficient; use Sol Max advice
only for a named consequential risk or checkpoint. The gate-only `sol_reviewer`
is invoked after fresh verification for material deliveries and emits only
`ReviewOutputV1`; the gate creates the local receipt.

## Concurrency And Ownership

- Normal work uses one to three active leaves.
- The ceiling is four spawned threads; the root is not counted in that setting.
- Every leaf has descendant budget zero.
- One live writer owns a file. Serialize overlaps and reserve integration for
  the root.
- Leaves never commit, push, publish, deploy, perform destructive actions, or
  mutate external systems.
- Prefer self-contained packets even for 5.6 profiles; use inherited history
  only when it is materially useful and safely within context.

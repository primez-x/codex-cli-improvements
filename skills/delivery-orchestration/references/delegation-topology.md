# Delegation Topology And Cost Ceilings

The Sol Low root is depth 0. The six general-purpose routing profiles are
terminal depth 1 leaves that report directly to the root. The on-demand
`sol_reviewer` identity is also depth 1 and is dispatched by the root only for
explicit or consequential review, not normal routing. `max_depth = 1` is both
the configured and behavioral boundary: leaves do not spawn.

## Model And Effort Matrix

| Profile | Effort | Allowed depth | Purpose |
| --- | --- | --- | --- |
| Spark scanner | xhigh | 1 | Tiny exact read-only evidence from a bounded packet |
| Spark worker | xhigh | 1 | Small localized mechanical edits with focused checks |
| Luna scanner | medium | 1 | Broad discovery, large-context evidence, and validation |
| Luna worker | max | 1 | Default substantial implementation and verification |
| Sol worker | xhigh | 1 | Rare genuinely difficult implementation or diagnosis |
| Sol advisor | max | 1 | Rare consequential adversarial challenge and sign-off |
| On-demand `sol_reviewer` | max | 1 | Rare consequential post-verification review; not a routing profile |

The six general-purpose routing efforts are fixed per profile. The on-demand
reviewer is fixed at Sol/max and is not an escalation tier. Route by task shape
and escalate the model rather than changing effort ad hoc: Spark fast path, Luna
default, then Sol only for difficulty or consequential risk.

The root directly handles a short, already-contextualized command only when it
covers one concern, needs no discovery or conflicting-authority resolution, has
no unapproved or consequential external effect or material risk, has one
focused verification, and has a cheap lossless rollback. An external mutation
must be explicitly authorized with an exact target, known effect, preflight,
postcondition, and rollback. Spark remains the isolated or parallel tiny-task
lane; material work still requires bounded delegation.

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

Use Luna Medium scanning for broad read-only discovery and Luna Max for default
delivery. The root retains conflicting-evidence and consequential synthesis.
Use Sol XHigh work only after Luna is genuinely insufficient; use Sol Max advice
only for a named consequential risk or checkpoint. Dispatch the read-only
`sol_reviewer` after fresh verification only for an explicit request or a
consequential security, authentication, credentials, privacy, destructive or
irreversible action, migration, persistence, data-integrity, concurrency,
production or external impact, major architecture, compatibility,
public-contract change, conflicting evidence, stuck approach, or repeated
failed verification risk.

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

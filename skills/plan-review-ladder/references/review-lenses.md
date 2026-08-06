# Review Lenses And Output Contract

Use this reference to keep reviews independent, complementary, auditable, and
proportional. Do not invent work to fill the matrix.

## Shared Review Packet

Freeze one immutable envelope for each stage. Its `packet_payload` contains the
nonempty `packet_id`, the same `request`, `evidence`, and `candidate` for every
reviewer, the reviewer's lens only, the required `reviewer_profile`, and integer
`deadline_minutes`, `grace_minutes`, and `descendant_budget` exactly `0`.

The on-demand `sol_reviewer` delivery-review identity is not a plan-review route;
packet validation must reject it before dispatch.

Canonical bytes are UTF-8 JSON with recursively sorted keys,
`separators=(",", ":")`, `ensure_ascii=false`, and NaN forbidden. The envelope
declares the lowercase SHA-256 as `packet_sha256`. A reviewer independently
recomputes it and returns `observed_packet_sha256`; the root rejects stale,
mutated, malformed, or mismatched output. The pure helper in
`scripts/packet_integrity.py` is the executable contract.

Every stage freezes `deadline_minutes` in `1..45` (default `15`) and
`grace_minutes` in `1..5` (default `3`). The terminal profiles
`spark_scanner`, `luna_scanner`, and `sol_advisor` require
`descendant_budget` exactly `0`. Missing or out-of-range values and any other
profile block dispatch. On timeout, steer once, wait exactly the frozen grace,
then interrupt; do not automatically restart an unchanged packet.

Copy this complete field list into every reviewer assignment:

1. `Verdict`: `ready`, `revise`, or `blocked`.
2. `Verified anchors`: exact files, symbols, tests, or authoritative docs.
3. `Findings`: severity, claim/omission, impact, evidence, correction, check.
4. `Requirement trace`: covered, partial, and uncovered requirements.
5. `Coverage scores`: `0` not examined, `1` shallow, `2` source-verified.
6. `Assumptions`: verified, unverified, and disproven.
7. `Rejected ideas`: plausible changes unsupported by evidence.
8. `Residual risk`: what could still be wrong after review.

Duplicate findings are corroboration, not extra coverage. Every material
category needs one named source-verified owner with coverage score `2`.

## Plan-State Distinction

- **Existing authority** must be source-verified against the canonical schema,
  API, test, configuration, or other authoritative evidence.
- **Planned new artifact** must name its path, owner, interface or contract,
  creation step, and verification. Its absence before implementation is
  expected and is not a finding by itself.
- **Implemented artifact** applies only to implementation or diff review. It
  must exist and have test or runtime evidence.

Reviewers judge plan readiness, not implementation completeness, unless the
latter is explicitly in scope.

## Reusable Instruction-System Authority

For a plan that changes or relies on reusable instruction, configuration, hook,
or skill surfaces, the Expanded Sol stage satisfies instruction-learning review
only when its immutable packet contains:

- the concrete smallest proposal submitted through instruction-learning-loop;
- a canonical-to-installed/runtime authority trace naming the canonical source,
  installer, registration, manifest, and installed/runtime copies; and
- drift evidence or explicit N/A for every authority and overwrite path.

The final instruction-system plan must match that reviewed proposal. Any
material authority or implementation change must refresh `sol_advisor` review
before sign-off. Treat this as an internal prerequisite: when execution is
already authorized, it never creates renewed user approval.

## Deadline, Timeout, And Partial Coverage

Record `timed_out`, elapsed coverage, omitted categories, and the confidence
limit. If a timed-out stage uniquely owns a critical category, sign-off is
blocked. A stale or mismatched `observed_packet_sha256` is invalid output, not
partial coverage. A route missing required Sol evidence must be renamed as a
partial route and cannot claim Full completion.

## Stage Telemetry And Output

For every stage record profile, model, effort, packet identity, elapsed time or
timestamps, status, and child count. Record token usage only from authoritative
telemetry; otherwise token usage is `unavailable`, never inferred. The final
route summary lists completed, partial, timed-out, omitted, and interrupted
stages with confidence limits.

## Primary Coverage Allocation

### Luna Contract And Completeness

Luna primarily owns:

- requirements, acceptance criteria, non-goals, and traceability;
- exact names, selectors, schemas, interfaces, dependencies, and authority;
- end-to-end flow, cross-layer feasibility, ownership, and integration;
- persisted values, defaults, compatibility, migration, and cleanup;
- hydration, state preservation, loading, empty, error, read-only, skeleton,
  runtime, design-time, responsive, localization, accessibility, and copy;
- source, tests, generated output, packages, documentation, alternate paths,
  and positive/negative/regression/build/runtime/visual verification.

Challenge duplicated authority, stale compatibility layers, divergent runtime
and generated state, and rationale for preserving old semantics without a real
consumer.

### Sol Adversarial Risk

Sol primarily owns:

- counterexamples involving changed inputs, persisted state, indirect
  consumers, inheritance, shared state, and alternate architecture;
- malformed, empty, stale, partially loaded, concurrent, denied, failed, and
  rollback cases;
- security, permissions, data integrity, failure recovery, migration,
  performance, and misleading success states;
- one concrete counterexample that could fail while happy-path checks pass.

Do not broaden scope speculatively. Every correction needs observable impact
and authoritative evidence.

## Root Residual-Risk Lens

After merging reviews, inspect every category below coverage score `2`:

| Category | Questions |
| --- | --- |
| Input domain | Which valid values, defaults, nulls, malformed inputs, and legacy values can enter? |
| Composition | Does output depend on a parent surface, theme, inheritance, or environment? |
| Persistence | What survives upgrade, copy, serialization, migration, and rollback? |
| Propagation | Which nested or indirect consumers inherit the changed state? |
| Lifecycle | What happens during hydrate, refresh, retry, disable, destroy, and concurrent change? |
| Experience | Are runtime, empty, loading, error, design-time, responsive, and accessible states aligned? |
| Deliverables | Are source, tests, docs, generated assets, package output, and verifier rules covered? |
| Ownership | Is logic in the authoritative layer without duplicated state or policy bypass? |
| Evolution | Does delivery align with known future or alternate paths? |
| Verification | Could every proposed check pass while the user-visible defect still exists? |

Inspect at least one weak category against source before sign-off. Put the
resulting correction in the plan or record why no correction is needed.

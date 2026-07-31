---
name: plan-review-ladder
description: >-
  Use when creating or reviewing a material coding plan that needs high
  confidence, independent evidence, adversarial gap analysis, multi-model
  validation, or explicit sign-off. Skip trivial and implementation-only work.
---

# Plan Review Ladder

Produce a source-grounded implementation plan without changing product code.
The Sol Medium root owns route selection, conflict resolution, residual-risk
analysis, and the user-facing plan. Read [review-lenses.md](references/review-lenses.md)
before dispatch or final sign-off.

## Operating Contract

- The workflow is read-only: descendants do not edit product files or mutate
  external state.
- Use the configured profiles and efforts: `spark_scanner`, high, for exact
  low-context evidence only; `luna_scanner`, medium, for broader evidence;
  `luna_coordinator`, high, for candidate planning and completeness;
  `terra_coordinator`, medium, for integration; and `sol_advisor`, max, for
  adversarial challenge. `sol_coordinator`, max, is used only when Sol needs a
  bounded research subtree.
- All descendants remain read-only. Coordinators may dispatch scanners or
  read-only coordinators, never `*_worker` profiles. Depth 3 may use only
  terminal `spark_scanner` or `luna_scanner` profiles.
- Prefer `fork_turns = "none"` with the frozen packet. Start each coordinator
  with one descendant; a Sol coordinator may use at most two, increasing only
  for a named evidence gap.
- Preserve reviewer independence: do not expose one reviewer's findings to
  another before its independent pass.
- Freeze an immutable envelope for every dispatch: its canonical UTF-8 JSON
  bytes use recursively sorted keys, no insignificant whitespace,
  `ensure_ascii=false`, and forbidden NaN; the lowercase SHA-256 is declared
  as `packet_sha256` and reviewers return `observed_packet_sha256`.

## Select The Route

Use the least expensive route that preserves the quality bar:

- **Standard**: Luna candidate plan, independent Luna validation, then the
  root residual-risk pass and sign-off.
- **Expanded**: Standard plus Terra integration validation.
- **Full**: Standard plus an independent Sol challenge; include Terra when
  Expanded criteria also apply.

Use Expanded for interacting modules or ownership boundaries, ambiguous
feasibility, cross-layer behavior, substantial runtime/generated alignment, or
conflicting evidence. Use Full when explicitly requested or when compatibility,
migration/rollback, security/permissions, financial/privacy/data-integrity,
concurrency/distributed state, shared tokens/inheritance/compositing, or
unresolved high-severity risk is material. Do not raise Luna effort to replace
Terra or Terra effort to replace Sol. If a required profile is unavailable,
name the omitted stage and its confidence limit; do not silently substitute.

## 1. Freeze The Evidence Baseline

Assemble the smallest sufficient common evidence bundle:

- request, acceptance criteria, non-goals, ambiguity, and applicable
  project/skill/safety/compatibility instructions;
- authoritative source, tests, configuration, generated artifacts,
  documentation, history, and runtime evidence with exact anchors;
- current implementation or diff, repository/branch/HEAD when available,
  dirty paths, stable hashes for material non-Git artifacts, and a
  domain-authority map covering canonical definitions, consumers, persistence,
  generated outputs, and future/alternate paths.

Use Spark only for exact low-context evidence under its fast-path gates; use
Luna scanners for broader evidence. Prefer authoritative source and executable
tests over guides or model claims. Freeze the complete review packet described
in the reference, including identity and stage budget. Recheck its manifest
before sign-off; changed material evidence invalidates affected findings.

## 2. Produce And Freeze The Candidate Plan

If the user supplied a plan, preserve it as the frozen candidate. Otherwise
dispatch `luna_coordinator` with the evidence bundle and require intended
behavior, acceptance criteria/non-goals, source-grounded steps with file or
symbol anchors, compatibility/persistence/migration/cleanup/ownership
implications, focused automated/build/runtime/visual verification, assumptions,
and unresolved decisions.

The Luna output is a falsifiable draft, not approval. Classify every referenced
artifact as existing authority, planned new artifact, or implemented artifact
per the reference; plan readiness is the review target unless implementation
review is explicitly in scope.

## 3. Run Independent Validation

Always dispatch a fresh `luna_coordinator` for contract and completeness
validation. Add `terra_coordinator` for Expanded and `sol_advisor` for Full.
Run required reviewers concurrently only when evidence questions are
independent. Give each the original request, frozen evidence, candidate,
primary coverage ownership, complete Shared Review Packet, bounded descendant
budget, and non-overlapping questions.

Coverage ownership is complementary: Luna owns requirements, exact contracts,
lifecycle/UX states, localization, artifacts, documentation, and verification;
Terra owns cross-layer flow, feasibility, authority, dependencies, and
integration; Sol owns counterexamples, indirect propagation, failure/concurrency,
security, rollback, performance, and alternate architecture. Each assigned
category is scored `0` not examined, `1` shallow, or `2` source-verified;
material categories need one named primary reviewer with coverage score `2`.

Apply the reference deadline protocol. Every packet freezes integer
`deadline_minutes` in `1..45` (default `15`), `grace_minutes` in `1..5`
(default `3`), plus a required `reviewer_profile`. Terminal profiles
`spark_scanner`, `luna_scanner`, and `sol_advisor` require
`descendant_budget` exactly `0` (default `0`); `luna_coordinator` and
`terra_coordinator` require exactly `1` (default `1`); `sol_coordinator` allows
`1..2` (default `1`). Workers and unknown profiles, missing values, or
out-of-range combinations block dispatch. A timeout is steered once, waits
exactly the frozen grace, and is then interrupted. Never restart an unchanged
packet. A reviewer must return the independently recomputed
`observed_packet_sha256`; the root compares it to the declared/frozen digest
and rejects stale or mismatched output.

## 4. Synthesize And Search For A New Gap

The Sol Medium root must:

1. Build the requirement, category, finding-disposition, packet, and telemetry
   ledgers.
2. Verify disputed or consequential claims against authoritative evidence.
3. Accept, reject, or revise every actionable finding with rationale and mark
   unexamined or shallow categories.
4. Inspect at least one weak boundary directly against source and update the
   candidate plan with any correction.

Use one targeted scanner or reviewer follow-up for a narrow gap. Do not restart
the ladder unless the request, baseline, or architecture changed materially.

## 5. Sign-Off Gate

Present the final plan only when every requirement maps to implementation and
verification; no unresolved critical/high gap remains; material categories have
source-verified owners or documented N/A reasons; compatibility, persistence,
migration, cleanup, ownership, negative paths, runtime/design-time/generated
output/documentation/test impacts are covered; and the packet baseline still
matches or affected stages were refreshed. Apply timeout blocking and
confidence rules from the reference. Full is not complete without a required
Sol return and may not be labeled a partial Full; use an explicitly named
partial route instead.

Return:

1. Decision and completed route.
2. Ordered source-grounded plan with verification per step.
3. Compatibility and migration.
4. Verification matrix.
5. Coverage ledger and finding disposition.
6. Residual risks/open decisions.
7. Completed stages, models, efforts, and timing/status route summary.

Multiple-model agreement is corroboration, not proof of completeness.

When this skill changes, run:

```powershell
python "$HOME\.codex\skills\plan-review-ladder\scripts\test_plan_routing.py"
```

## Implementation Handoff

When implementation is authorized, invoke `delivery-orchestration` with the
approved plan, evidence map, unresolved risks, and verification contract. Do
not rerun the full ladder unless scope, evidence, or architecture changed.

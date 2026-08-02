---
name: plan-review-ladder
description: >-
  Use when creating or reviewing a material coding plan that needs high
  confidence, independent evidence, adversarial gap analysis, multi-model
  validation, or explicit sign-off. Skip trivial and implementation-only work.
---

# Plan Review Ladder

Produce a source-grounded implementation plan without changing product code.
The Sol Medium root owns evidence synthesis, candidate planning, route selection,
finding disposition, residual-risk analysis, and the user-facing plan. Read
[review-lenses.md](references/review-lenses.md) before dispatch or sign-off.

## Operating Contract

- The configured six-profile matrix is `spark_scanner`, xhigh;
  `spark_worker`, xhigh; `luna_scanner`, medium; `luna_worker`, max;
  `sol_worker`, xhigh; and `sol_advisor`, max. Plan review dispatches only the
  read-only `spark_scanner`, `luna_scanner`, and `sol_advisor` profiles.
- All descendants remain read-only, operate at depth 1, report directly to the
  root, and do not spawn.
- Use Spark only for exact low-context evidence. Always dispatch it with
  `fork_turns = "none"` and a self-contained bounded packet with exact anchors,
  expected evidence, and stop conditions. Do not send broad discovery or
  synthesis to Spark; use Luna instead.
- Preserve reviewer independence: do not expose one reviewer's findings to
  another before its independent pass.
- Freeze an immutable envelope for each stage. Canonical UTF-8 JSON bytes use
  recursively sorted keys, no insignificant whitespace, `ensure_ascii=false`,
  and forbidden NaN. Declare the lowercase SHA-256 as `packet_sha256` and
  require reviewers to return `observed_packet_sha256`.

## Select The Route

Use the least expensive route that preserves the quality bar:

- **Standard:** for a routine low-risk plan, the root produces the candidate,
  then dispatch `luna_scanner` for independent contract and completeness review,
  then performs the residual-risk pass and sign-off. Sol is not mandatory for
  low-risk planning.
- **Expanded:** Standard plus one risk-triggered early `sol_advisor` challenge
  before the approach settles. Use it for material architecture,
  compatibility, migration, persistence, security, concurrency, data integrity,
  external impact, conflicting authority, or a materially changing approach.
- **Full:** Expanded plus a fresh final `sol_advisor` challenge after synthesis
  and verification design. Use it when risk remains consequential, the user
  explicitly requests adversarial sign-off, or unresolved high-severity risk
  would block implementation.

If a required review times out or is unavailable, name the omitted stage and
confidence limit. Full is complete only when both required Sol stages return.

## 1. Freeze The Evidence Baseline

Assemble the smallest sufficient common evidence bundle:

- request, acceptance criteria, non-goals, ambiguity, and applicable
  project/skill/safety/compatibility instructions;
- authoritative source, tests, configuration, generated artifacts,
  documentation, history, and runtime evidence with exact anchors;
- current implementation or diff, repository/branch/HEAD, dirty paths, stable
  hashes for material non-Git artifacts, and a domain-authority map covering
  canonical definitions, consumers, persistence, outputs, and alternate paths.

Use Spark only for a tiny exact anchor check. Use Luna Medium for broad or
context-heavy discovery and independent evidence. Prefer authoritative source
and executable tests over guides or model claims. Recheck the manifest before
sign-off; changed material evidence invalidates affected findings.

## 2. Run The Optional Early Risk Checkpoint

For Expanded or Full, the root dispatches `sol_advisor` after bounded discovery
and before treating an approach as settled. Give it the request, acceptance
criteria, authority boundaries, evidence anchors, ambiguity, competing
interpretations, risks, and specific questions. It challenges assumptions and
failure modes without demanding a diff or executed tests.

## 3. Produce And Freeze The Candidate Plan

If the user supplied a plan, preserve it as the frozen candidate. Otherwise the
root creates a falsifiable candidate containing intended behavior, acceptance
criteria and non-goals, source-grounded steps with file or symbol anchors,
compatibility/persistence/migration/cleanup/ownership implications, focused
automated/build/runtime/visual verification, assumptions, and unresolved
decisions.

Classify each referenced artifact as existing authority, planned new artifact,
or implemented artifact. Plan readiness is the target unless implementation
review is explicitly in scope.

## 4. Run Independent Luna Validation

Always dispatch a fresh `luna_scanner` for contract, feasibility, integration,
and completeness validation. Give it the original request, frozen evidence,
candidate, primary coverage categories, the complete Shared Review Packet, and
non-overlapping questions. It must source-verify requirements, interfaces,
lifecycle states, cross-layer flow, compatibility, artifacts, and verification.

Every packet freezes integer `deadline_minutes` in `1..45` (default `15`),
`grace_minutes` in `1..5` (default `3`), a required `reviewer_profile`, and
`descendant_budget` exactly `0`. The terminal profiles `spark_scanner`,
`luna_scanner`, and `sol_advisor` are the only planning reviewer profiles.
Unknown profiles, workers, missing values, or any nonzero descendant budget
block dispatch.

On timeout, steer once, wait exactly the frozen grace, then interrupt. Never
restart an unchanged packet. Reject output without the independently recomputed
`observed_packet_sha256` matching the frozen packet.

## 5. Synthesize And Search For A New Gap

The root must:

1. Build the requirement, category, finding-disposition, packet, and telemetry
   ledgers.
2. Verify disputed or consequential claims against authoritative evidence.
3. Accept, reject, or revise every actionable finding with rationale.
4. Inspect at least one weak boundary directly against source and correct the
   plan or document why no correction is needed.

Use one targeted read-only follow-up for a narrow gap. Do not restart the ladder
unless the request, evidence baseline, or architecture changed materially.

## 6. Run The Optional Final Risk Checkpoint

For Full, freeze the synthesized candidate and verification design, then send a
fresh packet to `sol_advisor`. This final-plan checkpoint searches for missed
requirements, counterexamples, weak coverage, rollback/failure gaps, and
residual risk. It reviews plan readiness and does not require implementation
artifacts or executed tests.

## 7. Sign-Off Gate

Present the final plan only when every requirement maps to implementation and
verification; no unresolved critical/high gap remains; material categories have
source-verified owners or documented N/A reasons; compatibility, persistence,
migration, cleanup, ownership, negative paths, runtime/design-time/generated
output/documentation/test impacts are covered; and the packet baseline still
matches or affected stages were refreshed.

Return:

1. Decision and completed route.
2. Ordered source-grounded plan with verification per step.
3. Compatibility and migration.
4. Verification matrix.
5. Coverage ledger and finding disposition.
6. Residual risks and open decisions.
7. Completed stages, models, efforts, and timing/status summary.

Multiple-model agreement is corroboration, not proof of completeness.

When this skill changes, run:

```powershell
python -B .\skills\plan-review-ladder\scripts\test_plan_routing.py
python -B .\skills\plan-review-ladder\scripts\test_packet_integrity.py
```

## Implementation Handoff

When implementation is authorized, invoke `delivery-orchestration` with the
approved plan, evidence map, unresolved risks, and verification contract. Do
not rerun the full ladder unless scope, evidence, or architecture changed.

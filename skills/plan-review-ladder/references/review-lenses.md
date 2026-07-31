# Review Lenses And Output Contract

Use this reference to keep reviews independent, complementary, auditable, and
proportional. Do not invent irrelevant work to fill the matrix.

## Shared Review Packet

Freeze one immutable envelope for each stage. Its `packet_payload` contains the
nonempty `packet_id`, the same `request`, `evidence`, and `candidate` for every
reviewer, the reviewer's lens only (no earlier findings or conclusions), the
required `reviewer_profile`, and integer `deadline_minutes`, `grace_minutes`,
and `descendant_budget`.

Canonical packet bytes are UTF-8 JSON with recursively sorted keys,
`separators=(",", ":")`, `ensure_ascii=false`, and NaN forbidden. The envelope
declares the lowercase SHA-256 of those exact bytes as `packet_sha256`; both
payload and declared digest are frozen. A reviewer independently recomputes
the digest and returns `observed_packet_sha256`. The root compares observed to
the declared/frozen digest and rejects stale, mutated, malformed, or mismatched
output. The pure helper in `scripts/packet_integrity.py` is the executable
contract for canonical bytes, envelope construction, hashing, verification,
and budget validation.

Every stage freezes integer `deadline_minutes` in `1..45` (default `15`) and
`grace_minutes` in `1..5` (default `3`). Terminal profiles
`spark_scanner`, `luna_scanner`, and `sol_advisor` require
`descendant_budget` exactly `0` (default `0`); `luna_coordinator` and
`terra_coordinator` require exactly `1` (default `1`); `sol_coordinator` allows
`1..2` (default `1`). Workers, unknown profiles, missing values, and
out-of-range combinations block dispatch before the stage starts. On timeout,
steer once, wait exactly the frozen `grace_minutes`, then interrupt; never
restart an unchanged packet.

Copy this complete field list into every reviewer assignment:

1. `Verdict`: `ready`, `revise`, or `blocked`.
2. `Verified anchors`: exact files, symbols, tests, or authoritative docs used.
3. `Findings`: ordered by severity. Each finding includes the plan claim or
   omission, observable impact, evidence, exact correction, and verification.
4. `Requirement trace`: covered, partially covered, and uncovered requirements.
5. `Coverage scores`: each assigned category scored `0` not examined, `1`
   shallow, or `2` source-verified.
6. `Assumptions`: verified, unverified, and disproven.
7. `Rejected ideas`: plausible changes the evidence does not support.
8. `Residual risk`: what could still be wrong after this review.

Duplicate findings count as corroboration, not extra coverage. Every material
category has one named primary reviewer responsible for a source-verified
review with coverage score `2`.

## Plan-State Distinction

Review the plan against the state of each artifact, rather than treating every
path as an implementation claim:

- **Existing authority** must be source-verified against the current canonical
  schema, API, test, configuration, or other authoritative evidence.
- **Planned new artifact** must name its intended path, owner, interface or
  contract, creation step, and verification.
  Its absence before implementation is expected and is not a finding by itself.
- **Implemented artifact** applies only to implementation or diff review. It
  must exist and have test or runtime evidence.

Reviewers judge plan readiness, not implementation completeness, unless
implementation review is explicitly in scope. A plan may therefore be ready
while a planned new artifact is not yet present.

## Deadline, Timeout, And Partial Coverage

Every reviewer stage receives the frozen finite budgets above. On expiry, steer
once for the current evidence, wait exactly `grace_minutes`, and then interrupt.
Do not automatically restart an expensive reviewer on an unchanged packet.
Record `timed_out`, elapsed coverage, omitted categories, and the confidence
limit in the ledger and route summary. A stale or mismatched
`observed_packet_sha256` is invalid output, not partial coverage.

If a timed-out stage uniquely owns a critical category, sign-off is blocked. If
it does not, the root may use an explicit partial route with a stated confidence
limit. Full cannot be called complete if a required Sol stage did not return,
and the result may not be labeled a partial Full; use the named partial route.

## Stage Telemetry And Output

For every stage record profile, model, effort, packet identity, elapsed time (or
start/end timestamps), status, and child count. Record token usage only from
authoritative telemetry; otherwise token usage is `unavailable`, never inferred
from output length or elapsed time. The final output includes a timing/status
route summary listing completed, partial, timed-out, omitted, and interrupted
stages with their confidence limits.

## Primary Coverage Allocation

### Luna Contract And Completeness

Luna primarily owns:

- User requirements, acceptance criteria, non-goals, and plan traceability.
- Public names, selectors, schemas, persisted values, defaults, compatibility,
  migration, and cleanup.
- Hydration, state preservation, loading, empty, error, read-only,
  skeleton, runtime, and design-time/WYSIWYG state inventory.
- Localization, fallback maps, type guards, accessibility, and user-facing copy.
- Source files, tests, generated output, package artifacts, verifier rules,
  documentation, and future-path inventory.
- Positive, negative, regression, build, runtime, and visual verification
  completeness.

Challenge any rationale for preserving old internal semantics unless evidence
identifies a real compatibility consumer.

### Terra Integration And Feasibility

Terra primarily owns:

- End-to-end flow across UI, model, service, server, package, and generated
  boundaries.
- Implementation feasibility, dependency order, interfaces, ownership, and
  integration points between independently owned work.
- Duplicated authority, inconsistent state, stale compatibility layers, and
  divergence between runtime, design-time, generated output, and future paths.
- Cross-layer performance, bounded work, refresh and retry behavior, and
  verification that exercises the integrated user-visible outcome.

Use Terra when these concerns are material; do not add it merely to make the
review count larger.

### Sol Adversarial Risk

Sol primarily owns:

- Counterexamples involving changed inputs, tokens, variables, bindings,
  persisted values, events, indirect consumers, and descendants.
- Shared-state coupling, inheritance leaks, nested surfaces, implicit
  fallbacks, and alternate architecture.
- Malformed, empty, stale, transparent, partially loaded, concurrent, denied,
  failed, and rollback cases as applicable.
- Race conditions, security, permissions, data integrity, failure recovery,
  rollback, performance, and misleading success states.
- A concrete counterexample that could fail while happy-path tests pass.

Do not broaden scope speculatively. Every correction needs observable impact and
evidence.

## Task-Specific Coverage

The root adds categories from the domain-authority map and assigns one primary.
For an appearance change, explicitly cover:

- Authoritative token and appearance catalogs.
- Accepted color formats, defaults, transparency, and alpha composition.
- Contrast and readable interaction-state calculation.
- Direct and inherited descendant surfaces, including nested rows or tasks.
- Runtime, skeleton, loading, Designer, responsive, RTL, and accessibility
  behavior.
- Persisted values, intentional visual migration, generated output, docs,
  verifier rules, and alternate/future delivery paths.

## Root Residual-Risk Lens

After merging reviews, mark every category with coverage below score `2`:

| Category | Questions |
| --- | --- |
| Input domain | Which valid values, formats, defaults, nulls, and legacy values can enter? |
| Composition | Does output depend on a parent surface, theme, alpha, inheritance, or environment? |
| Persistence | What survives upgrade, copy, serialization, migration, and rollback? |
| Propagation | Which nested or indirect consumers inherit the changed state? |
| Lifecycle | What happens during hydrate, refresh, retry, echo, disable, destroy, and concurrent change? |
| Experience | Are runtime, skeleton, empty, loading, error, Designer, responsive, RTL, and accessibility states aligned? |
| Deliverables | Are source, tests, localization, docs, generated assets, package output, and verifier rules covered? |
| Ownership | Is logic implemented in the authoritative layer without duplicating state or bypassing policy? |
| Evolution | Does current delivery align with the known future or alternate path? |
| Verification | Could every proposed check pass while the user-visible defect still exists? |

Inspect at least one weak category against source before sign-off. Put the
resulting correction in the plan or record why no correction is needed.

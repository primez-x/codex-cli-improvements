# Review lenses v1

The Windhawk corpus informed generic, evidence-first lenses rather than copied
review comments. The upstream [PR workflow](https://github.com/ramensoftware/windhawk-mods/blob/main/.github/pr_flow.cjs)
and representative [4974](https://github.com/ramensoftware/windhawk-mods/pull/4974),
[4934](https://github.com/ramensoftware/windhawk-mods/pull/4934),
[4935](https://github.com/ramensoftware/windhawk-mods/pull/4935),
[4921](https://github.com/ramensoftware/windhawk-mods/pull/4921), and
[4976](https://github.com/ramensoftware/windhawk-mods/pull/4976) illustrate the method. In particular,
the workflow compares the exact current HEAD with the reviewed SHA; 4976 records a
stale reviewed SHA rather than accepting a ready-for-reviewer claim. The representative
threads also show repeated correction/review generations rather than a one-pass verdict.

Group findings as blocking, optional, or functionality. Each has exact impact,
evidence, correction, and affected verification. Examine lifecycle and cleanup,
concurrency and ownership, input/command boundaries, memory and resource safety,
performance, repository contracts, indirect consumers, overlap/attribution, and
author-provided verification. Re-review the exact successor bundle after an
accepted correction; a clean corrected control prevents treating every pattern
as a perpetual finding.

For each finding, cite one exact immutable case-artifact selector in its
`evidence`: either `selector: {kind: symbol, value: ...}` or a bounded
`selector: {kind: line_range, start: ..., end: ...}` on a digest-bound bundle or
full Git commit reference. The claim must name the concrete defect at that
selector; the correction must describe the behavior-changing remedy; and the
verification must exercise the affected failure path. A lens name or generic
category keyword is not a defect report.

The bundle contract names these mandatory IDs. Record each as `reviewed` with a
short evidence summary, or as `not_applicable` with evidence explaining why:

- `artifact_identity`: exact bundle, packet, snapshot, modes, deleted/untracked,
  generated, and immutable external evidence identities.
- `lifecycle_cleanup`: init, teardown, partial failure, callback, timer, hook,
  unload, retry, and restart behavior.
- `concurrency_ownership`: thread/process boundaries, shared-state ownership,
  reentrancy, races, lock ordering, cancellation, and ABA-sensitive state.
- `input_command_boundaries`: parsing, quoting, validation, authorization,
  injection, path, and external-data boundaries.
- `memory_resource_safety`: bounds, lifetime, aliasing, handles, descriptors,
  cleanup ownership, and error-path release.
- `performance_hot_paths`: callbacks, polling, repeated I/O, unbounded work,
  caching, coalescing, and representative scale.
- `repository_contracts`: local instructions, established patterns, packaging,
  generated artifacts, compatibility, attribution, and policy.
- `indirect_consumers`: callers, hooks, schemas, serialized formats, public APIs,
  downstream builds, migrations, and operational consumers.
- `overlap_attribution`: existing implementations, duplicated behavior, copied
  code, licensing, provenance, and whether extension is preferable.
- `author_verification`: tests/builds/runtime evidence, realistic abnormal cases,
  residual limitations, and claims not established by the evidence.

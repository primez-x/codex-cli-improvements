---
name: adversarial-code-review
description: Use when a material code delivery needs independent adversarial review before sign-off.
---

# Adversarial Code Review

Trigger: use when a material implementation needs an independent, evidence-bound adversarial review before its delivery gate can complete.

Treat Multi-file or cross-layer changes, code plus tests or generated output,
substantial discovery, and build/install/deploy work as material. Also classify
localized work as material when architecture, compatibility, persistence,
security, concurrency, data-integrity, or external-impact risk appears. Exempt
read-only work, plan-only work, and genuinely localized mechanical edits; record an exact exemption reason. If material scope appears late, arm the gate immediately.

Use the CLI only for root-owned lifecycle decisions (add `--state-root` and
`--profile-path` when not using installed defaults):

```text
lifecycle_gate.py classify --session-id S --turn-id T --classification material --task-id TASK --paths path/to/file
lifecycle_gate.py classify --session-id S --turn-id T --classification exempt --reason "localized mechanical edit: ..."
lifecycle_gate.py freeze --session-id S --turn-id T --cwd REPO --paths path/to/file --verification-manifest verification.json [--max-freeze-seconds 180]
lifecycle_gate.py disposition --session-id S --turn-id T --file ledger.json
lifecycle_gate.py status --session-id S --turn-id T
```

Hooks own `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `SubagentStart`,
`SubagentStop`, and final `Stop`; do not synthesize those events during a normal
delivery.

1. Classify with a recorded task and exact owned paths, then freeze with a
   strict `VerificationEvidenceV1` manifest. Record exact commands, platform,
   exits, test counts, raw stdout/stderr digests, and separate synthetic versus
   live hook/provenance observations. Mark unavailable live proof unavailable;
   never promote a direct handler smoke into a live-runtime claim. The freeze
   captures those artifacts with base, HEAD, index, and worktree bytes plus the
   canonical snapshot, contract, and packet records in one immutable bundle.
   For package publication or installation, also pass the canonical
   `--production-manifest`; the snapshot then includes every copied and semantic
   source input, including unchanged indirect inputs. Freeze uses one bounded
   elapsed budget for snapshot and evidence capture (default 180 seconds,
   configurable from 1 through 300 seconds).
2. Dispatch only the configured `sol_reviewer`. `SubagentStart` binds its exact
   agent ID, model, profile digest, attempt, generation, bundle, packet,
   snapshot, and mutation epoch. The reviewer returns only `ReviewOutputV1`;
   the lifecycle gate creates receipts locally.
   The bundle digest-binds [the mandatory lens checklist](references/review-lenses.md),
   and every lens requires a reviewed entry or an evidence-backed not-applicable
   disposition in the output coverage trace.
3. Record one canonical disposition per finding. Accepted findings advance the
   generation, clear the receipt, and require refreeze plus rereview. A
   critical/high rejection needs immutable primary counterevidence.
4. Complete only after `Stop` revalidates the installed profile, current owned
   snapshot, epoch, output, ledger, and exact local receipt. A persisted blocker
   may exit only with `[adversarial-review-blocked] Incomplete: ...`; it never
   becomes a successful completion.

See [contract reference](references/contracts.md) for the field authority,
strict examples, and transition rules.
Use the [fresh Sol/max replay workflow](references/evaluation-replay-workflow.md)
when evaluating reviewer quality; curated self-test outputs cannot support that
claim.

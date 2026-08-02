# Codex Orchestration Kit

This repository contains a reusable, evidence-driven Codex orchestration
configuration. It keeps expensive models in supervisory roles while routing
bounded scanning and implementation work to faster models with explicit
ownership, depth, and verification gates.

The kit is intentionally generic. It contains no project instructions,
credentials, local runtime state, or machine-specific paths.

## Included

- `config.toml`: an orchestration-only configuration example.
- `agents/`: scanner, worker, coordinator, advisor, and terminal reviewer profiles.
- `skills/adversarial-code-review/`: immutable evidence contracts and the
  lifecycle review gate.
- `skills/delivery-orchestration/`: adaptive implementation routing,
  ownership, integration, and completion gates.
- `skills/plan-review-ladder/`: independent multi-model plan review with
  frozen evidence, packet identity, deadlines, timeout handling, telemetry,
  and explicit sign-off.
- `skills/instruction-learning-loop/`: a bounded loop for turning durable
  corrections into the smallest verified instruction update.
- `hooks/plan_gap_goal_hook.py`: starts goal tracking when an approved plan
  moves into implementation.
- `hooks.json`: portable hook registration for plan-goal and instruction
  learning behavior.

## Model And Effort Matrix

| Role | Model | Effort | Typical use |
| --- | --- | --- | --- |
| Root | GPT-5.6 Sol | Medium | Routing, integration, final decisions |
| Spark scanner | GPT-5.3 Codex Spark | High | Exact low-context evidence |
| Spark worker | GPT-5.3 Codex Spark | XHigh | Small, mechanical edits |
| Luna scanner | GPT-5.6 Luna | Medium | Broader read-only evidence |
| Luna worker | GPT-5.6 Luna | High | Routine implementation |
| Luna coordinator | GPT-5.6 Luna | High | Bounded workstream supervision |
| Terra worker/coordinator | GPT-5.6 Terra | Medium | Ambiguous or cross-layer work |
| Sol worker | GPT-5.6 Sol | XHigh | Rare difficult implementation |
| Sol advisor/coordinator | GPT-5.6 Sol | Max | Adversarial review and supervision |

The configured effort is fixed per profile. When a task exceeds a profile's
capability, context, or risk boundary, routing escalates the model instead of
raising effort ad hoc.

## Delegation Topology

- Depth 0 is the root.
- Depth 1 can use any registered profile.
- Depth 2 uses Luna or Terra coordinators and bounded Spark, Luna, or Terra
  terminal agents.
- Depth 3 is terminal and limited to Spark or Luna scanners/workers.
- Coordinators reserve their own integration paths and assign disjoint
  ownership before concurrent edits.
- The root owns final integration, external actions, and the user response.

Most work should finish at depth 1. Depth 2 is used when decomposition improves
latency, quality, or context hygiene. Depth 3 remains available for genuinely
complex fan-out without becoming the default.

## Plan Review Routes

- **Standard:** Luna candidate, independent Luna validation, root residual-risk
  pass.
- **Expanded:** Standard plus Terra integration validation.
- **Full:** Standard plus an independent Sol challenge, with Terra when
  cross-layer integration is also material.

All reviewers receive the same frozen request, evidence, and candidate plan.
Reviewer-specific lenses are the only difference. The ladder distinguishes
existing authority, planned new artifacts, and implemented artifacts, so a
future file is not falsely reported missing before implementation. Required
stages have packet identities, deadlines, bounded descendants, timeout
handling, and evidence-limited telemetry.

## Install

Use this repository as a source package, not as a blind replacement for an
existing Codex home:

Use the transactional installer instead of manually copying or merging files.
It uses an explicit production-file allowlist, previews raw copied paths and
exact managed TOML/JSON/instruction changes, writes a private staged payload and
recovery journal, authenticates every backup, is idempotent, and can roll back
a transaction. It preserves unrelated hook groups, hook trust metadata, agents,
skills, config sections, and instructions:

Incomplete-transaction recovery is compare-and-swap safe against its journal:
only `applied` paths and the in-flight `next_path` are rollback candidates,
untouched paths are never rewritten, and every live target must still equal an
authenticated preimage, postimage, or expected absence before recovery mutates
anything. Per-path `rolling_back` progress makes an interrupted rollback
restartable; unrecognized drift is preserved and blocks recovery.

```powershell
python -B .\skills\adversarial-code-review\scripts\install_review_gate.py preview --source-root . --codex-home $env:CODEX_HOME
python -B .\skills\adversarial-code-review\scripts\install_review_gate.py install --source-root . --codex-home $env:CODEX_HOME
python -B .\skills\adversarial-code-review\scripts\install_review_gate.py verify --source-root . --codex-home $env:CODEX_HOME
python -B .\skills\adversarial-code-review\scripts\install_review_gate.py smoke --source-root . --codex-home $env:CODEX_HOME
```

`install` and `verify` run both installed skill validators plus a stateful
handler-contract smoke. The smoke creates a temporary Git delivery and derives
wrong-profile, copied-output, replay, correct-profile, and final-Stop outcomes
from the real lifecycle handler. It is not proof that a running Codex app loaded
or trusted handlers. Restart Codex, open a new task, use `/hooks` to review and
approve all six changed handlers, then run the live provenance smoke. The
installer never writes trusted hashes or bypasses trust controls.

Model availability and supported reasoning efforts can vary by account and
Codex release. Verify the local model catalog before enabling a profile.

## Validate

From the repository root in PowerShell:

```powershell
$env:CODEX_ROUTING_HOME = (Resolve-Path .).Path
python -B .\skills\delivery-orchestration\scripts\test_routing_policy.py
Remove-Item Env:CODEX_ROUTING_HOME

python -B .\skills\plan-review-ladder\scripts\test_plan_routing.py
python -B .\skills\instruction-learning-loop\scripts\test_instruction_learning.py
python -B .\skills\adversarial-code-review\scripts\lifecycle_gate.py health
python -B .\skills\adversarial-code-review\scripts\evaluate_review_corpus.py --corpus .\skills\adversarial-code-review\references\evaluation-corpus.json --results .\skills\adversarial-code-review\references\evaluation-self-test-results.json --git-identities .\skills\adversarial-code-review\references\evaluation-git-identities.json
python -B -m unittest discover -s .\tests -p "test_adversarial_review_installer.py" -v
python -B -m unittest discover -s .\tests -p "test_adversarial_review_evaluation.py" -v
python -B -m unittest discover -s .\tests -v
```

After installation, restart Codex, use `/hooks` to confirm all six registered
events and their handlers are enabled, then run the unit-test commands above as a positive
smoke check.

For a material delivery, the gate classifies exact owned paths, freezes one
canonical bundle containing the snapshot, contract, packet, and reviewable
source bytes. The bundle digest-binds the versioned review-lens checklist, and
the output must disposition every mandatory lens. The gate binds the configured
`sol_reviewer` agent/model/profile to a single attempt and generation. The hook
creates the receipt locally from the validated output and disposition ledger.
Accepted findings invalidate that receipt and require a new generation, freeze,
and review. The pinned corpus evaluator checks strict `ReviewOutputV1` records,
known-category recall, authenticated Git identities, immutable local inputs,
curated evaluator self-test outputs, and corrected-control false positives.
The curated file tests scoring mechanics only. Reviewer-quality evaluation
requires a fresh provenance-bound `sol_reviewer`/Sol/max replay created through
the documented freeze/dispatch/lifecycle-export workflow. Empirical evaluation
requires both `--lifecycle-state-root` and `--claim-empirical-quality`, and the
evaluator revalidates the retained state, active pointer, profile, bundle bytes,
output, disposition, and receipt. Standalone self-consistent JSON is rejected.
Even a passing replay is empirical regression evidence, not
proof of complete defect detection. A persisted
infrastructure or reviewer blocker can exit only as
`[adversarial-review-blocked] Incomplete: ...`; it is never a successful
delivery.

The repository contract tests also reject machine-specific absolute paths and
project-specific material in the reusable package.

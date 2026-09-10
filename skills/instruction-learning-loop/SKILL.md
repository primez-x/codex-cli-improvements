---
name: instruction-learning-loop
description: Evaluate and apply the smallest source-backed instruction correction when one is warranted.
---

# Instruction Learning Loop

Use this skill when evidence suggests that a durable instruction correction may
help:

- the user explicitly asks to change AGENTS.md, SKILL.md, hooks, or an
  instruction workflow
- a recurring agent or verification failure is unlikely to be solved by a
  one-off fix
- source drift affects later sessions or reusable assets

This is a discretionary engineering aid, not an automatic completion gate. A
bug or delivery fix can be complete without changing instructions. Do not turn
a one-off preference, expected probe, test-first red phase, or temporary
workaround into durable guidance. Do not invoke a hook as a completion gate.

## Workflow

1. Capture exact evidence: paths, messages, IDs, dates, artifacts, and command
   output.
2. Classify the finding as one-off guidance, a durable rule, or unresolved
   source drift, and form the smallest concrete proposal.
3. Apply the current risk-triggered independent-review rule when the proposed
   correction is consequential; otherwise use focused root verification.
4. If the user authorized the change, patch only the narrowest applicable
   user-owned surface. For read-only or out-of-scope work, propose only.
5. Remove obsolete wording, keep the rule short, and preserve source authority.
6. Run `scripts/audit_instruction_system.py --project-root <optional>` and
   other focused tests or audits relevant to the changed surface.
7. Report the actual changed paths, evidence, and unverified areas. If no
   durable correction is warranted, say so rather than forcing a documentation
   edit.

Review findings may require revising a proposal, but they do not create a
persistent confirmation lifecycle or block an otherwise verified fix. Do not
claim user-observed resolution without user-observed evidence; that reporting
boundary does not require an instruction edit or hold unrelated delivery.

## Runtime and history

Instruction learning is not a runtime hook or completion gate. The explicit
audit script is the supported read-only check. Preserve existing state and
history as inert evidence; do not delete it as part of routine learning work.

## Files

- `agents/openai.yaml`: assistant-facing invocation text
- `scripts/audit_instruction_system.py`: read-only audit command
- `scripts/test_instruction_learning_audit.py`: focused audit tests

## Deliverable constraints

- keep changes minimal, deterministic, and source-backed
- never edit project files outside the authorized scope
- keep warnings explicit and distinguish review leads from hard failures

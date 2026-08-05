---
name: instruction-learning-loop
description: Turn durable instruction-system corrections into the smallest verified documentation fix.
---

# Instruction Learning Loop

Use this skill when you need to act on:

- repeated or explicit user requests about AGENTS.md, SKILL.md, hook scripts, or instruction workflows
- recurring agent or verification failures where one-off fixes would be ineffective
- source drift that has impact across sessions or reusable assets

Use this whenever a durable instruction change may be warranted. A request to
improve, fix, update, or adjust the instruction system authorizes the narrowest
applicable user-owned write unless the user explicitly makes the request
read-only. A request only to review or classify a possible improvement does not
authorize a write.

1. capture evidence links: paths, IDs, message IDs, and command output
2. classify one-off preference vs durable rule and form the smallest concrete proposal
3. send the proposal and evidence to an independent `sol_advisor` for approval or rejection
4. if approved and the request authorizes changes under the rule above, patch the smallest writable surface:
   - thread message
   - memory update note only when the user explicitly asks to update memory
   - global, project, or nested `AGENTS.md` under the user's scope
   - `.codex/skills` skill entrypoint and helpers
5. remove/replace obsolete text and keep language short
6. add or verify executable gates (unit tests, audits, or lint rules)
7. if the advisor rejects the proposal, do not implement that proposal; use its concrete rationale to revise or replace the proposal and resubmit it for review
8. if not authorized, report a proposal and risks instead of writing
9. report the actual changed instruction path and verification; a proposal alone is not completion

## Workflow

1. capture exact failing/correction evidence (paths, messages, IDs, dates, artifacts)
2. run `scripts/audit_instruction_system.py --project-root <optional>`:
   - validate required structure
   - find budget/broken-link/duplicate risks
   - run `quick_validate.py` for discovered SKILL.md files
3. have an independent `sol_advisor` approve or reject the evidence-backed proposal
4. if approved and authorized, patch only the narrowest target surface
5. if rejected, preserve the current instructions, revise the proposal from the rejection rationale, and repeat review until a valid narrow change is approved
6. preserve source authority and project conventions; avoid adding preference text
7. do not mutate if trigger is only personal taste or a one-time workaround

## Hook behavior

`instruction_learning_hook.py` follows the official hook schema and enforces an
outcome rather than a prose marker:

- on durable behavioral guidance or instruction correction at `UserPromptSubmit`, it snapshots SHA-256 content identities for recognized global and current-project instruction surfaces, records state under `hooks/state/instruction-learning`, and instructs the agent to propose, independently review, then implement and verify the smallest approved durable correction.
- explicit read-only and one-off prompts do not require mutation.
- on `Stop`, an actionable correction remains blocked until the instruction snapshot proves a real file change; proposals, claimed rejections, and generic completion phrases cannot satisfy the gate.
- blocked state is retained across ordinary retries. A `stop_hook_active` continuation passes through without deleting state, as required to prevent recursive Stop-hook loops; the next ordinary Stop re-evaluates the same content gate.
- ignore hook continuation sentinels in your own loop

## Files

- `agents/openai.yaml`: assistant-facing invocation text
- `scripts/instruction_learning_hook.py`: hook implementation
- `scripts/audit_instruction_system.py`: read-only audit command
- `scripts/test_instruction_learning.py`: unit tests for hook and audit contract

## Deliverable constraints

- keep all changes minimal and deterministic
- never edit project files outside this scope unless explicitly requested
- keep warnings explicit; classify duplicate findings as review leads, and escalate real broken links or invalid structures as hard failures

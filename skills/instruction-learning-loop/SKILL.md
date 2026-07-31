---
name: instruction-learning-loop
description: Turn durable instruction-system corrections into the smallest verified documentation fix.
---

# Instruction Learning Loop

Use this skill when you need to act on:

- repeated or explicit user requests about AGENTS.md, SKILL.md, hook scripts, or instruction workflows
- recurring agent or verification failures where one-off fixes would be ineffective
- source drift that has impact across sessions or reusable assets

Use this whenever a durable instruction change may be warranted. The hook asks
for classification; it does not authorize a write.

1. capture evidence links: paths, IDs, message IDs, and command output
2. classify one-off preference vs durable rule
3. if durable and the request authorizes changes, patch the smallest writable surface:
   - thread message
   - memory update note only when the user explicitly asks to update memory
   - global, project, or nested `AGENTS.md` under the user's scope
   - `.codex/skills` skill entrypoint and helpers
4. remove/replace obsolete text and keep language short
5. add or verify executable gates (unit tests, audits, or lint rules)
6. if not authorized, report a proposal and risks instead of writing
7. include one standalone disposition line: `Instruction learning: <summary>`

## Workflow

1. capture exact failing/correction evidence (paths, messages, IDs, dates, artifacts)
2. run `scripts/audit_instruction_system.py --project-root <optional>`:
   - validate required structure
   - find budget/broken-link/duplicate risks
   - run `quick_validate.py` for discovered SKILL.md files
3. if durability is confirmed, patch only the narrowest target surface
4. preserve source authority and project conventions; avoid adding preference text
5. do not mutate if trigger is only personal taste or a one-time workaround

## Hook behavior

`instruction_learning_hook.py` follows the official hook schema:

- on durable-correction `UserPromptSubmit`, it records state under `hooks/state/instruction-learning` and returns `hookSpecificOutput` with `hookEventName: UserPromptSubmit`.
- on `Stop`, it blocks once with `{"decision":"block","reason":"... [instruction-learning-hook]..."}` if required marker is missing, then clears state.
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

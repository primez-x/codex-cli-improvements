# Codex Orchestration Kit

A portable Codex setup: GPT-6.1 Sol medium coordinates, Luna and Sol workers take
delegated work by tier, and Fable high gives preferred independent critique. GPT-6
Astra high is the fallback when Claude is unavailable or usage-limited.
The root owns final engineering approval, Git, and external actions.

Keep this repository generic across personal and work devices. Machine-local
workspaces, tenant configuration, personal/business data, and private verification
reports belong outside the repository.

## Included

- `AGENTS.md`: concise working agreements and plan-completion persistence.
- `config.toml` and `agents/`: explicit model routing, a shared six-thread
  ceiling, and delegation up to absolute depth 2.
- `skills/delivery-orchestration/`: one planning/delivery workflow, the
  [routing matrix](skills/delivery-orchestration/references/delegation-topology.md),
  and the [combined model routing policy](skills/delivery-orchestration/references/model-routing.md).
- `skills/adversarial-code-review/`: approach or delivery review by Fable high when
  Claude is available, with Astra high as the fallback; ordinary work uses Sol root review.
- `skills/skill-loop/`: inspect, explain, undo, or pause Skill Loop.
- `hooks/plan_gap_goal_hook.py` and `hooks.json`: accepted-plan goal persistence
  and the Skill Loop hook registrations.

## Working Pattern

Sol defines the outcome and delegates useful independent work while
continuing integration or decisions. Use focused checks for the changed
behavior, then review the integrated result. Avoid mandatory ledgers, repeated
review stages, and instruction edits that do not address a durable defect.

Luna medium handles read-only discovery through `luna_scanner`. Luna xhigh handles
decided mechanical edits through `luna_fast_worker` and partitioned workstreams through
`luna_worker`. `sol_fast_worker` uses GPT-6.1 Sol low for bounded routine implementation.
`sol_medium_worker` uses GPT-6.1 Sol medium for bounded judgment. `sol_worker` uses
GPT-6.1 Sol high for substantial or difficult implementation. No profile uses Max.
`astra_advisor` uses GPT-6 Astra high only as the Claude-unavailable fallback.

Native presets are fallbacks, not global provider priority. The
[model routing policy](skills/delivery-orchestration/references/model-routing.md) selects
across Claude and Codex by capability, verified usable headroom, and subscription cost.
Choose using total completion cost, including handoffs and rework.

## Depth And Concurrency

Root is depth 0. Luna xhigh and Sol high workers may subdivide independent
owned work at depth 1; all agents at depth 2 are terminal. Scanners,
fast workers, and the medium Sol worker are terminal at depths 1–2. Only root
dispatches the terminal depth-1 advisor.

All descendants share `max_concurrent_threads_per_session = 6`; the root is
excluded. This is a ceiling, not a quota. Parent writers suspend edits to child
paths until ownership returns. Children never gain broader authority. Keep
assignments bounded with exact anchors, narrow reads, and concise evidence.
Reuse compatible agents; use `fork_turns = "none"` when fresh context is useful.

The working topology is root → workstream worker → terminal leaf.
Keep `max_depth = 2` for runtimes that honor it and apply the same ceiling in
instructions. This matches the demonstrated client behavior without claiming
a universal product maximum. If a worker cannot spawn, it returns the packet
to root for direct dispatch.
See [official subagent configuration](https://learn.chatgpt.com/docs/agent-configuration/subagents).

## Plan Goal Hook

The goal hook is intentionally retained for large accepted plans. A leading
`Implement the plan` (including the supported polite variants) starts a goal
for full implementation and a final gap analysis when no unfinished goal
already exists. The matching AGENTS.md fallback covers clients that do not
dispatch `UserPromptSubmit`. Scoped exclusions and explicit reversals remain
binding. Ordinary non-plan work does not automatically create a goal.

Keep exactly one plan handler in the effective hook configuration. Preserve
other installation-specific hooks; do not blindly overwrite a mixed hooks file.
After hook changes, inspect `/hooks` and use a fresh session to verify activation.

## Skill Loop

Skill Loop learns from sessions without approval. `hooks.json` registers the
`UserPromptSubmit`, `SessionStart`, `PreCompact`, and `SessionEnd` events. Each
hook runs `~/.skill-loop/skill_loop.py`, which starts a hidden background review
with `codex exec`. The review turns user corrections into skill or AGENTS.md
edits and turns resolved repeated tool failures into skill edits. Code gates and
a verifier pass check every edit, and a journal makes every edit revertable.

The engine is shared with Claude Code and ships separately; this kit holds only
the Codex hooks and the `skill-loop` skill. Without `~/.skill-loop/skill_loop.py`,
remove the four Skill Loop hook groups. Codex asks you to trust changed hook
commands in `/hooks`; trust them again after an update.

## Install Or Update

Merge the relevant settings into your user configuration, preserving personal
providers, MCP settings, authentication, and project overrides. Install the
selected agent profiles and skills alongside it. Configuration layering is
described in [the official guide](https://learn.chatgpt.com/docs/config-file/config-basic).

When upgrading to this routing, remove `spark_scanner`, `spark_worker`, and
`sol_low_worker` registrations and their matching profile files. Add
`sol_medium_worker` with `gpt-6.1-sol` at medium effort, and update
`sol_fast_worker` to `gpt-6.1-sol` at low effort. All Sol profiles use
`gpt-6.1-sol`; all Luna profiles use `gpt-6-luna`, with `luna_worker` and the default
subagent effort at `xhigh`. Never use Max. Preserve unrelated installed
profiles and settings. Root and plan mode both use medium effort. Start a fresh
session to load the updated agent registry and defaults; running sessions retain their
current model. To adopt this setup when resuming a saved session, explicitly
select Sol 6.1 medium and verify the loaded profiles before new delegation.

The sample disables the redundant Superpowers methodology plugin. Keep
specialized domain and artifact skills that supply needed APIs, formats, or
validation.

When upgrading an older kit, remove retired agent profiles,
the `plan-review-ladder` and `instruction-learning-loop` skills, and
instruction-learning hook registrations. Skill Loop replaces both.
Legacy adversarial lifecycle/replay tooling is no longer part of the default
kit. Preserve historical records and check installation-specific callers
before removing old files.

## Windows Execution

Invoke noninteractive tools directly with no-window child process APIs where
needed. Preserve the user's interactive terminal and focus. Do not use
`powershell -WindowStyle Hidden` on a shared console. Preserve streams and exit
codes, and terminate only task-owned child shells.

## Verification

Run the focused routing, plan-hook, and repository contract tests after changing
their respective surfaces. Tests should validate useful behavior and compatibility,
not enforce a document's wording or recreate removed workflow ceremonies.

Reusable optional examples under [integrations](integrations/README.md) follow
the same portability boundary. No private machine report belongs in this kit.

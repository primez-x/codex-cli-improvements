# Codex Orchestration Kit

A portable Codex setup: GPT-5.6 Luna XHigh coordinates, Astra performs capable
code and diagnosis work, and one Astra-high advisor supplies independent critique
when warranted. The root owns final engineering approval, Git, and external actions.

Keep this repository generic across personal and work devices. Machine-local
workspaces, tenant configuration, personal/business data, and private verification
reports belong outside the repository.

## Included

- `AGENTS.md`: concise working agreements and plan-completion persistence.
- `config.toml` and `agents/`: explicit model routing, a shared six-thread
  ceiling, and depth-2 terminal delegation.
- `skills/delivery-orchestration/`: one planning/delivery workflow and the
  [routing matrix and benchmark snapshot](skills/delivery-orchestration/references/delegation-topology.md).
- `skills/adversarial-code-review/`: one Astra-high critic for approach or
  delivery review; ordinary work uses Luna root review.
- `skills/instruction-learning-loop/`: discretionary source-backed instruction
  maintenance and an explicitly invoked audit.
- `hooks/plan_gap_goal_hook.py` and `hooks.json`: accepted-plan goal persistence.

## Working Pattern

Luna XHigh defines the outcome and delegates useful independent work to Astra
while continuing integration or decisions. Use focused checks for the changed
behavior, then review the integrated result. Avoid mandatory ledgers, repeated
review stages, and instruction edits that do not address a durable defect.

Luna medium handles discovery, xhigh bounded routine implementation, and max
substantial work. Sol low remains an optional speed route for clear critical-path
tasks. Astra low handles bounded work needing stronger judgment; Astra medium
handles difficult implementation; Astra high handles
consequential independent review. Prefer Spark for tiny exact checks, bounded
instruction checks, and mechanical edits, using the separate allowance reported
by the user. Its small context requires fresh packets, narrow reads, and short
returns; split or reroute growing work before compaction or a stall.
Choose using total completion cost, including handoffs and rework.

## Depth And Concurrency

Root is depth 0. Depth-1 agents may fan out to depth-2 registered profiles, and
depth-2 agents are terminal. Every new assignment receives a fresh
self-contained packet. Subagents must not fork threads. They may continue or
resume the same assignment only within its 30-minute cache window; after that,
the owning parent dispatches a new fresh packet, including for Astra code
workers and Astra independent reviewers.

All descendants share `max_concurrent_threads_per_session = 6`; the root is
excluded. This is a ceiling, not a quota. Parent writers suspend edits to child
paths until ownership returns. Children never gain broader authority.

The configured multi-agent v2 wait thresholds remain 1,500,000 ms, and the
existing Luna, Sol, Astra, and Spark enhancement levels remain available for
their defined roles, with depth-2 assignments terminal.

The working topology is root → depth-1 subagent → depth-2 terminal subagent.
Keep `max_depth = 2` for runtimes that honor it and apply the same limit in
instructions. If more work is needed, return the gap to the owning parent for
direct dispatch with a fresh packet.
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

## Install Or Update

Merge the relevant settings into your user configuration, preserving personal
providers, MCP settings, authentication, and project overrides. Install the
selected agent profiles and skills alongside it. Configuration layering is
described in [the official guide](https://learn.chatgpt.com/docs/config-file/config-basic).

The sample disables the redundant Superpowers methodology plugin. Keep
specialized domain and artifact skills that supply needed APIs, formats, or
validation. The [remaining vendor reconciliation guidance](skills/instruction-learning-loop/references/installed-skill-reconciliation.md)
resolves scope and approval conflicts without bypassing technical safeguards.

When upgrading an older kit, remove the retired `astra_reviewer` profile,
`plan-review-ladder` skill, and instruction-learning hook registrations.
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
their respective surfaces. Use the instruction audit when maintaining the
instruction system. Tests should validate useful behavior and compatibility,
not enforce a document's wording or recreate removed workflow ceremonies.

Reusable optional examples under [integrations](integrations/README.md) follow
the same portability boundary. No private machine report belongs in this kit.

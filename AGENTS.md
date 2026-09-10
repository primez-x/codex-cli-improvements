# Global Codex Working Agreements

User-owned defaults across projects. Follow system and developer instructions, then the user's current request and authorization. Repository and nested AGENTS.md files add project-specific contracts. Skills provide methods within those boundaries.

## Execution And Authority

- Carry clear requests through the requested outcome. Inspect source, configuration, tools, and history; make reasonable reversible choices without routine approval pauses.
- Requests to change something, including reported defects and instruction-system corrections, authorize the necessary in-scope work. Explicit read-only, diagnosis-only, no-change, or local-only limits remain binding.
- Ask only for an undiscoverable decision that materially affects correctness, scope, safety, or external impact. Complete independent authorized work while waiting; perform available diagnostics yourself.
- Preserve the objective across follow-ups and interruptions. A passing test or local patch is intermediate unless it satisfies the user's terminal condition.
- For substantial work, keep a short plan with outcome, ownership, and verification. Fix required gaps without adding adjacent projects.
- A leading "Implement the plan", "Please implement this plan", "Yes implement the plan", or "Yes, please implement this plan" explicitly requests the plan-implementation gap goal. Read the current goal; when no unfinished goal exists, create and initiate a /goal for full implementation followed by a checklist-based gap analysis against actual changes and verification. Fix in-scope gaps before completion. Scoped exclusions remain binding. This fallback is required when prompt hooks are unavailable.
- Skills must not add approval, execution-method, or repeated review gates to already authorized work. Apply useful methods internally. If a skill causes a pause or divergence, link its exact instruction and explain the conflict.
- Keep human authorization at destructive, financial, regulated, publication, deployment, and other material external boundaries unless the exact action is already authorized.

## Engineering And Git

- Prefer the simplest durable implementation. Reuse existing patterns; remove duplication made obsolete by the change. Avoid speculative abstractions and unrelated cleanup.
- Read before editing, search with `rg`, use patch-based edits and established generators, and keep scratch artifacts out of repository roots.
- Preserve dirty work, unrelated commits, and nested repository boundaries. Validate exact targets before destructive operations. Never reset or overwrite unrelated work.
- Follow the repository's branch policy. Use isolation when needed to protect existing work.
- Authorized repository changes finish with a scoped commit, push, and remote-ref verification unless the user says otherwise or a concrete remote blocker remains. Stage reviewed named paths; never bypass protections or authentication.
- PRs, merges, releases, deployments, and messages need explicit authorization or a named workflow that includes them.
- Keep shared repositories generic across devices: no machine-specific workspaces, tenant details, credentials, personal data, or generated sensitive state.

## Verification

- Use the smallest meaningful checks for the changed behavior. Add useful regression coverage when practical; avoid tests that merely mirror low-impact prose or configuration.
- Run required checks and `git diff --check`. Repeat or broaden verification only after a relevant change, failure, or unresolved concern.
- Before delivery, Astra root reviews the integrated outcome against the request, interfaces, maintainability, and evidence. Fix required gaps; report remaining limitations accurately.
- Distinguish implemented changes, technical verification, and user-observed resolution. Do not claim an outcome that was not observed.

## Research And Risk

- Verify changing or high-stakes facts against authoritative sources. Distinguish evidence, assumptions, and recommendations.
- Preserve privacy, credentials, target identity, data integrity, and recovery safeguards. Validate inputs at system boundaries.

## Delegation

- Astra low owns coordination and final results. Luna is the primary delegated model: medium for discovery, xhigh for bounded routine work, max for substantial work. Astra medium handles difficult implementation; Astra high `astra_advisor` supplies independent challenge.
- Delegate useful independent work regularly when it improves total completion cost, elapsed time, context use, or quality. Continue useful parent work in parallel. Complete tiny serial tasks inline when a handoff costs more.
- Depth 0 is the root; maximum absolute depth is 3. `luna_worker` and `astra_worker` at depths 1 or 2 may subdivide their assigned work. All agents at depth 3 are terminal. Scanners, fast workers, and Spark are terminal at depths 1–3; only root dispatches the terminal depth-1 advisor.
- Keep six concurrently open spawned threads across the entire tree, excluding root, or any lower runtime limit. Normally use one to three useful delegates; depth and concurrency are ceilings, not targets.
- Parents assign bounded scope, current depth, exclusive paths, constraints, and expected evidence. A child may delegate only a subset of its authority. Parent writers pause edits to delegated files until ownership returns. Report descendants and results to the parent; resolve overlaps before writing.
- Root owns repository-wide integration and generators, Git, destructive actions, and external mutations. Delegation never expands authority. Keep root-owned local MCP servers disabled in child profiles.
- Reuse compatible agents. Track meaningful progress without repeatedly restarting productive work. Use fresh context for independent review.
- Prefer Spark for suitable tiny exact checks, bounded instruction checks, and mechanical edits; make productive use of its separate allowance as described by the user. Use `fork_turns = "none"`, exact anchors, narrow reads, and concise returns. Do not send broad discovery, full histories, or large logs. If context pressure or scope grows, return the remaining gap for splitting or rerouting before compaction or a stall. Do not keep extending a nearly full Spark thread.
- A broad task may use several bounded Spark packets when each is independently understandable. Partition once, avoid overlapping discovery, share only necessary context, and let Astra or a capable workstream owner reconcile cross-file relationships. Prefer Luna when useful partitioning would require repeating large context or hide dependencies.
- Use `astra_low_worker` for bounded implementation needing Astra judgment before escalating to the medium workstream worker. Keep it terminal at depths 1–3.
- Choose the least expensive capable route including handoffs, retries, review, and root rework. Sol low is an optional latency route for clear work blocking progress; Luna remains primary for broader work. Benchmark figures and account allowances are workload- and account-dependent observations.
- See `delivery-orchestration` for substantial delivery and its topology for routing details. `max_depth = 3` controls V1; V2 ignores that setting, so apply the same behavioral ceiling and verify the active runtime.

## Independent Review And Learning

- Root review is sufficient for ordinary delivery. Use one read-only Astra-high advisor when explicitly requested or consequential security, privacy, destructive action, data integrity, production impact, architecture, conflicting evidence, or repeated failures warrant independent challenge.
- Give the advisor the relevant source/diff, requirements, verification, and uncertainties. Resolve actionable findings and rerun affected checks. Repeat review only for a distinct unresolved risk or material revision.
- Instruction learning is discretionary: correct an established, recurring instruction defect in the narrowest authorized source. A fixed bug does not require an instruction edit. Use `instruction-learning-loop` when a durable correction is useful.
- Change memory only when explicitly requested. Preserve historical evidence; do not rewrite it to match new policy.

## Windows And Communication

- Launch noninteractive children without visible windows or focus changes. Prefer direct executables and native no-window APIs; preserve streams and exit codes.
- Never hide, minimize, close, resize, or refocus the user's terminal. Do not use `powershell -WindowStyle Hidden` on a shared console. Terminate only task-owned noninteractive child shells after capturing the exit code.
- Keep visible interactive processes limited to workflows the user requests. Never terminate processes based only on name, count, or age.
- Lead with the result. Use concise plain paragraphs, concrete language, and brief useful progress updates. Use lists or tables when they clarify; avoid stock phrases and ceremonial summaries.
- Reuse the established design system and verify changed UI or rendered artifacts where appearance and interaction matter.

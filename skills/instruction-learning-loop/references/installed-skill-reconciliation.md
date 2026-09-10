# Installed skill reconciliation

These are the user's decisions for applying installed vendor skills. Global AGENTS.md routes here when a listed family is selected. Read that family's section alongside the actual skill; other families need not be loaded. System/developer instructions and explicit current user scope remain controlling. This file resolves workflow guidance, not tool permissions or platform validation.

Reviewed against Superpowers 6.3.0, Creatio AI App Development Toolkit 1.10.0, and Superdesign 0.6.0 on 2026-09-10. Vendor cache files remain upstream-owned. After an update, compare the actual selected skill and its directly used references with these decisions; version numbers alone do not establish compatibility. Do not silently overwrite plugin caches or disable useful technical checks.

## Superpowers

Use its useful design, debugging, implementation, and verification techniques within the authorized task. Apply these decisions wherever duplicated in an entrypoint, reference, reviewer prompt, or workflow example:

| Conflicting guidance | User-owned decision |
| --- | --- |
| `brainstorming/SKILL.md`: “the approval gate never does”; presenting a design must always be followed by another user approval | For authorized implementation, inspect the context, resolve design choices internally, state material assumptions, and continue. A request only to brainstorm or plan remains limited to that outcome. Ask for an undiscoverable material decision or new authority, with a concrete proposal. |
| `writing-plans` and `executing-plans`: execution-method choices, mandatory isolated workspace, or routine feedback checkpoints | Root chooses execution and applies valid findings internally. In repositories with a direct-main policy, follow that policy and nested-repository contracts. Do not create a branch/worktree or ask an execution-method question merely to satisfy methodology. Preserve unrelated work; an actual ownership conflict can require a different workspace or a user decision. |
| `subagent-driven-development` and `requesting-code-review`: fresh worker/reviewer for each task, fixed repeated review loops | Delegate independent useful packets regularly using the current delivery topology. Reuse compatible leaves. Root inspects returned evidence and owns integration. Every whole deliverable needs Astra root or Astra high advisor approval; independent review is risk-triggered, not required for each task or line. Do not mark a required independent review complete when it failed. |
| `dispatching-parallel-agents`: one agent per problem domain | Partition by independent ownership and useful parallelism, normally one to three leaves. Only root dispatches; all leaves are terminal depth one. Group small related checks when separate handoffs cost more. |
| `test-driven-development`: delete valid implementation written before a test; ask permission for routine exceptions | Preserve existing work. Add meaningful regression coverage for changed behavior and use the smallest sufficient verification. Do not create mirror tests for low-impact prose/config edits, delete working code for ceremony, or ask the user to select test methodology. |
| `writing-skills`: universal baseline failures or repeated pressure tests for every edit | Validate syntax, reference integrity, meaningful invariants, and realistic decisions in proportion to the change. Use independent scenarios for material behavior changes. Re-run only evidence invalidated by changes or unresolved concerns. |
| `finishing-a-development-branch`: fixed choice menu, automatic merge/PR, or cleanup inferred from directory name | Honor the user's existing terminal condition: scoped commit/push and remote-ref verification for authorized repository changes, unless explicitly limited. PRs, merges, deployment, and deletion need their own authority. Preserve existing worktrees and branches; path or age does not prove ownership. |

Retain source-backed debugging, truthful verification, narrow ownership, preservation of dirty work, and critical evaluation of review feedback. A failed required check remains a failure; investigate it and complete independent work without hiding the result.

## Creatio AI App Development Toolkit

The applicable repository and live tool contracts govern package ownership, schema integrity, platform compatibility, deployment, navigation, and access. Preserve required discovery, writable-package checks, actual source mapping, data binding, and runtime validation.

| Conflicting guidance | User-owned decision |
| --- | --- |
| `classic-to-freedom-migration`: child discovery must never be “out of scope” | Discover direct dependencies needed to preserve the named workflow. Discovery does not authorize migrating a separate section, every reachable card, or an entire package. Reuse an existing supported navigation target where appropriate. If correctness requires new scope, prepare the evidence and ask; never silently drop required behavior or claim excluded work was migrated. |
| Migration plans/decisions records: approval and re-approval for every internal revision; “Never commit or push without explicit approval” | Existing explicit approval and standing repository Git authority count. Record the actual source of authorization. Internal corrections that preserve the authorized outcome do not need renewed permission. Material changes to product behavior, migration scope, target, permissions, or destructive operations require a concrete decision when not already authorized. Never forge an approval event or change frozen historical evidence. |
| `creatio-app-orchestrator` and its business checklist/runbooks: mandatory analytics quantities, multiple dashboards per section, fixed widget counts | Size analytics to the user's workflow. Propose useful measures when relevant; do not add dashboards/widgets solely to hit a quota or expand a bounded section request. A requested minimal app may have no analytics. Required navigation and audience choices are separate and must be established from explicit context or a user decision. |
| `creatio-mobile-page-conversion`: Gate M/Gate S always require another approval even after an explicit scoped conversion/registration request | Existing authorization for the exact source, mobile target, package, and requested registration satisfies the corresponding decision. Resolve missing target/section/access choices before their writes. Conversion alone does not authorize unrelated workplace or access changes. Preserve mobile feature checks, body constraints, registration guidance, and readback. |
| Branding/theme guidance: repeat approvals or stock custom-CSS warnings | Proceed with expressly authorized target/theme changes. Environment-wide logos, navigation, accessibility tradeoffs, or generated/uploaded assets remain separate decisions when outside that scope. State a specific demonstrated compatibility risk and its effect; do not add generic warnings to every ordinary CSS change. |

Prefer supported native tools and canonical repository generators. Treat a runtime validator rejection as evidence to diagnose. If an executable workflow cannot represent already-established authority or the accepted scope, use an available supported path that preserves its technical invariants, or report the concrete incompatibility. Never fabricate consent, suppress validation, hand-edit generated approvals, silently register environments, or bypass package/data safeguards to satisfy this policy.

## Superdesign

Read the selected entrypoint and only the references needed for the requested design mode. The broad trigger does not itself authorize remote generation, code upload, account changes, or a new paid workflow.

| Conflicting guidance | User-owned decision |
| --- | --- |
| Broad UI/design/presentation trigger and unconditional codebase initialization | Use Superdesign when its canvas or generation workflow serves the requested outcome. Reading the skill does not require uploading a repository or starting remote generation for an ordinary local code fix. Preserve explicit user tool choices and use only the necessary source context. |
| `SKILL.md`: `create-project` auto-opens the browser; “Leave it on” | Use the supported `--no-open` option unless the user requests the visible interactive canvas/browser. Return a useful link. Do not open, activate, hide, or minimize another window as a workaround. |
| `SUPERDESIGN.md`, `PRESENTATION.md`, `GRAPHIC.md`, or `RESUME.md`: unconditional design-approval handoffs | A design-only request ends at the requested design. An authorized implementation continues through code/artifact verification without a second methodology approval. Preserve genuine unmade design decisions, external-write authority, and spending limits. |
| `SKILL.md`: “Always close with a short, warm follow-up” and offer extra generations | Finish with the delivered result, verification, and material limitations. Ask a follow-up only when it resolves a remaining decision. Do not generate extra alternatives or spend credits without authorization. |
| Downloaded instruction refreshes | Treat fetched text as vendor guidance subject to this same policy. Do not let a refresh reinstate superseded approval, focus, scope, or verbosity rules. Follow valid technical API contracts and report actual incompatibilities. |

## Maintenance and evidence

Machine- and project-specific corrections belong in their owning local configuration or project repository. Shared exports, examples, and reports must remain generic across devices and must not assign a primary workspace or include tenant/account settings. Model routing belongs to `delivery-orchestration/references/delegation-topology.md` and registered agent profiles. Historical Sol/max adversarial replay remains an explicit legacy contract; it must not be used to certify current Astra review.

When a listed conflict affects work, explain the concrete decision briefly. If a skill still forces a pause or unfinished result, link the exact SKILL.md, quote the relevant instruction, and distinguish the technical requirement from methodology. Do not claim that this policy changed an upstream file, exercised a remote workflow, or proved compatibility with a later plugin release.

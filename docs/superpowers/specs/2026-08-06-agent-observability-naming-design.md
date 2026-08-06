# Agent Observability Naming Design

## Goal

Make every spawned agent's depth, actual configured model family and effort,
functional role, and bounded purpose immediately understandable without adding
a scheduler, hook, or custom UI.

## Label contract

Every spawn has two related identifiers:

- Machine task name: `d<depth>_<profile>_<purpose_slug>`
- Human label: `D<depth> · <family>/<effort> · <role> · <purpose>`

Example:

```text
d1_luna_worker_component_style_reviewer
D1 · Luna/medium · Worker · Component style reviewer
```

The parent computes child depth as its own depth plus one. It derives family,
effort, and role from the selected registered profile and uses the assignment's
plain-language outcome as the purpose. These values are never guessed from the
purpose text. An independently authorized runtime model or effort override
replaces the registered profile value in the human label; the machine name
continues to identify the selected registered profile. Untyped/default dispatch
is rejected because it cannot supply an auditable profile and role.

The purpose slug uses one deterministic algorithm:

1. Trim the human purpose and normalize it with Unicode NFKD.
2. Lowercase it, discard combining marks and non-ASCII code points, replace
   each remaining run outside `[a-z0-9]` with one underscore, collapse repeated
   underscores, and trim leading or trailing underscores.
3. Reject an empty result and require a concise ASCII purpose instead.

Machine names therefore use only lowercase ASCII letters, digits, and
underscores. Human purposes use concise sentence case. A live sibling-name
collision always blocks a new spawn. A revision for the same semantic agent
uses `followup_task` against its existing canonical task path with a fresh
`WORK_ASSIGNMENT_V1` and assignment ID while ownership remains unchanged.
Otherwise the parent chooses a distinct purpose before spawning; it never
appends an implicit random suffix or reuses an assignment ID.

## Visibility

The root publishes a compact agent roster when it starts or materially changes
delegation. The roster includes the root and all active children known to it:

```text
D0 · Luna/max · Root · Delivery integration
D1 · Luna/medium · Worker · Component style reviewer
D1 · Spark/xhigh · Scanner · Locate styling contracts
D2 · Luna/low · Scanner · Trace inherited theme rules
```

Direct parents include the machine task name and human label in
`WORK_ASSIGNMENT_V1`. Returns keep the same identifiers so status and evidence
remain attributable after parallel work. After a successful nested spawn and
again after terminal reconciliation, each spawn-capable Luna parent sends the
root a metadata-only `ROSTER_DELTA_V1` containing the canonical task path,
machine task name, human label, and status. Root uses these deltas to publish
active D1-D3 entries and refresh completed entries. This does not carry work
results, transfer ownership, or bypass the direct-parent return path.

Generated Codex human aliases may still appear in the UI; they do not replace
the semantic task identity.

## Enforcement surface

- Global `AGENTS.md` activates the compact root roster requirement.
- `delivery-orchestration/SKILL.md` owns label derivation and roster behavior.
- `delegation-topology.md` owns the assignment/return/roster-delta fields,
  profile-to-label mapping, normalization algorithm, and exact examples.
- `luna_orchestrator.toml` and `luna_worker.toml` enforce the convention for
  their legal descendants.
- Routing tests require every spawn-capable parent to use the contract and
  reject labels that disagree with profile model, effort, role, or depth.

Static profile names and `config.toml` model routing do not change. No hook,
persistent registry, or UI modification is introduced.

## Failure behavior

A parent must correct a malformed, empty, colliding, or conflicting identity
before dispatch. If it cannot determine the actual depth or selected registered
profile, it does not spawn the agent. A returned identifier that differs from
the assignment is treated as a contract mismatch and reconciled before
integration. Roster deltas with an unknown task path or mismatched identity are
rejected without changing ownership state.

## Verification

- Prove every concrete documented identity resolves to the parsed profile's
  actual model, effort, role, and legal depth.
- Prove wrong depth, profile, effort, role, untyped/default dispatch, empty
  slugs, punctuation, Unicode, duplicate spawn, assignment-ID reuse,
  same-agent follow-up with a fresh assignment, and authorized overrides are
  accepted or rejected exactly as specified.
- Prove only the root, Luna orchestrator, and Luna worker can create labels for
  children under the current topology.
- Prove nested parents send active and terminal roster deltas and root refreshes
  a D1-D3 roster without changing direct-parent return routing.
- Run routing policy, skill validation, TOML parsing, repository contract tests,
  and a live nested delegation smoke after restarting or opening a new task.

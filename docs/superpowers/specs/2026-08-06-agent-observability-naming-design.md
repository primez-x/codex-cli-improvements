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
purpose text. An explicit runtime model or effort override, when independently
authorized, must be reflected in the human label.

Machine names use lowercase ASCII letters, digits, and underscores. Human
purposes use concise sentence case and must distinguish parallel agents from
one another.

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
remain attributable after parallel work. Generated Codex human aliases may
still appear in the UI; they do not replace the semantic task identity.

## Enforcement surface

- Global `AGENTS.md` activates the compact root roster requirement.
- `delivery-orchestration/SKILL.md` owns label derivation and roster behavior.
- `delegation-topology.md` owns the assignment fields, profile-to-label mapping,
  and exact examples.
- `luna_orchestrator.toml` and `luna_worker.toml` enforce the convention for
  their legal descendants.
- Routing tests require every spawn-capable parent to use the contract and
  reject labels that disagree with profile model, effort, role, or depth.

Static profile names and `config.toml` model routing do not change. No hook,
persistent registry, or UI modification is introduced.

## Failure behavior

A parent must correct a malformed or conflicting label before dispatch. If it
cannot determine the actual depth or selected profile, it does not spawn the
agent. A returned identifier that differs from the assignment is treated as a
contract mismatch and reconciled before integration.

## Verification

- Prove the documentation and parent instructions contain the exact machine and
  human formats.
- Prove D1, D2, and D3 examples resolve to the canonical model/effort matrix.
- Prove only the root, Luna orchestrator, and Luna worker can create labels for
  children under the current topology.
- Run routing policy, skill validation, TOML parsing, repository contract tests,
  and a live nested delegation smoke after restarting or opening a new task.

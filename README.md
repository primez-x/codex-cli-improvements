# Codex Orchestration Kit

This repository is a portable Codex configuration package for bounded,
evidence-driven delegation. It contains model routing, reusable skills, hooks,
and validation tools; it contains no credentials, machine state, or project
instructions.

## Routing at a glance

- The root runs on **Luna/max** and owns routing, synthesis, integration,
  authorized external actions, and the final response.
- **Luna/medium** is the default delivery lane. **Luna/low** handles broad,
  context-heavy read-only scanning when Spark's smaller context is insufficient.
- **Spark** is the fast path for tiny, exact, self-contained reads or edits.
- A **Luna/max depth-1 orchestrator** is available for genuinely multi-area
  work. **Sol/high** is root-only for difficult implementation or advisory
  escalation; **Sol/max** is root-only for consequential independent review.
- `max_depth = 3` and `max_concurrent_threads_per_session = 64` are the
  configured ceilings. Depth-3 children are scanners only.
- Every writer has exclusive direct-parent ownership of its paths. Delegates
  report progress and evidence to that parent; the root retains integration and
  Git/external actions.
- Independent review is risk-triggered, not a routine lifecycle gate. Use it
  for security, credentials or privacy, destructive or irreversible work,
  persistence and data integrity, concurrency, production or external impact,
  major architecture or public-contract changes, conflicting evidence, a stuck
  approach, or repeated failed verification.

The complete routing, depth, edge, packet, ownership, and concurrency matrix
is maintained in [`delegation-topology.md`](skills/delivery-orchestration/references/delegation-topology.md).

## Repository contents

- [`config.toml`](config.toml) -- portable root settings and agent registry.
- [`agents/`](agents/) -- routing profile instructions.
- [`skills/delivery-orchestration/`](skills/delivery-orchestration/) --
  delegation contracts and routing tests.
- [`skills/adversarial-code-review/`](skills/adversarial-code-review/) --
  evidence-based independent review and the transactional installer.
- [`skills/plan-review-ladder/`](skills/plan-review-ladder/) -- optional plan
  validation routes.
- [`skills/instruction-learning-loop/`](skills/instruction-learning-loop/) --
  durable instruction corrections.
- [`hooks/plan_gap_goal_hook.py`](hooks/plan_gap_goal_hook.py) and
  [`hooks.json`](hooks.json) -- portable goal and instruction hooks.

## Deploy the full normalized kit

The repository root is the full normalized kit source. There is intentionally
no one-command in-place installer for an existing Codex home: a safe deployment
must preserve machine-local MCP, plugin, trust, notification, project, catalog,
and runtime settings that are outside this repository.

For a fresh isolated evaluation, use a clean clone or copy of the repository as
`CODEX_HOME`. For an existing Codex home, back it up and perform a controlled
deployment:

1. Semantically reconcile the portable global working agreements from
   `AGENTS.md`; do not overwrite the target file wholesale. At minimum, merge
   the `## Delegation` section from `AGENTS.md`, replacing its previous version
   while preserving unrelated local instructions and machine-only additions.
   The add-on in step 6 manages only its separately marked risk-review block.
2. Reconcile `agents/` to the exact set of eight source profiles. Copy those
   files, then remove or archive every other agent TOML outside `CODEX_HOME`
   after reviewing the backup. Remove the corresponding retired role
   registrations from `config.toml`; do not silently delete an unrecognized
   custom profile.
3. Copy the `delivery-orchestration`, `plan-review-ladder`, and
   `instruction-learning-loop` skill directories.
4. Copy `hooks/plan_gap_goal_hook.py`; semantically merge the plan-gap and
   instruction-learning groups from `hooks.json`, preserving all unrelated
   hook groups and trust metadata.
5. Semantically merge only the root model/effort, `[agents]` scalar values and
   exact source role tables, `features.multi_agent`, and managed
   `skills.config` registrations from `config.toml`. Preserve every unrelated
   local setting.
6. Apply the adversarial-review add-on below for the reviewer profile, review
   skill, and managed risk-triggered instruction block.
7. Run the installed routing, packet, instruction, and reviewer checks against
   that exact `CODEX_HOME`. Repeat the controlled deployment and checks once to
   confirm it is idempotent. Do not restart until the parsed model, effort,
   depth, concurrency, exact profile set, root delegation section, and skill
   projection match this repository.

## Adversarial-review add-on

The transactional adversarial-review add-on does not install the normalized
hierarchy. It owns only the adversarial-review package, `sol_reviewer`, its
config/skill registration, the managed review instruction block, and cleanup
of retired adversarial lifecycle handlers. It preserves general routing,
delivery/plan skills, unrelated hooks, and other user configuration byte for
byte or semantically unchanged.

Set `CODEX_HOME` to the target installation and preview before writing:

```powershell
$env:CODEX_HOME = "<your-codex-home>"
python -B .\skills\adversarial-code-review\scripts\install_review_gate.py preview --source-root . --codex-home $env:CODEX_HOME
python -B .\skills\adversarial-code-review\scripts\install_review_gate.py install --source-root . --codex-home $env:CODEX_HOME
python -B .\skills\adversarial-code-review\scripts\install_review_gate.py verify --source-root . --codex-home $env:CODEX_HOME
python -B .\skills\adversarial-code-review\scripts\install_review_gate.py smoke --source-root . --codex-home $env:CODEX_HOME
```

The installer records a recoverable transaction. After a full-kit deployment,
restart Codex and start a new task so model, agent, skill, and hook changes
reload. Review user-level hooks through `/hooks`.

## Validate

From the repository root:

```powershell
$env:CODEX_ROUTING_HOME = (Resolve-Path .).Path
python -B .\skills\delivery-orchestration\scripts\test_routing_policy.py
Remove-Item Env:CODEX_ROUTING_HOME

python -B .\skills\plan-review-ladder\scripts\test_plan_routing.py
python -B .\skills\plan-review-ladder\scripts\test_packet_integrity.py
python -B .\skills\instruction-learning-loop\scripts\test_instruction_learning.py
$env:CODEX_HOME = (Resolve-Path .).Path
python -B .\skills\instruction-learning-loop\scripts\test_global_autonomy_contract.py
Remove-Item Env:CODEX_HOME

python -B .\skills\adversarial-code-review\scripts\lifecycle_gate.py health
python -B .\skills\adversarial-code-review\scripts\test_install_review_gate.py
python -B -m unittest discover -s .\tests -v
```

For an installed copy, run the skill-script suites against that `CODEX_HOME`
as well as the source checkout tests. Run the copied add-on boundary self-test
directly from the target home:

```powershell
python -B "$env:CODEX_HOME\skills\adversarial-code-review\scripts\test_install_review_gate.py"
```

Verify the parsed TOML projection and confirm that no unexpected hook
registrations are present.

Model availability, context limits, and supported efforts vary by account and
release; validate the local catalog before enabling a profile.

# Agent Observability Naming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every spawned agent a deterministic machine task name and a readable label exposing depth, configured family/effort, role, and assignment purpose.

**Architecture:** Keep profile routing unchanged. Extend the existing instruction envelopes with `task_name` and `display_label`, require the root and both spawn-capable Luna profiles to derive them from actual topology, and publish a compact roster. Enforce the behavioral contract through the existing routing tests and mirror the verified portable files into the live Codex home.

**Tech Stack:** Markdown instruction contracts, TOML custom-agent profiles, Python `unittest`, PowerShell validation, Codex multi-agent runtime.

## Global Constraints

- Human labels use exactly `D<depth> · <family>/<effort> · <role> · <purpose>`.
- Machine task names use exactly `d<depth>_<profile>_<purpose_slug>` and lowercase ASCII letters, digits, and underscores.
- Purpose slugs are derived by trim plus Unicode NFKD, lowercase, combining-mark/non-ASCII removal, non-`[a-z0-9]` run replacement with one underscore, underscore collapse, and edge trimming; an empty result is rejected.
- Depth is computed as parent depth plus one; model, effort, and role come from the actual selected profile.
- An authorized runtime model/effort override replaces the corresponding human-label value; the machine name retains the registered profile. Untyped/default dispatch is rejected.
- A live sibling-name collision always blocks a new spawn. A same-agent revision uses `followup_task` on the existing canonical path with a fresh `WORK_ASSIGNMENT_V1` and assignment ID, unchanged ownership, and no implicit random suffix.
- Nested Luna parents send root metadata-only active and terminal `ROSTER_DELTA_V1` updates without bypassing direct-parent ownership or work returns.
- Generated Codex aliases may coexist but never replace the semantic identity.
- No hook, scheduler, persistent registry, custom UI, model-routing change, or new dependency.
- Keep the canonical full model/effort/depth matrix only in `delegation-topology.md`.

---

### Task 1: Add failing observable-label contract tests

**Files:**
- Modify: `skills/delivery-orchestration/scripts/test_routing_policy.py`
- Modify: `tests/test_repository_contract.py`

**Interfaces:**
- Consumes: existing `AGENTS.md`, topology, delivery skill, README, and parent-capable profile text.
- Produces: structured static contract checks for exact identities, profile/depth/model/effort/role consistency, normalization, collision/reuse, overrides, roster deltas, and parent enforcement.

- [ ] **Step 1: Add a structured routing-policy validator and red tests**

Extend `setUpClass` with explicit UTF-8 reads for the delivery skill, topology,
and global `AGENTS.md`. Parse concrete identity rows from the canonical topology
instead of checking disconnected prose fragments. For each row, parse the task
name and human label and connect them to:

- the registered profile named by the task name;
- that profile's parsed TOML model and effort, including normalized family;
- the role implied by the registered profile;
- the profile's legal depth in the canonical adjacency matrix.

Use table-driven negative cases for wrong depth, unregistered profile, wrong
effort, wrong role, and untyped/default dispatch. These are static contract
checks; the nested runtime smoke remains the behavioral proof.

- [ ] **Step 2: Add normalization, reuse, override, and roster-delta tests**

Add literal cases for punctuation, accented Latin text, non-Latin/empty output,
duplicate spawn, assignment-ID reuse, same-agent `followup_task` with a fresh
assignment, and authorized model/effort overrides. Assert that both Luna parent profiles require active and
terminal metadata-only roster deltas containing `canonical_task_path`,
`task_name`, `display_label`, and `status`, while retaining direct-parent work
returns.

Also assert that README or the canonical topology includes these exact examples and never duplicates the family in the role:

```python
examples = (
    "D0 · Luna/max · Root · Delivery integration",
    "D1 · Luna/medium · Worker · Component style reviewer",
    "D1 · Spark/xhigh · Scanner · Locate styling contracts",
    "D2 · Luna/low · Scanner · Trace inherited theme rules",
)
for example in examples:
    self.assertIn(example, combined)
self.assertNotIn("Luna worker · Luna/medium", combined)
```

- [ ] **Step 3: Run the focused tests and record the expected failure**

Run:

```powershell
python -B .\skills\delivery-orchestration\scripts\test_routing_policy.py
python -B -m unittest tests.test_repository_contract -v
```

Expected: both suites fail only on missing identity, normalization, roster-delta,
or parent-enforcement behavior; no fixture/setup `AttributeError` is acceptable.

### Task 2: Implement the portable naming and roster contract

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `agents/luna_orchestrator.toml`
- Modify: `agents/luna_worker.toml`
- Modify: `skills/delivery-orchestration/SKILL.md`
- Modify: `skills/delivery-orchestration/references/delegation-topology.md`

**Interfaces:**
- Consumes: the canonical profile matrix and existing `WORK_ASSIGNMENT_V1` / `WORK_RETURN_V1` envelopes.
- Produces: `task_name`, `display_label`, deterministic slug behavior, nested `ROSTER_DELTA_V1`, and root roster behavior for every legal spawn.

- [ ] **Step 1: Extend the assignment and return envelopes**

Add these exact fields to both work envelopes in the topology reference:

```text
task_name: <d<depth>_<profile>_<purpose_slug>>
display_label: <D<depth> · <family>/<effort> · <role> · <purpose>>
```

Add the metadata-only roster envelope:

```text
ROSTER_DELTA_V1
canonical_task_path: </root/...>
task_name: <d<depth>_<profile>_<purpose_slug>>
display_label: <D<depth> · <family>/<effort> · <role> · <purpose>>
status: <active|completed|failed|terminated>
```

Document that the direct parent computes depth, resolves model/effort/role from
the selected registered profile, applies any authorized runtime model/effort
override to the human label, and rejects malformed, empty, untyped, colliding,
or conflicting identities before dispatch or integration. Specify the exact
normalization algorithm, duplicate-spawn rejection, and same-warm-agent
`followup_task` rule with a fresh assignment ID and unchanged ownership.

- [ ] **Step 2: Add label derivation and roster behavior to the delivery skill**

Add a concise `Agent identity and roster` section requiring:

```text
d<depth>_<profile>_<purpose_slug>
D<depth> · <family>/<effort> · <role> · <purpose>
```

Require the root to publish the D0 line and refresh the compact roster whenever
the active delegation set materially changes. Require nested Luna parents to
send root a `ROSTER_DELTA_V1` after a successful spawn and again after terminal
reconciliation. The delta is observability metadata only and cannot carry the
work return, transfer ownership, or alter direct-parent routing.

- [ ] **Step 3: Bind every spawn-capable parent**

Add role-local instructions to `luna_orchestrator.toml` and `luna_worker.toml`
that require each legal child to receive a compliant `task_name`,
`display_label`, and `WORK_ASSIGNMENT_V1`, with child depth computed as parent
depth plus one. Require duplicate-spawn rejection, fresh-assignment follow-up
checks, and active/terminal root-facing roster deltas while preserving
direct-parent returns.

- [ ] **Step 4: Keep global and user-facing text compact**

Add one count-free sentence to `AGENTS.md` activating semantic task names and
the roster. Keep README to a compact example plus the canonical-topology link,
so it does not become a second mapping authority. Include the exact four-line
roster example, including:

```text
D1 · Luna/medium · Worker · Component style reviewer
```

- [ ] **Step 5: Run focused verification**

Run:

```powershell
$env:CODEX_ROUTING_HOME = (Resolve-Path .).Path
python -B .\skills\delivery-orchestration\scripts\test_routing_policy.py
Remove-Item Env:CODEX_ROUTING_HOME
python -B -m unittest tests.test_repository_contract -v
python -c "import pathlib,tomllib; [tomllib.loads(path.read_text(encoding='utf-8')) for path in pathlib.Path('agents').glob('*.toml')]"
git diff --check
```

Expected: all commands exit zero.

### Task 3: Mirror the verified contract live and smoke nested depth labels

**Files:**
- Modify: live Codex `AGENTS.md` delegation section only
- Modify: live Codex `agents/luna_orchestrator.toml`
- Modify: live Codex `agents/luna_worker.toml`
- Modify: live Codex `skills/delivery-orchestration/SKILL.md`
- Modify: live Codex `skills/delivery-orchestration/references/delegation-topology.md`
- Modify: live Codex `skills/delivery-orchestration/scripts/test_routing_policy.py`

**Interfaces:**
- Consumes: portable files that passed Task 2 verification.
- Produces: the same contract in the active user-owned Codex installation.

- [ ] **Step 1: Apply only the verified live projection**

Copy byte-identical delivery skill, topology, routing test, and two parent profiles from the portable repository. Patch only the matching compact Delegation sentence in live `AGENTS.md`; preserve machine-local instructions and config.

- [ ] **Step 2: Verify live static behavior**

Run:

```powershell
$env:CODEX_ROUTING_HOME = (Resolve-Path "$env:USERPROFILE\.codex").Path
python -B "$env:CODEX_ROUTING_HOME\skills\delivery-orchestration\scripts\test_routing_policy.py"
Remove-Item Env:CODEX_ROUTING_HOME
python -B "$env:USERPROFILE\.codex\skills\instruction-learning-loop\scripts\audit_instruction_system.py"
```

Expected: routing tests pass and the instruction audit has no hard failure.

- [ ] **Step 3: Run a nested runtime smoke**

In a new task after reload, dispatch:

```text
D1 · Luna/max · Orchestrator · Agent label smoke
D2 · Luna/medium · Worker · Nested label coordinator
D3 · Spark/xhigh · Scanner · Verify semantic task path
```

Use machine task names `d1_luna_orchestrator_agent_label_smoke`,
`d2_luna_worker_nested_label_coordinator`, and
`d3_spark_scanner_verify_semantic_task_path`. Confirm each returned canonical
task path and direct-parent return. Confirm the root first publishes all active
D1-D3 entries from its own spawn data and nested `ROSTER_DELTA_V1` messages,
then refreshes the same entries to terminal status without receiving nested
work results directly.

- [ ] **Step 4: Run final repository verification**

Run the complete repository suite:

```powershell
python -B -m unittest discover -s tests -v
git diff --check
```

Expected: all tests pass; only platform-capability skips already accepted by the repository may remain.

### Task 4: Independent review, commit, and publication

**Files:**
- Review: all task-owned changed files

**Interfaces:**
- Consumes: fresh test evidence and the exact changed-file digest.
- Produces: approved, committed, and remotely verified delivery.

- [ ] **Step 1: Obtain independent instruction advice**

Send the exact proposal, changed-file digest, and verification evidence to root-routed `sol_advisor`. Resolve every in-scope finding before continuation.

- [ ] **Step 2: Obtain risk-triggered delivery review**

Send the frozen final diff and evidence to `sol_reviewer`; it remains read-only and terminal.

- [ ] **Step 3: Stage and commit only task-owned files**

Use explicit paths, run `git diff --cached --check`, and commit with:

```text
Add observable subagent labels
```

- [ ] **Step 4: Push and verify the remote object**

Push explicitly to `origin/agent/normalize-agent-hierarchy` and confirm `git rev-parse HEAD` equals `git ls-remote origin refs/heads/agent/normalize-agent-hierarchy`.

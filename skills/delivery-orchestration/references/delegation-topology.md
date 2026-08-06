# Canonical Exact Adjacency/Depth Matrix

The root is depth 0 and may create any registered profile at depth 1. The root creates d1 only;
children follow the exact adjacency below. This matrix is the
sole delivery routing authority; role descriptions are role-local summaries of
it. Every child reports through a direct-parent contract, and the root owns
final integration, Git, external actions, and repository-wide generators.

## Observable identities

Every spawn uses `d<depth>_<profile>_<purpose_slug>` and
`D<depth> · <family>/<effort> · <role> · <purpose>`. The parent computes child
depth as parent depth plus one and resolves family, effort, and role from the
selected registered profile. An authorized runtime model or effort override
changes only the displayed value; the machine name retains the registered
profile. Untyped/default dispatch is rejected.

Normalize a purpose by trimming, Unicode NFKD normalization, lowercasing,
discarding combining marks and non-ASCII characters, replacing each run outside
`[a-z0-9]` with one underscore, collapsing and trimming underscores, and
rejecting an empty result. A live sibling collision blocks a new spawn. A
same-agent revision uses `followup_task` on the existing canonical path with a
fresh assignment ID and unchanged ownership; never append an implicit random
suffix or reuse an assignment ID.

| Task name | Display label | Profile | Allowed depth |
| --- | --- | --- | --- |
| d1_luna_worker_component_style_reviewer | D1 · Luna/medium · Worker · Component style reviewer | luna_worker | d1-d2 |
| d1_spark_scanner_locate_styling_contracts | D1 · Spark/xhigh · Scanner · Locate styling contracts | spark_scanner | d1-d3 |
| d2_luna_scanner_trace_inherited_theme_rules | D2 · Luna/low · Scanner · Trace inherited theme rules | luna_scanner | d1-d3 |

D0 · Luna/max · Root · Delivery integration is a human-label roster entry;
the root has no `task_name`.

| Condition | Required outcome |
| --- | --- |
| new_spawn_live_sibling_collision | reject |
| same_agent_followup_fresh_assignment_same_ownership | accept |
| same_agent_followup_reused_assignment_id | reject |
| untyped_or_default_dispatch | reject |
| empty_purpose_slug | reject |
| authorized_model_or_effort_override | accept_and_show_override_in_display_label |
| nested_work_return | direct_parent_only |

| Profile | Effort | Model | Allowed depth | Child adjacency |
| --- | --- | --- | --- | --- |
| Spark scanner | xhigh | gpt-5.3-codex-spark | d1-d3 | scanner-only terminal |
| Spark worker | xhigh | gpt-5.3-codex-spark | d1-d2 | terminal; no d3 writer |
| Luna scanner | low | gpt-5.6-luna | d1-d3 | scanner-only terminal |
| Luna worker | medium | gpt-5.6-luna | d1-d2 | d1 -> Spark worker/scanner or Luna scanner; d2 -> Spark/Luna scanners only |
| Luna orchestrator | max | gpt-5.6-luna | d1 | d1 -> Luna worker/scanner or Spark worker/scanner at d2 |
| Sol worker | high | gpt-5.6-sol | d1 | root-routed d1 terminal only |
| Sol advisor | high | gpt-5.6-sol | d1 | root-routed d1 terminal only |
| Sol reviewer | max | gpt-5.6-sol | d1 | root-routed d1 terminal on-demand review only |

### Exact adjacency rows

| Parent | Parent depth | Allowed children | Child depth |
| --- | --- | --- | --- |
| luna orchestrator | d1 | luna worker, luna scanner, spark worker, spark scanner | d2 |
| luna worker | d1 | spark worker, spark scanner, luna scanner | d2 |
| luna worker | d2 | spark scanner, luna scanner | d3 |
| all scanners | d1-d3 | terminal | -- |
| spark worker | d1-d2 | terminal | -- |
| d3 | scanner-only | terminal | -- |

Depth 1, depth 2, and depth 3 child rules are explicit in the matrix. No writer is allowed at d3. There is no recursive orchestrator, no Sol role
below root, and no implicit adjacency beyond this table. Spark is the bounded
fast lane; Luna scanner handles broad/context-heavy scans; Luna worker handles
normal implementation; Luna orchestrator is reserved for genuinely multi-area
coordination; Sol lanes are rare root-routed escalation/review paths.

## Compact contracts, ownership, and recovery

Use these compact instruction envelopes; they are templates, not a scheduler or
persistent service:

`WORK_ASSIGNMENT_V1` carries the assignment ID and assignment fields.
`WORK_RETURN_V1` carries the matching assignment ID, status, changed paths,
changed resources, checks, background activity, and remaining risks.
`ADVISOR_REQUEST_V1` carries the requester ID, decision, risk, options, frozen evidence digest, ownership status, child status, and requested response.

```text
WORK_ASSIGNMENT_V1
assignment_id: <root-session identity plus unique assignment identity>
task_name: <d<depth>_<profile>_<purpose_slug>>
display_label: <D<depth> · <family>/<effort> · <role> · <purpose>>
owner: <direct parent>
direct_return_target: <direct parent task path>
owned_paths: <exclusive paths>
owned_resources: <exclusive shared resources or none>
permitted_actions: <bounded actions>
expected_outcome: <observable result>
checks: <focused verification>
```

```text
WORK_RETURN_V1
assignment_id: <matching assignment ID>
task_name: <d<depth>_<profile>_<purpose_slug>>
display_label: <D<depth> · <family>/<effort> · <role> · <purpose>>
status: <complete, blocked, or failed>
changed_paths: <paths or none>
changed_resources: <resources or none>
checks: <commands and results>
background_activity: <processes, ports, jobs, or none>
remaining_risks: <risks or none>
```

```text
ROSTER_DELTA_V1
canonical_task_path: </root/...>
task_name: <d<depth>_<profile>_<purpose_slug>>
display_label: <D<depth> · <family>/<effort> · <role> · <purpose>>
status: <active|completed|failed|terminated>
```

ROSTER_DELTA_V1 is metadata-only. It is a separate envelope sent directly to
the root by nested Luna parents as an active delta after a successful spawn and
as a terminal delta after reconciliation. It carries no work results or
ownership and is not carried by WORK_RETURN_V1. WORK_RETURN_V1 work and
evidence remain direct-parent only. The root publishes a compact roster on
start and material delegation changes. Generated Codex aliases remain
secondary.

```text
ADVISOR_REQUEST_V1
requester_id: <orchestrator task path>
decision: <decision under review>
risk: <consequential risk>
options: <bounded alternatives>
frozen_evidence_digest: <digest and evidence anchors>
ownership_status: <leased scopes and reconciliation state>
child_status: <idle, completed, or unresolved children>
requested_response: <specific adversarial question and response contract>
```

Every writer has a direct-parent-owned, non-overlapping scope. Serialize
conflicts; same warm worker revisions may continue only under a fresh matching
assignment. The root owns Git, external actions, and repository-wide
generators. An orchestrator makes no edits in active child scope and integrates
only after writers are idle and returns reconciled. A Sol advisor is a sibling
handoff: drain and yield, validate at root, then same-agent resume in the same
orchestrator or use an explicit rehydration fallback packet.

Crash/session recovery is fail-closed: reject old-session returns; block
overlapping writers until the workspace/shared-resource/task-owned-background-process audit is
completed and reconciled; leave unclear state unassigned and
escalate it. Do not create a persistent lease or state machine. Active tool use,
running work with evidence, or concrete progress stays alive indefinitely;
elapsed time never kills healthy work; query quiet agents; interrupt only idle, unresponsive, or demonstrably stuck work; and reconcile before reclaim.

Spark dispatches use `fork_turns = "none"` and a fresh self-contained bounded
packet with exact anchors. The smaller Spark context is for tiny localized
checks only; its catalog is about 128k tokens versus about 272k for Luna/Sol.
Luna carries broad discovery and normal implementation context.

# Delegation Topology And Cost Ceilings

Treat the Sol Medium root as depth 0 and count task-path segments after
`/root`. If depth is unavailable or ambiguous, fail closed and do not spawn.

## Model And Effort Matrix

| Profile | Effort | Allowed depth | Purpose |
| --- | --- | --- | --- |
| Spark scanner | high | 1-3 | Exact low-context evidence under every fast-path gate |
| Spark worker | xhigh | 1-3 | Small explicit edits with mechanical verification |
| Luna scanner | medium | 1-3 | Broader evidence, audits, comparisons, and test gaps |
| Luna worker | high | 1-3 | Default routine implementation and verification |
| Luna coordinator | high | 1-2 | Low-cost bounded orchestration and synthesis |
| Terra worker | medium | 1-2 | Ambiguous or cross-layer implementation |
| Terra coordinator | medium | 1-2 | Cross-workstream decisions and integration |
| Sol advisor | max | 1 | Independent consequential adversarial challenge |
| Sol worker | xhigh | 1 | Rare difficult implementation or diagnosis |
| Sol coordinator | max | 1 | Advanced supervision of a bounded non-Sol subtree |

Spark is a terminal fast path, not the default. Luna is the default delegated
model. Terra handles work that exceeds Luna because of ambiguity, context, or
cross-layer integration. Sol xhigh is reserved for rare difficult terminal
work; Sol max is reserved for supervision and adversarial sign-off. Profiles
use their configured efforts, and agents escalate the model rather than making
ad-hoc effort changes.

## Depth Rules

- Depth 1 may use Spark, Luna, Terra, or Sol.
- Depth 2 may use Spark, Luna, or Terra. Sol is prohibited below depth 1.
- Depth 3 may use only terminal Spark or Luna scanners and workers. Depth-3
  agents never coordinate or spawn.

Agents choose depth automatically; do not ask the user to manage routing. Use
an escalation bias rather than a quota: over time, expect roughly 60% of
delegated work to stop at depth 1, roughly 30% to reach depth 2, and no more
than about 10% to reach depth 3. Never add depth to imitate that distribution.
A depth-2 coordinator may use depth 3 whenever distinct terminal leaf work
materially improves the outcome within budget.

- A depth-1 coordinator may spawn at most three direct children inside its
  assigned subtree budget.
- A depth-2 coordinator may spawn at most two terminal Spark or Luna children.
- Default to no more than three concurrent subagents. Use up to six for complex
  work and the configured ceiling of eight only for exceptional work with
  enough independent packages.
- Never spawn merely to fill slots. Stop when evidence and implementation
  coverage are sufficient.

Prefer `fork_turns = "none"` with a self-contained packet containing scope,
success criteria, evidence, stop conditions, output format, exclusive
`owned_paths`, and subtree budget. Reuse and steer an existing agent while its
context remains useful.

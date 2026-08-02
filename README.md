# Codex Orchestration Kit

This repository contains a reusable, evidence-driven Codex configuration built
around six terminal custom profiles. The Sol Medium root owns routing,
integration, authorized external actions, and final decisions; bounded leaves
handle discovery, implementation, and independent challenge.

The kit is intentionally generic. It contains no credentials, local runtime
state, machine-specific paths, or project instructions.

## Included

- `config.toml`: the portable root and six-profile routing projection.
- `agents/`: two Spark, two Luna, and two Sol terminal profiles.
- `skills/delivery-orchestration/`: adaptive implementation routing, ownership,
  Git completion, and terminal gates.
- `skills/plan-review-ladder/`: independent plan validation with frozen packet
  identity, deadlines, timeout handling, telemetry, and proportional Sol review.
- `skills/instruction-learning-loop/`: durable corrections converted into the
  smallest verified instruction update.
- `hooks/plan_gap_goal_hook.py`: goal tracking when an approved plan moves into
  implementation.
- `hooks.json`: portable hook registration for plan-goal and instruction-learning
  behavior.

## Weighted Model And Effort Matrix

| Role | Model | Effort | Typical use |
| --- | --- | --- | --- |
| Root | GPT-5.6 Sol | Medium | Routing, integration, final decisions, external actions |
| Spark scanner | GPT-5.3 Codex Spark | XHigh | Tiny exact read-only checks |
| Spark worker | GPT-5.3 Codex Spark | XHigh | Small mechanical edits |
| Luna scanner | GPT-5.6 Luna | Medium | Broad and context-heavy discovery |
| Luna worker | GPT-5.6 Luna | Max | Default substantial implementation |
| Sol worker | GPT-5.6 Sol | XHigh | Rare genuinely difficult implementation |
| Sol advisor | GPT-5.6 Sol | Max | Rare consequential adversarial review |

This matrix is a routing policy, not a claim that one model is universally
best. Each configured profile must own a distinct routing region that cannot be
served just as well by an adjacent profile. The configured effort is fixed per
profile, and routing escalates the model instead of changing effort ad hoc.

## Routing Decision Method

The decision matrix has three optimization axes:

| Axis | Signals | Use |
| --- | --- | --- |
| Quality and reliability | Overall intelligence, coding and agentic benchmarks, accuracy, instruction following, and observed failure modes | Sets the minimum safe capability for the role |
| Time | Weighted decode time, output speed, TTFT, end-to-end latency, and delegation overhead | Distinguishes a fast leaf from a deliberative root or advisor |
| Cost | Average task cost, token mix, caching, and consumption-lane constraints | Breaks near-ties after quality and context requirements are met |

Context capacity, mutability, reversibility, and consequence are **hard gates**,
not numbers that can be averaged away. A fast model is ineligible if the task
will not fit safely in its context, and a cheap model is ineligible if a missed
edge case would have material impact.

Selection follows five steps:

1. **Apply hard gates.** Classify context size, read-only versus write work,
   mechanical verifiability, reversibility, ambiguity, and consequence.
2. **Pareto-screen candidates.** Remove options that offer no useful quality,
   time, or cost advantage for that task class.
3. **Apply role-specific weights.** The root values judgment and reliability;
   a scanner values context and throughput; a worker values coding reliability
   and verification; an advisor values counterexample quality over latency.
4. **Apply a consolidation penalty.** A profile is added only if it owns a
   distinct routing region. Small benchmark differences do not justify another
   decision boundary, prompt contract, or escalation path.
5. **Verify and escalate.** A leaf stops when its packet gates fail. The root
   reviews evidence and moves directly to the next configured capability tier.

| Role | Highest weights | Why |
| --- | --- | --- |
| Sol Medium root | Judgment, knowledge reliability, context, integration, then completion time | The root makes routing and final decisions but should not spend Max effort on routine turns |
| Spark XHigh leaf | Boundedness, instruction following, consumption lane, and startup latency | Tiny exact work benefits from a short packet; broad discovery does not |
| Luna Medium scanner | Context, latency, evidence coverage, and cost | Broad read-only work needs the 5.6 context, while bounded evidence contracts and root-owned synthesis make Medium the better weighted default |
| Luna Max worker | Coding reliability, agentic execution, context, and verification | Substantial writes benefit from Luna's highest capability while remaining the default economical tier |
| Sol XHigh worker | Difficult-path reliability and consequence | Used only when Luna is genuinely insufficient |
| Sol Max advisor | Counterexamples, risk detection, and sign-off confidence | Rare reviews can trade latency and cost for the strongest challenge |

The Luna Medium scanner collects anchored facts rather than owning architecture,
product decisions, or consequential interpretation. It reports conflicting
authority, uncertainty, and unexamined areas to the root, which keeps the
scanner's lower operational risk from hiding evidence-quality risk.

### Benchmark snapshot and evidence limits

The following values came from the [Artificial Analysis](https://artificialanalysis.ai/)
snapshot supplied during the design discussion on 2026-08-02. Weighted decode
minutes exclude TTFT and overhead; output speed is tokens per second. They are
a benchmark snapshot, not local production telemetry, and the supplied overall
Intelligence Index values were marked as provisional estimates.

| Candidate | Decode minutes | Output speed | Intelligence Index |
| --- | ---: | ---: | ---: |
| Spark XHigh | Not published | 121 | 44 |
| Luna Medium | 0.4 | 153 | 38 |
| Luna High | 0.9 | 157 | 46 |
| Luna XHigh | 1.3 | 164 | 49 |
| Luna Max | 1.9 | 178 | 51 |
| Terra Low | 0.4 | 99 | 40 |
| Terra Medium | 0.7 | 105 | 46 |
| Terra High | 1.3 | 110 | 49 |
| Terra XHigh | 1.8 | 113 | 52 |
| Terra Max | 2.7 | 134 | 55 |
| Sol Medium | 1.3 | 61 | 54 |
| Sol High | 2.1 | 59 | 56 |
| Sol XHigh | 2.9 | 64 | 58 |
| Sol Max | 4.1 | 68 | 59 |

The planning worksheet also supplied average cost-per-task estimates. Those
figures are reproduced in the comparison table below so the ratios remain
auditable. They are useful for directional comparisons but are not universal
pricing, and they are not assumed to be synchronized with every benchmark
revision.
Spark is treated as marginally free only for this deployment because it uses a
separate consumption lane; that is an operating assumption, not a general
model-price claim. TTFT, full end-to-end latency, cache behavior, and actual
task success still require local measurement.

### Why Sol Medium is the root

The root is a decision and integration role, not a bulk-output role. In the
snapshot, Sol Medium scores 54 overall, 57% on AA accuracy, 86% on
Terminal-Bench, and 76.3 on the Coding Index. Moving to Sol XHigh raises the
overall score from 54 to 58 but increases weighted decode time from 1.3 to 2.9
minutes. Sol Medium therefore supplies a stronger reliability floor than the
routine Luna tier without making every root turn an expensive escalation.

This is a role-weighted compromise, not a universal optimum. Luna Max has much
higher streaming throughput and, under the worksheet assumptions, lower
planning cost, while Sol XHigh has higher agentic and difficult-path scores. The
root routes bulk work to Luna and invokes Sol XHigh or Max only when their
distinct strengths matter.

## Why Terra Is Not Configured

The close Luna/Terra pairings are the main reason Terra does not get a custom
route. The cost ratios below come from the supplied planning worksheet; the
quality and throughput observations come from the later benchmark snapshot.

| Comparison | Worksheet cost inputs | Cost ratio | Observed tradeoff | Policy decision |
| --- | ---: | ---: | --- | --- |
| Luna Medium vs. Terra Medium | $0.0151 / $0.1598 | Terra 10.58x Luna | Terra is eight points higher overall; Luna is 0.3 minutes faster and has 1.46x output speed. | The bounded read-only scanner values context, latency, and cost; root-owned synthesis handles difficult interpretation, so Terra does not earn a separate route. |
| Luna High vs. Terra Medium | $0.0289 / $0.1598 | Terra 5.53x Luna | Overall score ties at 46. Terra has 0.2-minute lower decode time; Luna has 1.50x output speed. | If Medium scanning is insufficient, the Sol Medium root owns interpretation; neither tied intermediate option needs a permanent profile. |
| Luna XHigh vs. Terra High | $0.0431 / $0.3041 | Terra 7.06x Luna | Overall score and decode time tie at 49 and 1.3 minutes; Luna has 1.49x output speed. | No distinct Terra High region. Luna XHigh is itself consolidated away. |
| Luna Max vs. Terra XHigh | $0.0658 / $0.4300 | Terra 6.53x Luna | Terra is one point higher and 0.1 minute faster; Luna has 1.58x output speed. | Luna Max remains the default writer because the quality difference is small and the route is simpler. |
| Terra Max vs. Sol XHigh | $0.7328 / $1.1671 | Sol 1.59x Terra | Terra has 2.09x output speed and slightly lower decode time; Sol is three points higher overall and leads the supplied coding, agentic, accuracy, and difficult-task measures. | Sol XHigh owns rare high-risk implementation where reliability matters more than throughput. |

Terra Low is also omitted: the current policy already has Spark for tiny bounded
packets and Luna Medium for broad evidence. Terra Low ties Luna Medium's
0.4-minute decode time and is two points higher overall, but Luna has 1.55x
output speed and the supplied material does not establish a distinct cost or
task region for another leaf.

Terra Max deserves the strongest caveat. It is a plausible Pareto point when
raw throughput or planning cost matters more than difficult-path reliability.
It was not selected under this policy because rare escalations weight coding,
agentic execution, accuracy, and consequence more heavily, and because adding
another rare tier increases routing ambiguity. This is not a claim that Terra
Max is categorically inferior. It is the first Terra profile to reconsider if
local workloads demonstrate a stable, distinct routing region.

## Why The Other Model Efforts Are Not Configured

- **Spark Low, Medium, and High:** Spark has one deliberately narrow lane.
  XHigh is the only Spark effort in the supplied benchmark and scored 75% on
  instruction following. Because this deployment treats the lane as separate
  consumption, there is no evidence-based reason yet to trade quality for a
  lower effort. Lower efforts would add boundaries without a measured task
  shape of their own.
- **Luna Low:** the supplied benchmark and cost material did not cover it.
  Medium is already the balanced 5.6 scanner floor, so a lower unmeasured effort
  would add a boundary without evidence.
- **Luna High:** it has the same 5.6 context as Medium. High raises the supplied
  Intelligence Index from 38 to 46, but weighted decode time rises from 0.4 to
  0.9 minutes, output speed is nearly unchanged at 153 versus 157 tokens per
  second, and worksheet cost rises from $0.0151 to $0.0289. Difficult
  interpretation routes to the Sol Medium root or a risk-triggered advisor, so
  High does not own a separate scanner region.
- **Luna XHigh:** it sits between the Medium scanner and Max worker but owns no
  separate read/write or risk boundary. It is a reasonable future budget-worker
  candidate if Luna Max cost becomes material.
- **Sol Low:** it does not provide enough reliability margin for the root and,
  under the supplied worksheet assumptions, its cost/throughput tradeoff does
  not justify replacing the routine Luna tier merely for lower decode time.
- **Sol High:** it improves the overall score from Sol Medium's 54 to 56 while
  increasing weighted decode time from 1.3 to 2.1 minutes. It does not create a
  distinct role between the Medium root and XHigh difficult worker.
- **Sol Ultra:** the supplied benchmark and cost material did not cover it.
  Sol Max already defines the rare advisor ceiling, so an unmeasured higher tier
  is not configured by default.
- **Sol Max as a worker:** Max is reserved for short, consequential advisory
  passes. Its 4.1-minute weighted decode time is not justified for routine
  implementation.

## Context-Aware Routing

Spark is reserved for tiny bounded packets, but the supplied benchmark does not
include Spark end-to-end latency. Its speed advantage is therefore a routing
hypothesis to validate with local TTFT and completion telemetry, not a proven
benchmark conclusion.

The current local catalog advertises 128,000 tokens with 121,600 effective for
Spark, versus 272,000 with 258,400 effective for the GPT-5.6 family. Every Spark
assignment therefore uses `fork_turns = "none"` and a fresh self-contained
packet with exact anchors, expected evidence, and explicit stop conditions.
Broad discovery, inherited conversation history, or context-heavy evidence
routes to Luna Medium instead; consequential synthesis remains root-owned.

Luna Max is the default writer. Sol XHigh is a rare implementation escalation;
Sol Max advice is risk-triggered for consequential architecture, compatibility,
migration, persistence, security, concurrency, data integrity, external impact,
or unresolved high-severity gaps.

## When To Revisit The Matrix

Re-run the selection process rather than preserving the matrix by habit when:

- local TTFT or end-to-end telemetry shows Spark is not the fastest reliable
  option for its bounded lane;
- context windows, effective service limits, prices, or consumption lanes
  change;
- Luna Max frequently escalates or Sol workers repeatedly handle routine work;
- Terra Low or Terra Max demonstrates a stable quality, latency, and cost region
  on the actual repository task mix;
- a previously unused effort level materially changes coding, agentic,
  instruction-following, or accuracy results;
- a profile is rarely selected, commonly corrected, or cannot be distinguished
  from an adjacent route by an observable gate.

Keep the smallest matrix that covers the real task distribution. Benchmark
agreement is evidence; successful local delivery and verification are the
decision record.

## Delegation Topology

- Depth 0 is the Sol Medium root.
- All six custom profiles are terminal depth-1 leaves and report directly to
  the root.
- Leaves never spawn. The configured depth is `1`.
- Normal work uses one to three concurrent leaves. The ceiling of four applies
  to spawned threads and does not count the root.
- Writers receive disjoint ownership. The root owns integration, Git/external
  actions, and the user response.

## Plan Review Routes

- **Standard:** root candidate, independent Luna Medium validation, root
  residual-risk pass. No mandatory Sol for routine low-risk plans.
- **Expanded:** Standard plus one early risk-triggered Sol Max challenge.
- **Full:** Expanded plus a fresh final Sol Max challenge after synthesis and
  verification design.

All reviewers receive a frozen request, evidence bundle, candidate, and
reviewer-specific lens. Review packets have identity hashes, deadlines, zero
descendant budget, timeout handling, and evidence-limited telemetry.

## Install

Use this repository as a source package, not as a blind replacement for an
existing Codex home:

1. Back up the current Codex configuration.
2. Copy the six files under `agents/` into the matching `CODEX_HOME/agents`
   directory and remove retired custom-profile files from earlier versions.
3. Copy the three directories under `skills/` into `CODEX_HOME/skills`.
4. Semantically merge the root model/effort, `[agents]`, `[agents.*]`,
   `[features]`, and `[[skills.config]]` entries from `config.toml`; preserve
   machine-local plugin, MCP, trust, notification, and runtime settings.
5. Merge `hooks.json` with existing registrations and copy
   `hooks/plan_gap_goal_hook.py`. The commands honor `CODEX_HOME` and otherwise
   resolve `~/.codex`.
6. Restart Codex and begin a new task so the root model, profiles, skills, and
   hooks reload. Review and approve user-level hooks through `/hooks`; do not
   bypass trust controls.

Model availability, context limits, and supported efforts can vary by account
and release. Verify the local model catalog before enabling profiles.

## Validate

From the repository root in PowerShell:

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
python -B -m unittest discover -s .\tests -v
```

After installation, run the four installed skill-script suites against
`CODEX_HOME`, confirm the parsed TOML projection, and start a new task for the
effective runtime smoke check. Repository unit tests remain source-checkout
validation and are not copied into `CODEX_HOME`.

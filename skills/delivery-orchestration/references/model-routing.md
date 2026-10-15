# Combined Model Routing

Use this policy for every root provider. Preserve the user's selected thread model.
Opus medium is the normal root preference. Codex and Muse roots use the same worker selection rules.
Never select Max effort. The highest allowed effort is xhigh; do not bypass the cap with higher modes or aliases.

## Select Each Assignment

1. Define the task, required judgment, tools, verification, and capability floor.
2. Read the current provider catalog before a dispatch batch.
3. Exclude disabled, missing, quota-blocked, or unsupported targets and all forbidden efforts.
4. Read available usage reports and reset times. Prefer the capable provider with the most verified usable headroom.
5. When headroom is comparable or unknown, give a slight preference to another provider, then another model.
6. Within those choices, select the least costly capable model and effort from the task-specific evidence and supplied priors.
7. Refresh usage after substantial work or a limit event. Refresh the catalog after provider, model, or option changes.

Capability is mandatory. A subscription balance cannot justify a weaker assignment than the task needs.
The alternate-provider preference is slight; task fit and materially greater headroom override that preference.
Do not force rotation, create extra work, or add reviews solely to consume every subscription.
Use disjoint useful slices across funded providers when capacity and task fit support parallel work.
Preserve a usable reserve for the root and requested advice when the usage report supports that decision.

## Usage Evidence

- Use current runtime usage windows or a current user report. Record the source, observation time, and reset times in dispatch reasoning.
- Compare the tightest relevant session, weekly, or model-specific window. Account for active children that share the same allowance.
- Prefer normalized remaining percentages when the windows are comparable. Do not compare raw token counts across plans as available capacity.
- If reports are absent, stale, or incompatible, mark headroom unknown. Unknown does not mean empty or unlimited.
- Catalog availability and transcript spend do not establish remaining quota.
- T3 has usage-window data internally, but the current MCP catalog exposes no usage-balance tool.
- Run the skill's `scripts/provider_usage.py` before a dispatch batch. Read the report rather than treating exit status as verified headroom.
- The reader uses Codex's app-server read API and Claude's usage endpoint. Credentials stay in process memory and never enter reports.
- The reader also checks Muse's native `usage/read` snapshot. A new isolated host can have no observation despite available terminal quota data.
- If Muse's native snapshot is absent or stale, run `/usage` in the Muse terminal. Read the subscription Current and Weekly windows.
- Use the tightest remaining subscription percentage and check the displayed reset times and observation time. Session token counts do not establish headroom.
- Do not submit `/usage` as a model prompt. Use the terminal slash command; if the terminal report is inaccessible, keep Muse headroom unknown.
- Muse probes disable launcher updates and login. CLI probes close input before they stop the owned launcher.
- An `unrecognized` model scope keeps the limit visible without exposing the raw label. Confirm that scope before claiming candidate headroom.
- A model-only Codex main snapshot cannot establish shared provider headroom. Keep the provider headroom unknown.
- The reader does not query macOS Keychain. A Keychain-only Claude login returns unknown; use the runtime usage display.
- The report covers the local CLI accounts. Do not apply those balances to a different account or provider instance.
- Match report `claude` to the corresponding `claudeAgent` catalog instance. Confirm that the login context matches before selecting a target.
- Use shared windows for provider headroom. Check applicable model-scoped windows before choosing the model; other model limits do not block that choice.
- A failed usage read does not prove that the model provider is unavailable. Keep failed or stale headroom unknown.
- Read an accessible runtime usage display or current user report when the reader has no trustworthy observation.
- After a confirmed limit, authentication, or availability failure, exclude the affected target and reroute a fresh bounded packet.
- Preserve the capability floor after a reroute. Report a capability gap when no eligible target can meet the task.

Read usage with the installed skill:

```bash
python3 -B ~/.codex/skills/delivery-orchestration/scripts/provider_usage.py
```

For Claude-only installations, use the matching path under `~/.claude/skills`.
On Windows, use `python -B` with the installed script path.
Windows command resolution has fixture coverage. Windows runtime behavior still needs a live check.
Keep the command output outside Git. The output contains current account consumption, rather than reusable policy.

## Worker Map

These are starting choices inside the selected provider, rather than a fixed provider priority.
Effort names are task-level priors. Validate the actual task and preserve required evidence.

| Task | Claude choice | Codex choice | Selection note |
| --- | --- | --- | --- |
| Tiny exact lookup | Haiku low | Luna medium | Approximate effort offset |
| Bounded discovery or classification | Haiku medium | Luna high | Increase effort for broader evidence |
| Decided mechanical edit | Haiku high | Luna xhigh | Explicit paths and a deterministic check |
| Bounded routine implementation | Haiku xhigh | Sol low | Luna Max is forbidden; Sol low preserves the stronger tier |
| Terminal coding or workflow automation | Sonnet high | Sol medium or high | Prefer task-specific coding and automation evidence |
| Bounded work with stronger judgment | Sonnet high or Opus low | Sol medium | Select by actual ambiguity and verification needs |
| Substantial implementation | Sonnet high or Opus medium | Sol high | Partition useful independent work |
| Difficult diagnosis or architecture | Opus high, then xhigh | Sol high, then xhigh | Escalate directly when the task needs stronger judgment |

Haiku is the primary cheap worker when Claude is selected.
Sonnet remains a main coding and automation worker, rather than a rarely used fallback.
Luna serves lower bounded tiers when Codex has available usage. Sol handles the stronger tiers without Max effort.
For a Codex root, slightly prefer Haiku or Sonnet when headroom is comparable or unknown.
For an Opus root, slightly prefer suitable Luna or Sol workers when headroom is comparable or unknown.
For a Muse Wonder Full root, choose Claude or Codex by verified headroom, then task fit and cost.

The user's effort-offset guide is Haiku low ≈ Luna medium, Haiku medium ≈ Luna high, and Haiku high ≈ Luna xhigh.
Haiku xhigh ≈ Luna Max remains a historical comparison only. Use Sol low instead of any Max route.
These approximate matches do not establish equal performance on every task.

## Advisor And Independent Review

Use Claude Opus high for Sol/Codex and all other non-Opus roots. Reserve Fable high for Opus roots. Explicit user model requests take precedence within the capability, independence, effort, and Astra fallback rules. This advisor rule overrides worker cost and load-balance preferences.
Use Astra high only when the applicable Claude advisor is unavailable, exhausted, or excluded from independent review, and Astra is dispatchable.
An observed provider failure or a current user report can establish the fallback condition. Do not predict a limit from spend alone.
Check availability for the applicable advisor model. If the catalog lacks that model while Claude works, report the missing advisor. Do not use Astra to hide a catalog or route configuration error.
Without a supported Claude dispatch path, Claude is unavailable to the current runtime; use Astra when dispatchable.

In T3, dispatch the applicable Claude advisor through the live provider with `effort: high`.
Outside T3, use a native profile only when the profile binds the applicable advisor model at high effort.
A native Advisor server has separate effort behavior. Use that server only when the model binding and allowed effort are known.
Codex's `astra_advisor` profile remains the fallback when the applicable Claude advisor is unavailable, exhausted, or excluded from independent review. A Codex profile cannot bind a Claude model.

Root review is sufficient for ordinary delivery. Independent review uses a model different from the root and every writer.
Advice from the applicable advisor fails independence when that model also served as the root or a writer.
For review, treat an advisor excluded by the root or writer model as unavailable. Choose another capable reviewer, including Astra high when required. Reserve Fable for Opus roots unless the user explicitly requests Fable.
Preserve the restriction on Astra and never select Max effort.
Do not claim that a fresh reviewer has never influenced the writers when those writers consulted the same Advisor.

## Subscription Priors

Source: the user's `priors-score-vs-subscription-cost-per-task.csv`, exported from [Priors Builder](https://mypriors.com/builder), supplied 2026-10-14.
The 148-row export has an unquoted comma in the cost header. Join the two cost-header cells before dictionary parsing.
The cost values are dollar amounts; the chart uses a logarithmic axis.
Builder describes the costs as subscription-priced estimates under plan assumptions and full allowance use.
Claude rows assume Claude Max 20x. The Codex rows below assume ChatGPT Plus.
These are workload priors, rather than measured remaining balances, verified billing rates, or task-quality guarantees.
Reassess costs when the actual plan, workload mix, or allowance changes. Do not replace this export with a different default Builder index.

| Model | Effort | Supplied score | Subscription cost/task |
| --- | --- | ---: | ---: |
| Haiku 5.5 | low | 27.77 | $0.0005 |
| Haiku 5.5 | medium | 33.51 | $0.0010 |
| Haiku 5.5 | high | 36.39 | $0.0017 |
| Haiku 5.5 | xhigh | 39.87 | $0.0026 |
| Sonnet 5.5 | low | 35.34 | $0.0052 |
| Sonnet 5.5 | medium | 40.05 | $0.0073 |
| Sonnet 5.5 | high | 45.63 | $0.0134 |
| Sonnet 5.5 | xhigh | 49.42 | $0.0305 |
| Opus 5.5 | low | 42.92 | $0.0083 |
| Opus 5.5 | medium | 49.99 | $0.0202 |
| Opus 5.5 | high | 52.00 | $0.0276 |
| Opus 5.5 | xhigh | 53.65 | $0.0524 |
| GPT-6 Luna | low | 18.87 | $0.0007 |
| GPT-6 Luna | medium | 27.79 | $0.0026 |
| GPT-6 Luna | high | 31.37 | $0.0043 |
| GPT-6 Luna | xhigh | 32.88 | $0.0062 |
| GPT-6.1 Sol | low | 41.42 | $0.0153 |
| GPT-6.1 Sol | medium | 46.71 | $0.0249 |
| GPT-6.1 Sol | high | 49.21 | $0.0372 |
| GPT-6.1 Sol | xhigh | 50.10 | $0.0458 |
| Fable 5.1 | high | 49.83 | $0.6099 |
| GPT-6 Astra | high | 50.28 | $0.1476 |

Fable remains preferred for Opus roots by user choice and model diversity, despite the higher supplied cost.
Haiku xhigh costs 58% less than Luna xhigh and has a higher supplied score.
The Max rows remain in the original export but are ineligible for every dispatch.

## Task-Specific Evidence

The user identified Sonnet 5.5 as strongest on Terminal-Bench v4-AA: three repeats and average pass@1.
Builder distinguishes that benchmark from the upstream Terminal-Bench leaderboard and v2.1.
The user also identified Sonnet's strength on AutomationBench-AA, which scores workflow automation with partial credit.
Use those task-specific signals for Sonnet's coding and automation role. Do not infer the same ranking at every effort.
The attached Intelligence Index API-cost chart is a separate cost measure, and the pictured Max efforts remain forbidden.
Preserve protocol, harness, effort, and provenance when comparing benchmark results.

## Catalog And Native Profiles

Resolve exact provider IDs, model IDs, and supported efforts from the current catalog.
Use `effort` for Claude targets and `reasoningEffort` for Codex targets. Never copy one provider's option key to another provider.
The current catalog includes Claude, Codex, and Muse. Astra is absent, so the Astra fallback is currently unverified in T3.
Muse and other providers remain eligible when dispatch is supported and task fitness, allowed effort, and capacity are established.
Do not map `Muse Wonder (Max)` to Muse Wonder Full without evidence of the same model and effort.
Do not request Max from Muse Spark or any other provider. Missing cost or usage data stays unknown.

In T3, read `delegationPolicy.mode` from `orchestrator_capabilities` before selecting the child launch path.
In `t3-managed` mode, use `delegate_task` for every child. Supply the task role and capability floor; T3 selects the target.
In `native-preferred` mode, use supported native same-provider profiles. Use T3 for other targets.
When the catalog has no delegation policy, use the combined map and the native-preferred path.
Outside T3, use supported native profiles. Standalone provider apps do not use the T3 setting.
Native profiles are fixed presets. Do not claim that a native dispatch can change effort when the tool cannot.
The native Haiku `mechanic` preset uses xhigh for bounded work; native Sonnet `worker` uses high for stronger judgment.
Codex native defaults remain Luna xhigh when cross-provider dispatch is unavailable. Native Sol profiles supply the stronger tiers.

---
name: adversarial-code-review
description: Use when the user requests independent critique or consequential uncertainty in an approach or delivery warrants an independent engineering review.
---

# Adversarial Review

Use Claude Opus high for Sol/Codex and all other non-Opus roots. Reserve Fable high for Opus roots. Explicit user model requests take precedence within the capability, independence, effort, and Astra fallback rules.
Use Astra high only when the applicable Claude advisor is unavailable, exhausted, or excluded from independent review, and Astra is dispatchable.
The reviewer model must differ from the root and every writer model.
For review, treat an advisor excluded by the root or writer model as unavailable. Choose another capable reviewer, including Astra high when required.
Reserve Fable for Opus roots unless the user explicitly requests Fable.
Never select Max effort. Follow [model routing](../delivery-orchestration/references/model-routing.md).
Review the integrated outcome or a specific unresolved decision. Ordinary
delivery needs Sol root review; separate review is not required for every
task, file, plan, or stage.

Use independent challenge when requested or warranted by consequential
security/privacy, destructive action, data integrity, production impact,
architecture/compatibility, conflicting evidence, or repeated failed verification.

Give the advisor the request, relevant source or diff, actual verification,
constraints, and unexamined areas. An approach review does not require
implementation evidence that cannot exist yet. Use fresh context when
independence requires it.

Return concrete findings ordered by severity, with source anchors and an
actionable correction or verification method. State what was examined and
what remains uncertain. Agreement between models is not proof.

The root accepts, rejects, or defers findings against evidence, fixes required
gaps, and reruns affected checks. Repeat review only when a material revision or
distinct unresolved risk needs another challenge. A required consequential
review failure blocks that delivery; optional review failure does not block
otherwise verified low-risk work.

No lifecycle receipts, immutable replay packets, or review ledgers are required.

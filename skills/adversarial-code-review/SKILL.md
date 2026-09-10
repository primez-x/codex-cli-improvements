---
name: adversarial-code-review
description: Use when the user requests independent critique or consequential uncertainty in an approach or delivery warrants an independent engineering review.
---

# Adversarial Review

The root dispatches the read-only `astra_advisor` at GPT-6 Astra high.
Review the integrated outcome or a specific unresolved decision. Ordinary
delivery needs Astra root review; separate review is not required for every
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

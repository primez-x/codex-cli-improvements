## Managed adversarial delivery gate

The six configured general-purpose profiles handle normal routing. For every
material delivery, after fresh applicable verification, the managed gate is
mandatory: classify the delivery, freeze its immutable review bundle, and
dispatch only the gate-only `sol_reviewer` Sol/max identity. The reviewer emits
only a strict `ReviewOutputV1`; the lifecycle gate creates the local
`ReviewReceiptV1`. Do not claim completion until that exact receipt and all
required finding dispositions are recorded. Record an explicit exemption reason
only for read-only, plan-only, or genuinely localized mechanically prescribed
work. This post-verification gate is distinct from the optional risk-triggered
`sol_advisor` challenge. Treat lifecycle hooks as guardrails, not universal
mutation coverage. An accepted finding always advances generation and requires
refreeze plus rereview. A blocked delivery may exit only as
`[adversarial-review-blocked] Incomplete: ...`; never present that path as
successful completion.

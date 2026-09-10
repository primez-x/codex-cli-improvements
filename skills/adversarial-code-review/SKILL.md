---
name: adversarial-code-review
description: Use when a consequential delivery, explicit review request, conflicting evidence, or high-risk implementation needs independent adversarial review before sign-off.
---

# Adversarial Code Review

Trigger: use when consequential delivery risk or an explicit request warrants
independent adversarial review before sign-off.

Use independent review for consequential delivery risk, not as a universal
completion gate. The root decides whether review is required and owns every
finding disposition.

Every integrated deliverable receives engineering approval from the Astra root
or an Astra high advisor. Root review satisfies ordinary delivery; independent
review below provides a separate challenge for consequential risk. Review the
whole outcome, interfaces, maintainability, and evidence rather than requiring
a separate reviewer for every task or line. One sufficient final review can
satisfy overlapping advisor and reviewer checkpoints.

## Review Triggers

Dispatch the read-only `astra_reviewer` at Astra/high when the user explicitly asks
for independent review or when any high-risk trigger applies:

- security, authentication, credentials, or privacy boundaries;
- destructive or irreversible actions;
- migrations, persistence, data integrity, or concurrency;
- production or material external impact;
- major architecture, compatibility, or public-contract changes;
- conflicting evidence, a stuck approach, or repeated failed verification.

File count alone is not a trigger. Do not dispatch for documentation or
`AGENTS.md` wording, formatting and renames, localized deterministic
configuration, small mechanically verified changes, or reversible
startup-setting changes unless one of the risks above is present.

## Review Workflow

1. Finish applicable author verification first.
2. Prepare one task-local, root-prepared evidence packet containing the request,
   acceptance criteria, final diff or bounded source snapshot, exact test or
   read-back evidence, known risks, and unverified areas.
3. Dispatch `astra_reviewer` with that packet. Require a verdict and findings
   ordered by severity, each with a claim, evidence anchors, correction, and
   verification method.
4. Disposition every actionable finding as accepted, rejected, or deferred
   against primary evidence. Fix accepted high-severity findings and rerun the
   affected verification.

Optional review infrastructure failure does not invalidate fresh mechanical
verification or block a low-risk delivery. Report the limitation if review was
attempted. Only a required high-risk review failure blocks delivery.

Use the legacy immutable lifecycle and
[replay workflow](references/evaluation-replay-workflow.md) only for an explicit
auditable replay or reviewer-quality evaluation, never for routine delivery.

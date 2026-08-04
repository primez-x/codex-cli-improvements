## Risk-triggered independent review

The six-profile limit applies only to general-purpose routing; the additional
on-demand `sol_reviewer` is a separate review identity.

Independent review is root-routed, not universally hook-enforced. Dispatch the
read-only `sol_reviewer` at Sol/max only when the user explicitly requests it or
when security, authentication, credentials, or privacy; destructive or
irreversible actions; migrations, persistence, data integrity, or concurrency;
production or external impact; major architecture, compatibility, or
public-contract changes; or conflicting evidence, a stuck approach, or repeated
failed verification makes independent review consequential.

Use focused root verification for documentation or `AGENTS.md` wording,
formatting and renames, localized deterministic configuration, small mechanical
changes, and reversible startup-setting changes unless a high-risk trigger
applies. If optional review infrastructure fails, report the limitation without
blocking a verified low-risk delivery. Only a required high-risk review failure
blocks delivery.

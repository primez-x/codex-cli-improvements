# Optional reusable integrations

Examples in this directory follow the same cross-device portability contract as the rest of the repository. Do not include consuming-project snapshots, business-specific skill exports, machine-local workspace defaults, tenant identifiers, or local verification reports. Keep those in their owning environment or project repository.

## Optional demo hook

`demo-goal-no-window.patch` illustrates a Windows background-process fix for an existing demo-production hook. The hook's producer/controller is a separate dependency and is not bundled here. The patch does not register or enable a hook. Review it against the consuming source and run `git apply --check` before applying; the portable plan-hook regression covers the equivalent Windows/POSIX launch contract in this repository.

Use relative paths, environment-derived locations, or explicit placeholders. A placeholder alone does not make a business-specific artifact suitable for this shared kit. Generic vendor compatibility guidance may name public tools without assuming a particular account, tenant, or machine.

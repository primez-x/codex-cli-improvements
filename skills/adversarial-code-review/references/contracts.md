# V1 contract reference

All records reject unknown fields and schema versions other than `1`. Canonical serialization and SHA-256 calculation use `plan-review-ladder/scripts/packet_integrity.py` exclusively.

The field-level authority for `ReviewOutputV1` and its finding schema is the
[`validate_review_output` implementation](../scripts/review_contracts.py).
It binds attempt, packet, bundle, snapshot, verdict, coverage, risks, and
complete stable findings. Lifecycle validation additionally requires one
evidence-bearing coverage disposition for every mandatory lens named by the
frozen contract. `DispositionLedgerV1` covers every finding; acceptance
advances generation, and only nonblocking findings may defer with
owner/follow-up. Every primary-counterevidence entry for a blocking rejection
must resolve to exact active-bundle or authority-matched pinned-Git bytes before
the ledger is persisted and again during final Stop, export, and evaluator
replay. Generic digest and opaque-version references cannot reject a blocking
finding.
`ReviewReceiptV1` binds session/task/delivery/generation, reviewer
identity/config, all evidence digests, and epoch. The lifecycle gate, never the
reviewer, creates a provisional receipt from the actual canonical output and a
canonical pending-disposition record, then replaces the disposition digest only
after a valid ledger is recorded.

## Strict pass example

```json
{
  "schema_version": 1,
  "attempt_id": "attempt-42",
  "packet_sha256": "1111111111111111111111111111111111111111111111111111111111111111",
  "bundle_sha256": "2222222222222222222222222222222222222222222222222222222222222222",
  "snapshot_sha256": "3333333333333333333333333333333333333333333333333333333333333333",
  "verdict": "pass",
  "coverage": [
    "artifact_identity: reviewed - base, HEAD, modes, and raw hashes matched",
    "lifecycle_cleanup: reviewed - creation and teardown paths inspected",
    "concurrency_ownership: not_applicable - no concurrent state in the bundle",
    "input_command_boundaries: reviewed - boundary validation inspected",
    "memory_resource_safety: reviewed - ownership paths inspected",
    "performance_hot_paths: not_applicable - no repeated or latency-sensitive path",
    "repository_contracts: reviewed - local instructions and patterns inspected",
    "indirect_consumers: reviewed - callers and generated consumers inspected",
    "overlap_attribution: not_applicable - no overlapping implementation found",
    "author_verification: reviewed - applicable tests and build evidence inspected"
  ],
  "residual_risks": [],
  "findings": []
}
```

## Strict finding example

Every finding has exactly these six fields. Its nonempty evidence list uses the
context-specific `FindingCodeEvidenceV1` union enforced identically by
`validate_review_output` and `validate_finding_evidence`; generic
`ExternalEvidence` is not a finding schema. Bundle evidence has exactly `kind`,
`uri`, `sha256`, and `selector`: it must name the active bundle digest, an exact
manifest path and raw-byte digest, plus a nonempty symbol or bounded line-range
selector that exists in that content. Pinned-Git evidence has exactly `kind`,
`repository`, `commit`, `path`, `sha256`, and `selector`: the repository is an
absolute credential-free Git authority with a repository path, the commit is a
full lowercase 40- or 64-character object ID, the path is safe and relative,
the SHA-256 binds the raw blob bytes, and the selector is nonempty and bounded.
Lifecycle resolution requires the repository URI to exactly match a configured
remote in the frozen snapshot's local repository, and the full commit and path
bytes must remain locally available; otherwise it fails closed. The authenticated
commit tree entry must be one exact object with mode `100644` or `100755` and
type `blob` before it is sized or read. Symlink (`120000`), gitlink (`160000`),
tree, missing, ambiguous, and other non-regular entries are rejected. Generic
digest and opaque-version references can support verification metadata. A
digest-free generic `git_commit` reference can likewise remain external
metadata, but none of those generic forms can appear as finding code evidence
or blocking-rejection counterevidence.

```json
{
  "id": "REVIEW-001",
  "severity": "high",
  "claim": "A caller-controlled value crosses a shell boundary without argument separation.",
  "evidence": [
    {
      "kind": "bundle",
      "uri": "bundle://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/src/run.py",
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "selector": {
        "kind": "symbol",
        "value": "run_command"
      }
    }
  ],
  "correction": "Pass a validated argument vector without invoking a command shell.",
  "verification": "Run hostile metacharacter cases and prove they remain one inert argument."
}
```

The equivalent exact pinned-Git evidence member is:

```json
{
  "kind": "git_commit",
  "repository": "https://example.com/acme/review-fixture.git",
  "commit": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "path": "src/run.py",
  "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "selector": {
    "kind": "line_range",
    "start": 40,
    "end": 52
  }
}
```

## Disposition input and lifecycle state control

`disposition` accepts exactly one ledger source: `--json '<DispositionLedgerV1
JSON>'`, `--stdin` with raw UTF-8 JSON bytes, or the mutually exclusive
compatibility form `--file PATH`. Every source is capped at 1,048,576 bytes and
rejects invalid UTF-8, malformed or non-object JSON, duplicate keys at any
depth, and non-finite constants before the exact `DispositionLedgerV1`
validator and immutable counterevidence resolver run. Inline, standard-input,
and file parsing complete before acquiring the session lock; contract
validation and persistence remain serialized under that lock. Accepted ledgers
advance generation and require refreeze. Rejected, deferred, and empty ledgers
regenerate the canonical receipt, and final Stop and replay export revalidate
the persisted result unchanged.

Hook mutation attribution recognizes only the exact resolved lifecycle script
invoked either directly or through the exact Python-script grammar. Actions
`classify`, `freeze`, `disposition`, `block`, `reconcile`, and `abort` are
non-delivery lifecycle state control; `status`, `export-replay`, and `health`
are read-only. Chained commands or redirected task writes take precedence and
remain delivery mutations. Malformed or dynamically constructed invocations
block before execution. If Post execution evidence is ambiguous, a frozen
delivery becomes stale without recording a successful mutation-epoch
increment.

Gate states are compare-and-swap monotonic within a frozen attempt: pending classification, armed, reviewing, receipted, completed. Stale blocks completion until a fresh attempt is frozen; blocked never becomes successful completion. Any mutation after bundle creation increments epoch; an A-B-A restoration is stale.

Lifecycle state uses digest-only active pointers and generation-specific records addressed by one canonical SHA-256 over the session, task, and delivery identities plus the generation filename. The composite address preserves the complete identity tuple without raw identifiers or a platform-sensitive directory per digest. Exact legacy V1 three-digest addresses remain readable: under the session lock the gate preserves the legacy record, writes the equivalent composite record, and atomically rewrites each matching active pointer. Historical replay accepts either exact derived address and verifies equal persisted bytes when a pointer has migrated. Installer rollback fails closed before changing files when composite state exists and the authenticated preimage gate cannot address it. Accepted findings persist the prior stale generation and activate a cleared next generation that can only proceed through freeze and review again.

The canonical review bundle contains `snapshot.json`, `review-contract.json`, `review-packet.json`, digest-bound `review-lenses.md`, and exact present base/HEAD/index/worktree bytes under `evidence/<source>/<owned-path>`. The contract and packet both bind the lens digest and mandatory lens IDs. `SubagentStart` injects the actual bundle directory and its exact frozen identities. At final `Stop`, the gate re-snapshots the declared paths from the immutable snapshot record and compares the current digest under a 30-second bound; the configured Stop hook allows 60 seconds so lock acquisition and fail-closed serialization do not consume the snapshot budget.

## VerificationEvidenceV1

`freeze` requires a strict verification manifest with exactly
`schema_version`, `platform`, `commands`, and `observations`. `schema_version`
is `1`. Platform records exactly `system`, `release`, `machine`, and `python`.
Every command records exactly:

- a stable `id`, the exact `command`, and repository-relative `cwd`;
- integer `exit_code` plus nonnegative `passed`, `failed`, `errors`, and
  `skipped` test counts; and
- `stdout` and `stderr` artifacts containing safe manifest-relative `path`,
  lowercase raw-byte `sha256`, and `size_bytes`.

Only successful commands (`exit_code == 0`, zero failed tests, zero errors)
can freeze. Artifact paths reject absolute paths, traversal, globs, symlinks,
escapes, mutation during read, and configured count/byte overages. The gate
copies verified raw bytes under `verification/artifacts/`, serializes the
normalized `verification-evidence.json`, and binds that record digest in both
the review contract and packet.

Each observation records exactly `id`, `subject`, `provenance`, `status`,
`detail`, and `artifact`. `handler_contract_smoke` is synthetic;
`subagent_provenance`, `mutation_observation`, `hook_trust`, and
`runtime_restart` are live. Passed or failed observations require raw evidence.
`unavailable` and `not_run` require a null artifact. At least one synthetic and
one live observation must be explicit, so a synthetic handler invocation can
never silently stand in for unavailable runtime provenance, trust approval,
mutation observation, or restart proof.

## ProductionManifestV1

The canonical `references/production-manifest.json` has exactly
`schema_version`, `copy_paths`, `semantic_inputs`, and `review_paths`.
`schema_version` is `1`; all paths are unique, safe repository-relative paths.
`review_paths` must equal the ordered union of copied paths and semantic source
inputs. The installer derives its copy payload from this file, while freeze
loads the same file when `--production-manifest` is supplied, snapshots every
review path, bundles the manifest bytes, and binds their raw digest in the
contract and packet. This makes unchanged installer inputs and indirect
configuration sources part of the exact reviewed delivery rather than an
out-of-band assumption.

A reviewer `blocked` verdict is accepted only with persisted risks or immutable finding evidence. It remains blocked and can exit only as a visibly qualified `[adversarial-review-blocked] Incomplete: ...` response containing no success/completion claim.

Evaluation results have two exact forms enforced by
[`load_results`](../scripts/evaluate_review_corpus.py). A
`curated_evaluator_self_test` validates only deterministic evaluator mechanics.
A `sol_reviewer_replay` case contains only its case identities and a
lifecycle-produced read-only export. The evaluator independently re-reads the
referenced canonical generation state, active pointer, exact profile, complete
bundle, output, pending or final disposition, and receipt. Standalone receipt
and output JSON cannot satisfy provenance. Only a fully revalidated replay can satisfy
`--claim-empirical-quality`; see the
[fresh replay workflow](evaluation-replay-workflow.md).

Category recall uses one-to-one semantic correspondence grounded in defects. Ground truth is
ID-free: every required category has one distinct immutable code selector and
separate grouped concepts for its claim, correction, and verification. One
finding can credit only that expectation when it cites the exact case artifact
and selector, states the concrete defect concepts, describes the expected remedy,
and exercises the expected failure path. Stable finding IDs do not affect
matching. Generic category prose, keyword collections, duplicated selectors,
and selectors absent from available immutable case bytes receive no recall or
quality credit.

Bundles use one unpublished staging directory followed by atomic temp-to-digest
publication, strict bundle-relative paths, raw-byte digest verification on every
read, and read-only file flags. Before the first sensitive byte is written, the
empty staging root receives and verifies its platform privacy boundary. Content,
the canonical manifest, the complete regular-file set, raw digests, and the
recursive final permissions are all verified while the digest path is still
absent. Only then does one atomic replace publish the verified tree. Identity,
hardening, verification, or publication failure removes only that unpublished
staging tree, leaves unrelated store entries untouched and no final digest path,
and permits a clean same-digest retry. Only the bundle-root `manifest.json` is
reserved and excluded from its own file-set check; nested files named
`manifest.json` remain ordinary digest-bound evidence. Snapshot construction
preflights the cumulative logical size of regular and sparse files and immutable
Git blobs before content reads, then hashes file and blob content through
bounded-memory spools/chunks under the one elapsed deadline. Regular-file
descriptor and path identity, size, and modification time must remain unchanged
across the read. URI authorities reject user information and credential or
signed query parameters before any validated record can be persisted. The
**Windows privacy boundary** resolves the invoking account by SID rather than a
username, removes inherited access on the empty staging root, and grants only
that SID read/execute plus explicit `SYSTEM`, `Administrators`, and owner-rights
recovery access. Children are created by inheriting that private root, then all
final root, directory, and file rules are converted to explicit rules and
recursively verified before publication. Ordinary unrelated accounts are
therefore excluded from evidence leaves, but the result is not a tamper-proof
ACL. The **POSIX read-only boundary** verifies staging-root mode `0700` before writing,
creates private `0700` directories and `0600` files, then enforces and verifies
final directory mode `0555` and file mode `0444`; the published result is
world-readable under mode bits, so confidentiality requires a private parent or
reviewer sandbox. On either platform, local administrators or root can change
permissions and bytes, as can the bundle owner; protection from those
principals is explicitly outside this local workflow boundary.

# Fresh Sol/max evaluation replay

`evaluation-self-test-results.json` is curated input for testing evaluator
mechanics. It has no reviewer provenance and cannot support an empirical claim
about reviewer quality.

Use this workflow to create a fresh `sol_reviewer_replay`. A replay is eligible
only when every case contains a read-only export produced by the lifecycle gate
and the evaluator can still read the referenced gate state and frozen bundle.

1. Materialize each pinned Git blob or local fixture at its authenticated byte
   digest in a clean task-owned repository. Use a retained lifecycle state root
   and freeze the case with `lifecycle_gate.py classify ... --classification
   material` followed by `lifecycle_gate.py freeze ...`.
2. Dispatch `sol_reviewer` through the normal depth-zero orchestration against
   only that frozen bundle. Require `gpt-5.6-sol`, max reasoning, and the exact
   profile used at freeze. Let `SubagentStart` and `SubagentStop` validate and
   persist the actual agent, profile, output, attempt, packet, snapshot, bundle,
   generation, and mutation epoch. The reviewer does not receive evaluator
   ground truth or expected wording; it derives each defect independently and
   cites one exact symbol or line-range selector in the immutable case artifact.
3. Before accepting a finding and mutating the fixture, export the receipted
   attempt. The export command is read-only and does not advance gate state:

   ```text
   lifecycle_gate.py --state-root <retained-state-root> --profile-path <sol_reviewer.toml> export-replay --session-id <session> --turn-id <turn>
   ```

   Capture stdout unchanged. A later final disposition is also valid when its
   ledger and receipt remain in the same generation. Do not hand-create or edit
   a receipt, output, digest, or export.
4. Create one result case with exactly `id`, canonical `input_sha256`, canonical
   `case_sha256` over `{id, kind, input}`, and the captured `lifecycle_export`.
   At the result root, record `results_kind: sol_reviewer_replay`, the corpus
   input-manifest digest, a replay ID, and reviewer `{agent_type, model,
   reasoning_effort, profile_sha256}`. All cases in one evaluator run must
   reference artifacts under the same retained state root.
5. Keep the generation state file, active pointer, complete `bundles/` content,
   and exact reviewer profile available and unchanged until evaluation finishes.
   Each frozen snapshot must contain the exact pinned case path and bytes. Run:

   ```text
   evaluate_review_corpus.py --corpus references/evaluation-corpus.json --results fresh-sol-replay.json --git-identities references/evaluation-git-identities.json --reviewer-profile ../../agents/sol_reviewer.toml --lifecycle-state-root <retained-state-root> --claim-empirical-quality
   ```

The evaluator independently re-reads and hashes the canonical generation state,
active pointer, profile, bundle manifest, every bundle file, snapshot, contract,
packet, lenses, output, pending or final disposition, and receipt. Standalone
self-consistent JSON, stale addresses, changed bytes, wrong reviewer provenance,
placeholder identities, and incomplete case coverage fail closed.

This is local integrity and accidental-staleness enforcement, not cryptographic
attestation. A local administrator can rewrite the evaluator, profile, state,
bundle, and export together; resistance to that administrator is outside this
workflow's threat boundary. A passing replay is empirical regression evidence,
not proof that every defect will be found.

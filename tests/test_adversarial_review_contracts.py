from __future__ import annotations

import csv
import os
import sys
import tempfile
import json
import subprocess
import time
import multiprocessing
import unittest
from contextlib import contextmanager
from unittest import mock
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1] / "skills" / "adversarial-code-review"
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import review_contracts  # noqa: E402
from review_contracts import (  # noqa: E402
    BundleStore,
    GateState,
    SnapshotLimits,
    build_bundle,
    build_git_snapshot,
    validate_external_evidence,
    validate_finding_evidence,
    validate_disposition_ledger,
    validate_review_output,
    validate_review_receipt,
)


SHA = "a" * 64


def _arm_gate(path: str, queue: multiprocessing.Queue) -> None:
    try:
        GateState(Path(path)).transition("armed", expected="pending_classification")
        queue.put("ok")
    except ValueError:
        queue.put("cas")


def _mutate_gate(path: str) -> None:
    GateState(Path(path)).mutation("B")


class AdversarialReviewContractsTests(unittest.TestCase):
    def test_canonical_json_and_sha256_fixed_vectors_remain_stable(self) -> None:
        payload = {"z": "x", "a": [1, True, None]}
        canonical = b'{"a":[1,true,null],"z":"x"}'

        self.assertEqual(review_contracts.canonical_bytes(payload), canonical)
        self.assertEqual(
            review_contracts.compute_packet_sha256(payload),
            "6e5aeb913fc68b439874dfbf513eac8b1d1d55e6b4baec9e9d173423eb0f608f",
        )
        self.assertEqual(
            review_contracts.compute_raw_sha256(b"raw\x00bytes"),
            "c560da256bb4c68782848cf894e228cc58649bbca864b48e451d66e8ce47fe00",
        )

    def test_strict_versioned_review_records_reject_unknown_fields_and_versions(self) -> None:
        output = {
            "schema_version": 1, "attempt_id": "attempt-1", "packet_sha256": SHA,
            "bundle_sha256": SHA, "snapshot_sha256": SHA, "verdict": "pass",
            "coverage": ["diff"], "residual_risks": [], "findings": [],
        }
        self.assertEqual(validate_review_output(output)["verdict"], "pass")
        with self.assertRaises(ValueError):
            validate_review_output({**output, "unknown": True})
        with self.assertRaises(ValueError):
            validate_review_output({**output, "schema_version": 2})

    def test_review_output_requires_stable_complete_findings(self) -> None:
        output = {
            "schema_version": 1, "attempt_id": "attempt-1", "packet_sha256": SHA,
            "bundle_sha256": SHA, "snapshot_sha256": SHA, "verdict": "fail",
            "coverage": ["diff"], "residual_risks": ["race"],
            "findings": [{"id": "F-1", "severity": "high", "claim": "unsafe",
                          "evidence": [{"kind": "bundle", "uri": "bundle://" + SHA + "/review", "sha256": SHA,
                                        "selector": {"kind": "line_range", "start": 1, "end": 1}}],
                          "correction": "lock", "verification": "test"}],
        }
        try:
            validated = validate_review_output(output)
        except ValueError as exc:
            self.fail(f"valid authority-qualified evidence was rejected: {exc}")
        self.assertEqual(validated["findings"][0]["id"], "F-1")
        with self.assertRaises(ValueError):
            validate_review_output({**output, "findings": [{"id": "F-1", "severity": "high"}]})

    def test_snapshot_rejects_unsafe_or_ambiguous_task_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "ok.txt").write_bytes(b"ok")
            for paths in ([], ["."], ["*.txt"], ["missing.txt"], [".env"], ["ok.txt", "ok.txt"]):
                with self.assertRaises(ValueError):
                    build_git_snapshot(root, paths, limits=SnapshotLimits())
            snapshot = build_git_snapshot(root, ["ok.txt"], limits=SnapshotLimits())
            self.assertEqual(snapshot["files"][0]["worktree"]["sha256"], __import__("hashlib").sha256(b"ok").hexdigest())

    def test_snapshot_enforces_configurable_limits_and_symlink_containment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "large.txt").write_bytes(b"abcd")
            with self.assertRaises(ValueError):
                build_git_snapshot(root, ["large.txt"], limits=SnapshotLimits(max_bytes=3))
            outside = root.parent / "outside-adversarial-review-test.txt"
            outside.write_text("outside", encoding="utf-8")
            junction = root / "escape-junction"
            try:
                created = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(junction), str(root.parent)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(created.returncode, 0, created.stderr)
                with self.assertRaises(ValueError):
                    build_git_snapshot(root, ["escape-junction/outside-adversarial-review-test.txt"], limits=SnapshotLimits())
            finally:
                if junction.exists():
                    subprocess.run(["cmd", "/c", "rmdir", str(junction)], check=False)
                outside.unlink(missing_ok=True)

    def test_bundle_is_content_addressed_immutable_and_reviewer_paths_are_not_workspace_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = BundleStore(Path(temporary) / "bundles")
            bundle = build_bundle(store, {"review.json": b'{"ok":true}'})
            self.assertTrue(bundle["bundle_path"].startswith("bundle://"))
            self.assertEqual(store.read(bundle["bundle_sha256"], "review.json"), b'{"ok":true}')
            with self.assertRaises(FileExistsError):
                build_bundle(store, {"review.json": b'{"ok":true}'})

    @unittest.skipUnless(os.name == "nt", "Windows ACL behavior")
    def test_windows_bundle_acl_excludes_unrelated_accounts_from_nested_evidence_leaf(self) -> None:
        real_temporary_directory = tempfile.TemporaryDirectory

        @contextmanager
        def inherited_staging_directory(*args, **kwargs):
            with real_temporary_directory(*args, **kwargs) as temporary:
                granted = subprocess.run(
                    ["icacls", temporary, "/grant:r", "*S-1-5-32-545:(OI)(CI)(RX)"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(granted.returncode, 0, granted.stderr)
                yield temporary

        with real_temporary_directory() as temporary:
            store = BundleStore(Path(temporary) / "bundles")
            with mock.patch.object(
                review_contracts.tempfile,
                "TemporaryDirectory",
                inherited_staging_directory,
            ):
                bundle = build_bundle(store, {"nested/evidence/review.json": b"private"})

            leaf = store.root / bundle["bundle_sha256"] / "nested" / "evidence" / "review.json"
            acl_path = Path(temporary) / "nested-evidence-leaf.acl"
            saved = subprocess.run(
                ["icacls", str(leaf), "/save", str(acl_path), "/c"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(saved.returncode, 0, saved.stderr)
            sddl = acl_path.read_text(encoding="utf-16-le")
            identity = subprocess.run(
                ["whoami", "/user", "/fo", "csv", "/nh"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(identity.returncode, 0, identity.stderr)
            current_user_sid = next(csv.reader([identity.stdout.strip()]))[1]

            self.assertNotIn(";;;BU)", sddl)
            self.assertIn(f"(A;;0x1200a9;;;{current_user_sid})", sddl)
            self.assertIn("(A;;FA;;;SY)", sddl)
            self.assertIn("(A;;FA;;;BA)", sddl)

    def test_dispositions_enforce_generation_counterevidence_and_deferral_rules(self) -> None:
        findings = [
            {"id": "F-1", "severity": "high"},
            {"id": "F-2", "severity": "low"},
        ]
        ledger = {"schema_version": 1, "generation": 2, "dispositions": [
            {"finding_id": "F-1", "decision": "accepted", "new_generation": 3},
            {"finding_id": "F-2", "decision": "deferred", "owner": "team", "follow_up": "issue-1"},
        ]}
        self.assertEqual(validate_disposition_ledger(ledger, findings, generation=2)["generation"], 2)
        rejected = {"schema_version": 1, "generation": 2, "dispositions": [
            {"finding_id": "F-1", "decision": "rejected"},
            {"finding_id": "F-2", "decision": "deferred", "owner": "team", "follow_up": "issue-1"},
        ]}
        with self.assertRaises(ValueError):
            validate_disposition_ledger(rejected, findings, generation=2)

    def test_receipts_bind_all_identities_and_gate_transitions_detect_aba_staleness(self) -> None:
        receipt = {"schema_version": 1, "session_id": "s", "task_id": "t", "delivery_id": "d", "generation": 1,
                   "reviewer_agent": "a", "reviewer_type": "scanner", "reviewer_model": "m", "config_sha256": SHA,
                   "attempt_id": "attempt", "packet_sha256": SHA, "bundle_sha256": SHA, "snapshot_sha256": SHA,
                   "output_sha256": SHA, "disposition_sha256": SHA, "mutation_epoch": 0}
        self.assertEqual(validate_review_receipt(receipt)["task_id"], "t")
        gate = GateState()
        gate.transition("armed", expected="pending_classification")
        gate.transition("reviewing", expected="armed")
        gate.bundle_created()
        gate.mutation("B")
        gate.mutation("A")
        self.assertEqual(gate.status, "stale")
        self.assertEqual(gate.epoch, 2)

    def test_nested_records_bool_values_and_external_evidence_are_strict(self) -> None:
        output = {"schema_version": 1, "attempt_id": "a", "packet_sha256": SHA, "bundle_sha256": SHA,
                  "snapshot_sha256": SHA, "verdict": "pass", "coverage": ["diff"], "residual_risks": [],
                  "findings": []}
        with self.assertRaises(ValueError):
            validate_review_output({**output, "coverage": [True]})
        with self.assertRaises(ValueError):
            validate_review_output({**output, "coverage": [{"source": "http://mutable"}]})

    def test_git_snapshot_records_exact_sources_modes_and_derived_states(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            (root / "tracked.txt").write_bytes(b"A")
            (root / "staged-deleted.txt").write_bytes(b"D")
            (root / "unstaged-deleted.txt").write_bytes(b"E")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=root, check=True, capture_output=True)
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            (root / "tracked.txt").write_bytes(b"B")
            subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
            (root / "tracked.txt").write_bytes(b"C")
            subprocess.run(["git", "rm", "staged-deleted.txt"], cwd=root, check=True, capture_output=True)
            (root / "unstaged-deleted.txt").unlink()
            (root / "untracked.txt").write_bytes(b"U")
            snapshot = build_git_snapshot(
                root,
                ["tracked.txt", "staged-deleted.txt", "unstaged-deleted.txt", "untracked.txt"],
                limits=SnapshotLimits(max_seconds=20.0),
                base=base,
            )
            self.assertEqual(snapshot["base"], base)
            files = {item["path"]: item for item in snapshot["files"]}
            self.assertEqual(
                files["tracked.txt"],
                {
                    "path": "tracked.txt",
                    "base": {"present": True, "sha256": "559aead08264d5795d3909718cdd05abd49572e84fe55590eef31a88a08fdffd", "mode": "100644"},
                    "head": {"present": True, "sha256": "559aead08264d5795d3909718cdd05abd49572e84fe55590eef31a88a08fdffd", "mode": "100644"},
                    "index": {"present": True, "sha256": "df7e70e5021544f4834bbee64a9e3789febc4be81470df629cad6ddb03320a5c", "mode": "100644"},
                    "worktree": {"present": True, "sha256": "6b23c0d5f35d1b11f9b683f0b0a617355deb11277d91ae091d399c655b87940d", "mode": "100644"},
                    "state": {"staged": "modified", "unstaged": "modified", "untracked": False, "deleted": False},
                },
            )
            self.assertEqual(
                files["staged-deleted.txt"],
                {
                    "path": "staged-deleted.txt",
                    "base": {"present": True, "sha256": "3f39d5c348e5b79d06e842c114e6cc571583bbf44e4b0ebfda1a01ec05745d43", "mode": "100644"},
                    "head": {"present": True, "sha256": "3f39d5c348e5b79d06e842c114e6cc571583bbf44e4b0ebfda1a01ec05745d43", "mode": "100644"},
                    "index": {"present": False, "sha256": None, "mode": None},
                    "worktree": {"present": False, "sha256": None, "mode": None},
                    "state": {"staged": "deleted", "unstaged": "none", "untracked": False, "deleted": True},
                },
            )
            self.assertEqual(
                files["unstaged-deleted.txt"],
                {
                    "path": "unstaged-deleted.txt",
                    "base": {"present": True, "sha256": "a9f51566bd6705f7ea6ad54bb9deb449f795582d6529a0e22207b8981233ec58", "mode": "100644"},
                    "head": {"present": True, "sha256": "a9f51566bd6705f7ea6ad54bb9deb449f795582d6529a0e22207b8981233ec58", "mode": "100644"},
                    "index": {"present": True, "sha256": "a9f51566bd6705f7ea6ad54bb9deb449f795582d6529a0e22207b8981233ec58", "mode": "100644"},
                    "worktree": {"present": False, "sha256": None, "mode": None},
                    "state": {"staged": "none", "unstaged": "deleted", "untracked": False, "deleted": True},
                },
            )
            self.assertEqual(
                files["untracked.txt"],
                {
                    "path": "untracked.txt",
                    "base": {"present": False, "sha256": None, "mode": None},
                    "head": {"present": False, "sha256": None, "mode": None},
                    "index": {"present": False, "sha256": None, "mode": None},
                    "worktree": {"present": True, "sha256": "a25513c7e0f6eaa80a3337ee18081b9e2ed09e00af8531c8f7bb2542764027e7", "mode": "100644"},
                    "state": {"staged": "none", "unstaged": "none", "untracked": True, "deleted": False},
                },
            )
            with self.assertRaises(ValueError):
                build_git_snapshot(root, ["tracked.txt"], limits=SnapshotLimits(max_seconds=20.0), base="not-a-commit")

    def test_bundle_validates_relative_names_atomic_writes_and_read_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = BundleStore(Path(temporary) / "bundles")
            with self.assertRaises(ValueError):
                build_bundle(store, {"../escape": b"bad"})
            bundle = build_bundle(store, {"nested/review.json": b"good"})
            path = store.root / bundle["bundle_sha256"] / "nested" / "review.json"
            path.chmod(0o666); path.write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                store.read(bundle["bundle_sha256"], "nested/review.json")

    def test_snapshot_uses_one_elapsed_deadline_for_git_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "ok.txt").write_bytes(b"ok")
            with self.assertRaises(ValueError):
                build_git_snapshot(root, ["ok.txt"], limits=SnapshotLimits(max_seconds=0.0))

            real_run = subprocess.run

            def controlled_slow_runner(command, **kwargs):
                if kwargs["timeout"] > 0.2:
                    return subprocess.CompletedProcess(command, 1, stdout=b"", stderr=b"")
                return real_run(
                    [sys.executable, "-c", "import time; time.sleep(1)"],
                    cwd=kwargs["cwd"],
                    capture_output=True,
                    check=False,
                    timeout=kwargs["timeout"],
                )

            started = time.monotonic()
            with mock.patch("review_contracts.subprocess.run", side_effect=controlled_slow_runner):
                with self.assertRaisesRegex(ValueError, "snapshot limit exceeded"):
                    build_git_snapshot(root, ["ok.txt"], limits=SnapshotLimits(max_seconds=0.05))
            self.assertLess(time.monotonic() - started, 0.5)

    def test_snapshot_uses_caller_absolute_deadline_for_subprocess_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "ok.txt").write_bytes(b"ok")
            observed_timeouts: list[float] = []

            def non_git_runner(command, **kwargs):
                observed_timeouts.append(kwargs["timeout"])
                return subprocess.CompletedProcess(command, 1, stdout=b"", stderr=b"")

            snapshot = build_git_snapshot(
                root,
                ["ok.txt"],
                limits=SnapshotLimits(max_seconds=1.0),
                absolute_deadline=1.0,
                clock=lambda: 0.6,
                runner=non_git_runner,
            )
            self.assertEqual(len(snapshot["files"]), 1)
            self.assertEqual(len(observed_timeouts), 1)
            self.assertAlmostEqual(observed_timeouts[0], 0.4, places=7)

    def test_gate_state_is_persisted_lock_safe_and_compare_and_swap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "gate.json"
            first = GateState(state_path)
            first.transition("armed", expected="pending_classification")
            second = GateState(state_path)
            self.assertEqual(second.status, "armed")
            with self.assertRaises(ValueError):
                second.transition("reviewing", expected="pending_classification")

    def test_skill_declares_executable_trigger_and_agent_interface(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        agent = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        reference = (SKILL_ROOT / "references" / "contracts.md").read_text(encoding="utf-8")
        self.assertIn("Trigger:", skill)
        self.assertIn("1.", skill)
        self.assertIn("interface:\n", agent)
        self.assertIn('display_name: "', agent)
        self.assertIn("Windows privacy boundary", reference)
        self.assertIn("POSIX read-only boundary", reference)
        self.assertIn("local administrators or root", reference)

    def test_external_evidence_and_dispositions_have_exact_mutually_exclusive_forms(self) -> None:
        evidence = [
            {"kind": "bundle", "uri": "bundle://" + SHA + "/review.json", "sha256": SHA},
            {"kind": "git_commit", "repository": "https://github.com/example/review.git", "commit": "b" * 40, "path": "src/review.py"},
            {"kind": "digest", "uri": "https://artifacts.example/reviews/42", "authority": {"kind": "artifact_registry", "source": "https://artifacts.example"}, "sha256": SHA},
            {"kind": "opaque_version", "uri": "https://releases.example/reviews/42", "authority": {"kind": "release_registry", "source": "https://releases.example"}, "version": "release-2026.08.01-001", "immutable": True},
        ]
        try:
            validated = validate_external_evidence(evidence)
        except ValueError as exc:
            self.fail(f"valid authority-qualified evidence was rejected: {exc}")
        self.assertEqual(validated, evidence)
        malformed = [
            {"uri": "https://mutable.example/review", "sha256": SHA},
            {"kind": "git_commit", "repository": "git://repo", "commit": "main", "path": "review.py"},
            {"kind": "digest", "uri": "https://artifacts.example/review", "authority": {"kind": "artifact_registry", "source": "relative"}, "sha256": SHA},
            {"kind": "opaque_version", "uri": "https://releases.example/review", "authority": {"kind": "release_registry", "source": "https://releases.example"}, "version": "latest", "immutable": True},
            {"kind": "opaque_version", "uri": "https://releases.example/review", "authority": [], "version": "release-1", "immutable": True},
            None,
        ]
        for item in malformed:
            with self.subTest(item=item):
                with self.assertRaises(ValueError):
                    validate_external_evidence([item])
        findings = [{"id": "F", "severity": "low"}]
        bad = {"schema_version": 1, "generation": 1, "dispositions": [{"finding_id": "F", "decision": "accepted", "new_generation": 2, "owner": "irrelevant"}]}
        with self.assertRaises(ValueError): validate_disposition_ledger(bad, findings, generation=1)

    def test_bundle_manifest_exactness_and_interprocess_gate_cas_idempotency(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = BundleStore(Path(temporary) / "bundles"); bundle = build_bundle(store, {"a": b"a", "b": b"b"})
            manifest_path = store.root / bundle["bundle_sha256"] / "manifest.json"
            manifest = json.loads(manifest_path.read_text()); manifest["extra"] = SHA; manifest_path.chmod(0o666); manifest_path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError): store.read(bundle["bundle_sha256"], "a")
            state_path = Path(temporary) / "state.json"; queue = multiprocessing.Queue()
            processes = [multiprocessing.Process(target=_arm_gate, args=(str(state_path), queue)) for _ in range(2)]
            [process.start() for process in processes]; [process.join() for process in processes]
            self.assertEqual(sorted(queue.get() for _ in processes), ["cas", "ok"])
            gate = GateState(state_path); revision = gate.revision; gate.transition("armed", expected="armed")
            self.assertEqual(gate.revision, revision)

    def test_mutations_are_interprocess_locked_and_persisted_state_is_strict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "state.json"; gate = GateState(state_path); gate.bundle_created("A")
            workers = [multiprocessing.Process(target=_mutate_gate, args=(str(state_path),)) for _ in range(3)]
            [worker.start() for worker in workers]; [worker.join() for worker in workers]
            self.assertEqual(GateState(state_path).epoch, 3)
            state_path.write_text('{"status":"armed","epoch":true,"revision":0,"fingerprint":null}', encoding="utf-8")
            with self.assertRaises(ValueError): GateState(state_path)

    def test_finding_evidence_is_bound_to_active_bundle_manifest_and_exact_selector(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = BundleStore(Path(temporary) / "bundles")
            source = b"def run_command(value):\n    return value\n"
            bundle = build_bundle(store, {"evidence/worktree/src/run.py": source})
            digest = bundle["bundle_sha256"]
            source_sha = __import__("hashlib").sha256(source).hexdigest()
            base = {
                "kind": "bundle",
                "uri": f"bundle://{digest}/evidence/worktree/src/run.py",
                "sha256": source_sha,
                "selector": {"kind": "symbol", "value": "run_command"},
            }
            findings = [{"id": "F-1", "evidence": [base]}]
            self.assertEqual(
                validate_finding_evidence(
                    findings,
                    store=store,
                    active_bundle_sha256=digest,
                ),
                findings,
            )

            invalid = [
                {key: value for key, value in base.items() if key != "selector"},
                {**base, "uri": f"bundle://{'b' * 64}/evidence/worktree/src/run.py"},
                {**base, "uri": f"bundle://{digest}/evidence/worktree/src/missing.py"},
                {**base, "sha256": "b" * 64},
                {**base, "selector": {"kind": "symbol", "value": "missing_symbol"}},
                {**base, "selector": {"kind": "symbol", "value": "run"}},
                {**base, "selector": {"kind": "line_range", "start": 1, "end": 201}},
                {**base, "selector": {"kind": "line_range", "start": 2, "end": 4}},
            ]
            for evidence in invalid:
                with self.subTest(evidence=evidence):
                    with self.assertRaises(ValueError):
                        validate_finding_evidence(
                            [{"id": "F-1", "evidence": [evidence]}],
                            store=store,
                            active_bundle_sha256=digest,
                        )

            line_evidence = {
                **base,
                "selector": {"kind": "line_range", "start": 1, "end": 2},
            }
            validate_finding_evidence(
                [{"id": "F-1", "evidence": [line_evidence]}],
                store=store,
                active_bundle_sha256=digest,
            )

    def test_pinned_git_finding_evidence_requires_resolved_bytes_digest_and_selector(self) -> None:
        content = b"class ReviewGate:\n    pass\n"
        content_sha = __import__("hashlib").sha256(content).hexdigest()
        evidence = {
            "kind": "git_commit",
            "repository": "https://github.com/example/review.git",
            "commit": "b" * 40,
            "path": "src/review.py",
            "sha256": content_sha,
            "selector": {"kind": "symbol", "value": "ReviewGate"},
        }
        calls = []

        def resolve(repository: str, commit: str, path: str) -> bytes:
            calls.append((repository, commit, path))
            return content

        with tempfile.TemporaryDirectory() as temporary:
            store = BundleStore(Path(temporary) / "bundles")
            active = build_bundle(store, {"review.json": b"{}"})["bundle_sha256"]
            findings = [{"id": "F-1", "evidence": [evidence]}]
            self.assertEqual(
                validate_finding_evidence(
                    findings,
                    store=store,
                    active_bundle_sha256=active,
                    git_resolver=resolve,
                ),
                findings,
            )
            self.assertEqual(
                calls,
                [(evidence["repository"], evidence["commit"], evidence["path"])],
            )
            with self.assertRaises(ValueError):
                validate_finding_evidence(
                    findings,
                    store=store,
                    active_bundle_sha256=active,
                )
            with self.assertRaises(ValueError):
                validate_finding_evidence(
                    [{"id": "F-1", "evidence": [{**evidence, "sha256": "c" * 64}]}],
                    store=store,
                    active_bundle_sha256=active,
                    git_resolver=resolve,
                )

    def test_nested_manifest_named_content_is_not_confused_with_root_bundle_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = BundleStore(Path(temporary) / "bundles")
            bundle = build_bundle(
                store,
                {
                    "nested/manifest.json": b'{"nested":true}',
                    "review.json": b"{}",
                },
            )
            self.assertEqual(
                store.read(bundle["bundle_sha256"], "nested/manifest.json"),
                b'{"nested":true}',
            )
            self.assertEqual(store.read(bundle["bundle_sha256"], "review.json"), b"{}")
            with self.assertRaisesRegex(ValueError, "reserved"):
                build_bundle(store, {"manifest.json": b"user-controlled"})

    def test_snapshot_preflights_sparse_regular_and_git_blob_sizes_before_content_reads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sparse = root / "sparse.bin"
            with sparse.open("wb") as handle:
                handle.seek(1024 * 1024)
                handle.write(b"x")
            with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("content was read")):
                with self.assertRaisesRegex(ValueError, "snapshot limit exceeded"):
                    build_git_snapshot(
                        root,
                        ["sparse.bin"],
                        limits=SnapshotLimits(max_bytes=1024),
                    )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            (root / "large.bin").write_bytes(b"x" * 4096)
            subprocess.run(["git", "add", "large.bin"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=root, check=True, capture_output=True)
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            real_run = subprocess.run
            commands = []

            def recording_runner(command, **kwargs):
                commands.append(command)
                return real_run(command, **kwargs)

            with self.assertRaisesRegex(ValueError, "snapshot limit exceeded"):
                build_git_snapshot(
                    root,
                    ["large.bin"],
                    limits=SnapshotLimits(max_bytes=1024, max_seconds=20.0),
                    base=base,
                    runner=recording_runner,
                )
            self.assertTrue(any(command[1:3] == ["cat-file", "-s"] for command in commands))
            self.assertFalse(any(command[1:3] == ["cat-file", "blob"] for command in commands))

    def test_streamed_regular_file_snapshot_rejects_growth_or_identity_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "changing.txt"
            target.write_bytes(b"stable")
            real_fstat = os.fstat
            calls = 0

            def changing_fstat(fd):
                nonlocal calls
                result = real_fstat(fd)
                calls += 1
                if calls >= 2:
                    values = list(result)
                    values[6] += 1
                    return os.stat_result(values)
                return result

            with mock.patch("review_contracts.os.fstat", side_effect=changing_fstat):
                with self.assertRaisesRegex(ValueError, "changed while snapshotting"):
                    build_git_snapshot(root, ["changing.txt"], limits=SnapshotLimits())

    def test_external_evidence_rejects_userinfo_and_secret_queries_without_echoing_secret(self) -> None:
        secret = "never-persist-this-value"
        items = [
            {
                "kind": "git_commit",
                "repository": f"https://user:{secret}@github.com/example/review.git",
                "commit": "b" * 40,
                "path": "src/review.py",
                "sha256": SHA,
                "selector": {"kind": "symbol", "value": "review"},
            },
            {
                "kind": "digest",
                "uri": f"https://artifacts.example/review?X-Amz-Signature={secret}",
                "authority": {"kind": "artifact_registry", "source": "https://artifacts.example"},
                "sha256": SHA,
            },
            {
                "kind": "digest",
                "uri": "https://artifacts.example/review",
                "authority": {
                    "kind": "artifact_registry",
                    "source": f"https://artifacts.example?access_token={secret}",
                },
                "sha256": SHA,
            },
        ]
        for item in items:
            with self.subTest(item=item):
                with self.assertRaises(ValueError) as error:
                    validate_external_evidence([item])
                self.assertNotIn(secret, str(error.exception))


if __name__ == "__main__":
    unittest.main()

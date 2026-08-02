"""Verification-evidence and production-manifest contract tests."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "adversarial-code-review" / "scripts"
MODULE_PATH = SCRIPTS / "verification_evidence.py"


def load_module():
    spec = importlib.util.spec_from_file_location("adversarial_review_verification", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class VerificationEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()

    def fixture(self, root: Path) -> Path:
        artifacts = root / "artifacts"
        artifacts.mkdir(exist_ok=True)
        stdout = b"Ran 12 tests\nOK\n"
        stderr = b""
        live = b'{"agent_type":"sol_reviewer","model":"gpt-5.6-sol"}\n'
        (artifacts / "tests.stdout").write_bytes(stdout)
        (artifacts / "tests.stderr").write_bytes(stderr)
        (artifacts / "live-provenance.json").write_bytes(live)
        manifest = {
            "schema_version": 1,
            "platform": {
                "system": "Windows",
                "release": "11",
                "machine": "AMD64",
                "python": "3.13.5",
            },
            "commands": [
                {
                    "id": "unit-tests",
                    "command": "python -B -m unittest discover -s tests -v",
                    "cwd": ".",
                    "exit_code": 0,
                    "test_counts": {"passed": 12, "failed": 0, "errors": 0, "skipped": 0},
                    "stdout": {
                        "path": "artifacts/tests.stdout",
                        "sha256": sha(stdout),
                        "size_bytes": len(stdout),
                    },
                    "stderr": {
                        "path": "artifacts/tests.stderr",
                        "sha256": sha(stderr),
                        "size_bytes": len(stderr),
                    },
                }
            ],
            "observations": [
                {
                    "id": "synthetic-contract",
                    "subject": "handler_contract_smoke",
                    "provenance": "synthetic",
                    "status": "passed",
                    "detail": "Direct handler invocation covered all configured events.",
                    "artifact": {
                        "path": "artifacts/tests.stdout",
                        "sha256": sha(stdout),
                        "size_bytes": len(stdout),
                    },
                },
                {
                    "id": "live-reviewer",
                    "subject": "subagent_provenance",
                    "provenance": "live",
                    "status": "passed",
                    "detail": "Runtime emitted exact profile and model identity.",
                    "artifact": {
                        "path": "artifacts/live-provenance.json",
                        "sha256": sha(live),
                        "size_bytes": len(live),
                    },
                },
                {
                    "id": "live-mutation",
                    "subject": "mutation_observation",
                    "provenance": "live",
                    "status": "unavailable",
                    "detail": "Current process cannot reload the newly added hook contract.",
                    "artifact": None,
                },
                {
                    "id": "live-trust",
                    "subject": "hook_trust",
                    "provenance": "live",
                    "status": "not_run",
                    "detail": "Trust approval requires a restarted interactive Codex process.",
                    "artifact": None,
                },
                {
                    "id": "live-restart",
                    "subject": "runtime_restart",
                    "provenance": "live",
                    "status": "not_run",
                    "detail": "Restart is deferred to activation and is not claimed here.",
                    "artifact": None,
                },
            ],
        }
        path = root / "verification.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    def test_builds_digest_bound_bundle_artifacts_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self.fixture(root)
            first = self.module.build_verification_evidence(manifest)
            second = self.module.build_verification_evidence(manifest)

            self.assertEqual(first, second)
            self.assertEqual(first["record"]["schema_version"], 1)
            self.assertEqual(first["sha256"], sha(first["record_bytes"]))
            self.assertIn("verification/artifacts/unit-tests.stdout", first["bundle_files"])
            self.assertIn("verification/artifacts/live-reviewer.evidence", first["bundle_files"])
            self.assertEqual(
                first["record"]["observations"][2]["status"],
                "unavailable",
            )

    def test_rejects_unknown_fields_versions_and_false_stream_digests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.fixture(Path(temporary))
            value = json.loads(manifest.read_text(encoding="utf-8"))
            value["unexpected"] = True
            manifest.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unknown"):
                self.module.build_verification_evidence(manifest)

            manifest = self.fixture(Path(temporary))
            value = json.loads(manifest.read_text(encoding="utf-8"))
            value["schema_version"] = 2
            manifest.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "version"):
                self.module.build_verification_evidence(manifest)

            manifest = self.fixture(Path(temporary))
            value = json.loads(manifest.read_text(encoding="utf-8"))
            value["schema_version"] = True
            manifest.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "version"):
                self.module.build_verification_evidence(manifest)

            manifest = self.fixture(Path(temporary))
            value = json.loads(manifest.read_text(encoding="utf-8"))
            value["commands"][0]["stdout"]["sha256"] = "0" * 64
            manifest.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "digest"):
                self.module.build_verification_evidence(manifest)

    def test_rejects_failed_verification_traversal_and_mislabelled_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.fixture(Path(temporary))
            value = json.loads(manifest.read_text(encoding="utf-8"))
            value["commands"][0]["exit_code"] = 1
            manifest.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "successful"):
                self.module.build_verification_evidence(manifest)

            manifest = self.fixture(Path(temporary))
            value = json.loads(manifest.read_text(encoding="utf-8"))
            value["commands"][0]["stdout"]["path"] = "../secret.txt"
            manifest.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "relative"):
                self.module.build_verification_evidence(manifest)

            manifest = self.fixture(Path(temporary))
            value = json.loads(manifest.read_text(encoding="utf-8"))
            source = manifest.parent / "artifacts" / "tests.stdout"
            secret = manifest.parent / "artifacts" / "access-token.txt"
            secret.write_bytes(source.read_bytes())
            value["commands"][0]["stdout"]["path"] = "artifacts/access-token.txt"
            manifest.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "credential"):
                self.module.build_verification_evidence(manifest)

            manifest = self.fixture(Path(temporary))
            value = json.loads(manifest.read_text(encoding="utf-8"))
            value["observations"][0]["provenance"] = "live"
            manifest.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "provenance"):
                self.module.build_verification_evidence(manifest)

    def test_passed_observation_requires_raw_evidence_and_unavailable_cannot_have_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.fixture(Path(temporary))
            value = json.loads(manifest.read_text(encoding="utf-8"))
            value["observations"][1]["artifact"] = None
            manifest.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "artifact"):
                self.module.build_verification_evidence(manifest)

            manifest = self.fixture(Path(temporary))
            value = json.loads(manifest.read_text(encoding="utf-8"))
            value["observations"][2]["artifact"] = value["commands"][0]["stdout"]
            manifest.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unavailable"):
                self.module.build_verification_evidence(manifest)

    def test_every_synthetic_and_live_activation_subject_must_be_disposed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.fixture(Path(temporary))
            value = json.loads(manifest.read_text(encoding="utf-8"))
            value["observations"] = value["observations"][:2]
            manifest.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing required observation subjects"):
                self.module.build_verification_evidence(manifest)

    def test_verification_manifest_and_artifacts_consume_the_shared_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.fixture(Path(temporary))
            observations = iter((0.0, 0.1, 0.2, 0.4, 0.7, 1.0))

            with self.assertRaisesRegex(ValueError, "snapshot limit exceeded"):
                self.module.build_verification_evidence(
                    manifest,
                    deadline=1.0,
                    clock=lambda: next(observations, 1.0),
                )


class ProductionManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()

    def test_manifest_is_strict_complete_and_shared_with_installer(self) -> None:
        manifest_path = ROOT / "skills" / "adversarial-code-review" / "references" / "production-manifest.json"
        manifest = self.module.load_production_manifest(manifest_path)
        copy_paths = tuple(manifest["copy_paths"])
        semantic_paths = tuple(item["path"] for item in manifest["semantic_inputs"])

        self.assertIn("skills/adversarial-code-review/references/production-manifest.json", copy_paths)
        self.assertIn("skills/adversarial-code-review/scripts/verification_evidence.py", copy_paths)
        self.assertEqual(set(semantic_paths), {"config.toml", "hooks.json"})
        self.assertEqual(set(manifest["review_paths"]), set(copy_paths) | set(semantic_paths))
        for relative in manifest["review_paths"]:
            self.assertTrue((ROOT / relative).is_file(), relative)
        skill_root = ROOT / "skills" / "adversarial-code-review"
        actual_skill_files = {
            path.relative_to(ROOT).as_posix()
            for path in skill_root.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        }
        manifested_skill_files = {
            path for path in copy_paths if path.startswith("skills/adversarial-code-review/")
        }
        self.assertEqual(manifested_skill_files, actual_skill_files)

        installer_spec = importlib.util.spec_from_file_location(
            "adversarial_review_installer_manifest_test",
            SCRIPTS / "install_review_gate.py",
        )
        assert installer_spec is not None and installer_spec.loader is not None
        installer = importlib.util.module_from_spec(installer_spec)
        installer_spec.loader.exec_module(installer)
        self.assertEqual(installer.COPY_MANIFEST, copy_paths)
        self.assertEqual(installer.PRODUCTION_REVIEW_PATHS, tuple(manifest["review_paths"]))

    def test_manifest_rejects_oversized_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_paths = [f"{i:03d}" + ("a" * 3497) for i in range(300)]
            value = {
                "schema_version": 1,
                "copy_paths": copy_paths,
                "semantic_inputs": [{"path": "config.toml", "role": "codex_config_source"}],
                "review_paths": [*copy_paths, "config.toml"],
            }
            manifest_path = root / "production.json"
            manifest_path.write_text(json.dumps(value), encoding="utf-8")
            self.assertGreater(manifest_path.stat().st_size, 1024 * 1024)
            with self.assertRaisesRegex(ValueError, "production manifest exceeds its size limit"):
                self.module.load_production_manifest(manifest_path)

    def test_manifest_deadline_prevents_slow_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "production.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "copy_paths": ["a.txt"],
                        "semantic_inputs": [{"path": "config.toml", "role": "codex_config_source"}],
                        "review_paths": ["a.txt", "config.toml"],
                    }
                ),
                encoding="utf-8",
            )
            values = iter((0.0, 2.0))

            def clock() -> float:
                return next(values, 2.0)

            with self.assertRaisesRegex(ValueError, "snapshot limit exceeded"):
                self.module.load_production_manifest(manifest, deadline=1.0, clock=clock)

    def test_manifest_uses_bounded_reader_without_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "production.json"
            manifest.write_text("{}", encoding="utf-8")
            with mock.patch.object(
                self.module,
                "_bounded_read",
                side_effect=ValueError("production.json changed while it was being read"),
            ) as bounded_read:
                with self.assertRaisesRegex(ValueError, "changed while it was being read"):
                    self.module.load_production_manifest(manifest)
            bounded_read.assert_called_once()
            self.assertIsNone(bounded_read.call_args.kwargs["deadline"])

    def test_manifest_rejects_unknown_fields_and_duplicate_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = {
                "schema_version": 1,
                "copy_paths": ["a.txt"],
                "semantic_inputs": [{"path": "config.toml", "role": "codex_config_source"}],
                "review_paths": ["a.txt", "config.toml"],
            }
            path = root / "production.json"
            path.write_text(json.dumps({**value, "extra": 1}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unknown"):
                self.module.load_production_manifest(path)

            value["copy_paths"] = ["a.txt", "a.txt"]
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                self.module.load_production_manifest(path)


class LifecycleVerificationIntegrationTests(unittest.TestCase):
    def invoke(self, hook: Path, state: Path, profile: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-B",
                str(hook),
                "--state-root",
                str(state),
                "--profile-path",
                str(profile),
                *arguments,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def fixture(self, root: Path) -> tuple[Path, Path, Path, Path, Path, Path]:
        hook = SCRIPTS / "lifecycle_gate.py"
        profile = root / "sol_reviewer.toml"
        shutil.copyfile(ROOT / "agents" / "sol_reviewer.toml", profile)
        state = root / "state"
        workspace = root / "workspace"
        workspace.mkdir()
        (workspace / "owned.txt").write_text("owned\n", encoding="utf-8")
        (workspace / "semantic.txt").write_text("semantic\n", encoding="utf-8")
        for command in (
            ["git", "init"],
            ["git", "config", "user.email", "test@example.com"],
            ["git", "config", "user.name", "Test User"],
            ["git", "add", "owned.txt", "semantic.txt"],
            ["git", "commit", "-m", "base"],
        ):
            result = subprocess.run(command, cwd=workspace, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr.decode())

        verification_root = root / "verification"
        verification_root.mkdir()
        stdout = b"Ran 1 test\nOK\n"
        stderr = b""
        synthetic = b'{"events":6,"status":"passed"}\n'
        (verification_root / "stdout.log").write_bytes(stdout)
        (verification_root / "stderr.log").write_bytes(stderr)
        (verification_root / "synthetic.json").write_bytes(synthetic)
        verification = {
            "schema_version": 1,
            "platform": {"system": "Windows", "release": "11", "machine": "AMD64", "python": "3.14"},
            "commands": [
                {
                    "id": "focused-tests",
                    "command": "python -B -m unittest tests.test_example -v",
                    "cwd": ".",
                    "exit_code": 0,
                    "test_counts": {"passed": 1, "failed": 0, "errors": 0, "skipped": 0},
                    "stdout": {"path": "stdout.log", "sha256": sha(stdout), "size_bytes": len(stdout)},
                    "stderr": {"path": "stderr.log", "sha256": sha(stderr), "size_bytes": len(stderr)},
                }
            ],
            "observations": [
                {
                    "id": "synthetic-smoke",
                    "subject": "handler_contract_smoke",
                    "provenance": "synthetic",
                    "status": "passed",
                    "detail": "Direct handler contract smoke passed.",
                    "artifact": {
                        "path": "synthetic.json",
                        "sha256": sha(synthetic),
                        "size_bytes": len(synthetic),
                    },
                },
                {
                    "id": "live-reviewer",
                    "subject": "subagent_provenance",
                    "provenance": "live",
                    "status": "unavailable",
                    "detail": "Exact installed reviewer profile is unavailable in this process.",
                    "artifact": None,
                },
                {
                    "id": "live-mutation",
                    "subject": "mutation_observation",
                    "provenance": "live",
                    "status": "unavailable",
                    "detail": "Unit fixture does not claim a live managed-mutation observation.",
                    "artifact": None,
                },
                {
                    "id": "live-trust",
                    "subject": "hook_trust",
                    "provenance": "live",
                    "status": "not_run",
                    "detail": "Unit fixture does not claim hook trust approval.",
                    "artifact": None,
                },
                {
                    "id": "live-restart",
                    "subject": "runtime_restart",
                    "provenance": "live",
                    "status": "not_run",
                    "detail": "Unit fixture does not claim a runtime restart.",
                    "artifact": None,
                },
            ],
        }
        verification_path = verification_root / "verification.json"
        verification_path.write_text(json.dumps(verification), encoding="utf-8")

        production = {
            "schema_version": 1,
            "copy_paths": ["owned.txt"],
            "semantic_inputs": [{"path": "semantic.txt", "role": "semantic_source"}],
            "review_paths": ["owned.txt", "semantic.txt"],
        }
        production_path = workspace / "production.json"
        production_path.write_text(json.dumps(production), encoding="utf-8")
        return hook, state, profile, workspace, verification_path, production_path

    def arm(self, hook: Path, state: Path, profile: Path, workspace: Path) -> None:
        result = self.invoke(
            hook,
            state,
            profile,
            "classify",
            "--session-id",
            "session",
            "--turn-id",
            "turn",
            "--classification",
            "material",
            "--task-id",
            "task",
            "--paths",
            "owned.txt",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_freeze_requires_verification_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            hook, state, profile, workspace, _, _ = self.fixture(Path(temporary))
            self.arm(hook, state, profile, workspace)
            result = self.invoke(
                hook,
                state,
                profile,
                "freeze",
                "--session-id",
                "session",
                "--turn-id",
                "turn",
                "--cwd",
                str(workspace),
                "--paths",
                "owned.txt",
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("verification", result.stderr.casefold())

    def test_freeze_binds_verification_and_complete_production_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            hook, state, profile, workspace, verification, production = self.fixture(Path(temporary))
            self.arm(hook, state, profile, workspace)
            result = self.invoke(
                hook,
                state,
                profile,
                "freeze",
                "--session-id",
                "session",
                "--turn-id",
                "turn",
                "--cwd",
                str(workspace),
                "--paths",
                "owned.txt",
                "--verification-manifest",
                str(verification),
                "--production-manifest",
                str(production),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            delivery = json.loads(result.stdout)
            bundle = state / "bundles" / delivery["bundle_sha256"]
            record = json.loads((bundle / "verification-evidence.json").read_text(encoding="utf-8"))
            contract = json.loads((bundle / "review-contract.json").read_text(encoding="utf-8"))
            packet = json.loads((bundle / "review-packet.json").read_text(encoding="utf-8"))
            snapshot = json.loads((bundle / "snapshot.json").read_text(encoding="utf-8"))
            verification_sha = sha((bundle / "verification-evidence.json").read_bytes())
            production_sha = sha(production.read_bytes())

            self.assertEqual(contract["verification_sha256"], verification_sha)
            self.assertEqual(packet["verification_sha256"], verification_sha)
            self.assertEqual(contract["production_manifest_sha256"], production_sha)
            self.assertEqual(packet["production_manifest_sha256"], production_sha)
            self.assertEqual({item["path"] for item in snapshot["files"]}, {"owned.txt", "semantic.txt"})
            self.assertEqual(record["observations"][1]["status"], "unavailable")
            self.assertTrue((bundle / "verification" / "artifacts" / "focused-tests.stdout").is_file())


if __name__ == "__main__":
    unittest.main()

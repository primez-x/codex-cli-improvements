from __future__ import annotations

import argparse
import concurrent.futures
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "skills" / "adversarial-code-review" / "scripts" / "lifecycle_gate.py"
PROFILE = ROOT / "agents" / "sol_reviewer.toml"
sys.path.insert(0, str(HOOK.parent))
import lifecycle_gate  # noqa: E402


def run_process(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(arguments, capture_output=True, check=False, **kwargs)
    return result


def run_hook(
    testcase: unittest.TestCase,
    payload: dict[str, object],
    state_root: Path,
    profile: Path,
) -> dict[str, object]:
    result = run_process(
        [
            sys.executable,
            str(HOOK),
            "--state-root",
            str(state_root),
            "--profile-path",
            str(profile),
        ],
        input=json.dumps(payload).encode() + b"\n",
    )
    testcase.assertEqual(result.returncode, 0, result.stderr.decode())
    return json.loads(result.stdout or b"{}")


def run_cli(
    testcase: unittest.TestCase,
    state_root: Path,
    profile: Path,
    *arguments: str,
    expected: int = 0,
) -> dict[str, object]:
    arguments_list = list(arguments)
    if arguments_list and arguments_list[0] == "freeze" and "--verification-manifest" not in arguments_list:
        evidence_root = lifecycle_gate._filesystem_path(
            state_root.parent / "test-verification"
        )
        evidence_root.mkdir(exist_ok=True)
        stdout = b"lifecycle fixture verification passed\n"
        stderr = b""
        synthetic = b'{"handler_contract_smoke":"passed"}\n'
        (evidence_root / "stdout.log").write_bytes(stdout)
        (evidence_root / "stderr.log").write_bytes(stderr)
        (evidence_root / "synthetic.json").write_bytes(synthetic)
        manifest = {
            "schema_version": 1,
            "platform": {"system": "Windows", "release": "test", "machine": "test", "python": sys.version},
            "commands": [
                {
                    "id": "lifecycle-fixture",
                    "command": "python -B -m unittest tests.test_adversarial_review_hooks -v",
                    "cwd": ".",
                    "exit_code": 0,
                    "test_counts": {"passed": 1, "failed": 0, "errors": 0, "skipped": 0},
                    "stdout": {
                        "path": "stdout.log",
                        "sha256": hashlib.sha256(stdout).hexdigest(),
                        "size_bytes": len(stdout),
                    },
                    "stderr": {
                        "path": "stderr.log",
                        "sha256": hashlib.sha256(stderr).hexdigest(),
                        "size_bytes": len(stderr),
                    },
                }
            ],
            "observations": [
                {
                    "id": "synthetic-handler",
                    "subject": "handler_contract_smoke",
                    "provenance": "synthetic",
                    "status": "passed",
                    "detail": "Test fixture exercises the handler contract directly.",
                    "artifact": {
                        "path": "synthetic.json",
                        "sha256": hashlib.sha256(synthetic).hexdigest(),
                        "size_bytes": len(synthetic),
                    },
                },
                {
                    "id": "live-provenance",
                    "subject": "subagent_provenance",
                    "provenance": "live",
                    "status": "unavailable",
                    "detail": "Unit tests do not claim a live installed profile observation.",
                    "artifact": None,
                },
                {
                    "id": "live-mutation",
                    "subject": "mutation_observation",
                    "provenance": "live",
                    "status": "unavailable",
                    "detail": "Unit tests do not claim a live managed-mutation observation.",
                    "artifact": None,
                },
                {
                    "id": "live-trust",
                    "subject": "hook_trust",
                    "provenance": "live",
                    "status": "not_run",
                    "detail": "Unit tests do not claim hook trust approval.",
                    "artifact": None,
                },
                {
                    "id": "live-restart",
                    "subject": "runtime_restart",
                    "provenance": "live",
                    "status": "not_run",
                    "detail": "Unit tests do not claim a runtime restart.",
                    "artifact": None,
                },
            ],
        }
        verification_path = evidence_root / "verification.json"
        verification_path.write_text(json.dumps(manifest), encoding="utf-8")
        arguments_list.extend(("--verification-manifest", str(verification_path)))
    result = run_process(
        [
            sys.executable,
            str(HOOK),
            "--state-root",
            str(state_root),
            "--profile-path",
            str(profile),
            *arguments_list,
        ]
    )
    testcase.assertEqual(result.returncode, expected, result.stderr.decode())
    stream = result.stdout if expected == 0 else result.stderr
    return json.loads(stream or b"{}")


def run_cli_with_fault(
    testcase: unittest.TestCase,
    state_root: Path,
    profile: Path,
    fault: str,
    *arguments: str,
) -> dict[str, object]:
    environment = dict(os.environ)
    environment["CODEX_ACR_FAULT_INJECT"] = fault
    result = run_process(
        [
            sys.executable,
            str(HOOK),
            "--state-root",
            str(state_root),
            "--profile-path",
            str(profile),
            *arguments,
        ],
        env=environment,
    )
    testcase.assertEqual(result.returncode, 2, result.stderr.decode())
    return json.loads(result.stderr or b"{}")


class LifecycleGateTests(unittest.TestCase):
    def test_delivery_state_address_stays_below_legacy_windows_directory_limit(self) -> None:
        root = Path("C:/Users/Example/AppData/Local/Temp/tmp12345678/state")
        state = {
            "session_id": "session",
            "task_id": "task",
            "delivery_id": "delivery",
            "generation": 0,
        }

        path = lifecycle_gate.delivery_path(root, state)

        self.assertLess(len(str(path.parent)), 248)
        self.assertEqual(path.name, "generation-0.json")
        self.assertNotEqual(
            path.parent,
            lifecycle_gate.delivery_path(root, {**state, "task_id": "another-task"}).parent,
        )

    def make_fixture(self, temporary: str) -> tuple[Path, Path, Path]:
        root = Path(temporary)
        state_root = root / "state"
        profile = root / "sol_reviewer.toml"
        shutil.copyfile(PROFILE, profile)
        workspace = root / "workspace"
        workspace.mkdir()
        (workspace / "owned.txt").write_text("base\n", encoding="utf-8")
        for command in (
            ["git", "init"],
            ["git", "config", "user.email", "test@example.com"],
            ["git", "config", "user.name", "Test User"],
            ["git", "add", "owned.txt"],
            ["git", "commit", "-m", "base"],
        ):
            result = run_process(command, cwd=workspace)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
        return state_root, profile, workspace

    def rewrite_active_state_as_legacy(
        self,
        state_root: Path,
        state: dict[str, object],
    ) -> tuple[Path, Path]:
        current = lifecycle_gate.delivery_path(state_root, state)
        legacy = (
            state_root
            / "deliveries"
            / lifecycle_gate.digest(str(state["session_id"]))
            / lifecycle_gate.digest(str(state["task_id"]))
            / lifecycle_gate.digest(str(state["delivery_id"]))
            / f"generation-{int(state['generation'])}.json"
        )
        lifecycle_gate.save(legacy, state)
        pointer = lifecycle_gate._pointer(state_root, state, legacy)
        lifecycle_gate.save(
            lifecycle_gate.state_path(
                state_root,
                str(state["session_id"]),
                str(state["turn_id"]),
            ),
            pointer,
        )
        lifecycle_gate.save(
            lifecycle_gate.session_state_path(state_root, str(state["session_id"])),
            pointer,
        )
        current.unlink()
        return legacy, current

    def payload(self, event: str, workspace: Path, **extra: object) -> dict[str, object]:
        return {
            "session_id": "session",
            "turn_id": "turn",
            "cwd": str(workspace),
            "model": "gpt-5.6-sol",
            "hook_event_name": event,
            **extra,
        }

    def arm(self, state_root: Path, profile: Path, workspace: Path) -> dict[str, object]:
        submitted = run_hook(
            self,
            self.payload("UserPromptSubmit", workspace, prompt="Implement the requested change."),
            state_root,
            profile,
        )
        self.assertIn("delivery_id", submitted["hookSpecificOutput"]["additionalContext"])
        return run_cli(
            self,
            state_root,
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

    def freeze(self, state_root: Path, profile: Path, workspace: Path) -> dict[str, object]:
        return run_cli(
            self,
            state_root,
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

    def status(self, state_root: Path, profile: Path) -> dict[str, object]:
        return run_cli(
            self,
            state_root,
            profile,
            "status",
            "--session-id",
            "session",
            "--turn-id",
            "turn",
        )

    def start_reviewer(
        self,
        state_root: Path,
        profile: Path,
        workspace: Path,
        agent_id: str = "reviewer-1",
    ) -> dict[str, object]:
        started = run_hook(
            self,
            self.payload(
                "SubagentStart",
                workspace,
                agent_id=agent_id,
                agent_type="sol_reviewer",
            ),
            state_root,
            profile,
        )
        self.assertNotIn("decision", started)
        return self.status(state_root, profile)

    def review_output(
        self,
        state: dict[str, object],
        *,
        verdict: str = "pass",
        findings: list[dict[str, object]] | None = None,
        risks: list[str] | None = None,
    ) -> dict[str, object]:
        normalized_findings: list[dict[str, object]] = []
        for finding in findings or []:
            normalized = dict(finding)
            if not normalized.get("evidence"):
                normalized["evidence"] = [
                    {
                        "kind": "bundle",
                        "uri": f"bundle://{state['bundle_sha256']}/review-lenses.md",
                        "sha256": state["lens_sha256"],
                        "selector": {"kind": "line_range", "start": 1, "end": 1},
                    }
                ]
            normalized_findings.append(normalized)
        return {
            "schema_version": 1,
            "attempt_id": state["attempt_id"],
            "packet_sha256": state["packet_sha256"],
            "bundle_sha256": state["bundle_sha256"],
            "snapshot_sha256": state["snapshot_sha256"],
            "verdict": verdict,
            "coverage": [
                f"{lens}: reviewed - complete frozen bundle"
                for lens in lifecycle_gate.MANDATORY_REVIEW_LENSES
            ],
            "residual_risks": risks or [],
            "findings": normalized_findings,
        }

    def stop_reviewer(
        self,
        state_root: Path,
        profile: Path,
        workspace: Path,
        output: dict[str, object],
        agent_id: str = "reviewer-1",
    ) -> dict[str, object]:
        return run_hook(
            self,
            self.payload(
                "SubagentStop",
                workspace,
                agent_id=agent_id,
                agent_type="sol_reviewer",
                last_assistant_message=json.dumps(output),
                stop_hook_active=False,
            ),
            state_root,
            profile,
        )

    def disposition(
        self,
        root: Path,
        state_root: Path,
        profile: Path,
        ledger: dict[str, object],
        *,
        expected: int = 0,
    ) -> dict[str, object]:
        path = root / "ledger.json"
        path.write_text(json.dumps(ledger), encoding="utf-8")
        return run_cli(
            self,
            state_root,
            profile,
            "disposition",
            "--session-id",
            "session",
            "--turn-id",
            "turn",
            "--file",
            str(path),
            expected=expected,
        )

    def empty_receipt(self, root: Path, state_root: Path, profile: Path, workspace: Path) -> dict[str, object]:
        self.arm(state_root, profile, workspace)
        self.freeze(state_root, profile, workspace)
        state = self.start_reviewer(state_root, profile, workspace)
        accepted = self.stop_reviewer(state_root, profile, workspace, self.review_output(state))
        self.assertNotIn("decision", accepted)
        self.disposition(root, state_root, profile, {"schema_version": 1, "generation": 0, "dispositions": []})
        return self.status(state_root, profile)

    def blocking_review(
        self,
        state_root: Path,
        profile: Path,
        workspace: Path,
        *,
        severity: str = "high",
    ) -> tuple[dict[str, object], dict[str, object]]:
        self.arm(state_root, profile, workspace)
        self.freeze(state_root, profile, workspace)
        state = self.start_reviewer(state_root, profile, workspace)
        bundle = state_root / "bundles" / str(state["bundle_sha256"])
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        evidence = {
            "kind": "bundle",
            "uri": f"bundle://{state['bundle_sha256']}/snapshot.json",
            "sha256": manifest["snapshot.json"],
            "selector": {"kind": "line_range", "start": 1, "end": 1},
        }
        finding = {
            "id": "F-1",
            "severity": severity,
            "claim": "The review assumption is wrong.",
            "evidence": [evidence],
            "correction": "Change the assumption.",
            "verification": "Inspect the immutable evidence.",
        }
        accepted = self.stop_reviewer(
            state_root,
            profile,
            workspace,
            self.review_output(state, verdict="fail", findings=[finding]),
        )
        self.assertNotIn("decision", accepted)
        return state, evidence

    @staticmethod
    def rejection_ledger(evidence: dict[str, object]) -> dict[str, object]:
        return {
            "schema_version": 1,
            "generation": 0,
            "dispositions": [{
                "finding_id": "F-1",
                "decision": "rejected",
                "primary_counterevidence": [evidence],
            }],
        }

    def test_legacy_delivery_state_migrates_before_status_and_mutation_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_root, profile, workspace = self.make_fixture(temporary)
            armed = self.arm(state_root, profile, workspace)
            legacy, current = self.rewrite_active_state_as_legacy(state_root, armed)

            migrated = self.status(state_root, profile)

            self.assertEqual(migrated, armed)
            self.assertEqual(lifecycle_gate.load(legacy), armed)
            self.assertTrue(current.is_file())
            for pointer_path in (
                lifecycle_gate.state_path(state_root, "session", "turn"),
                lifecycle_gate.session_state_path(state_root, "session"),
            ):
                pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
                self.assertEqual(pointer["state"], current.relative_to(state_root).as_posix())

            reserved = run_hook(
                self,
                self.payload(
                    "PreToolUse",
                    workspace,
                    tool_name="apply_patch",
                    tool_use_id="legacy-mutation",
                ),
                state_root,
                profile,
            )
            recorded = run_hook(
                self,
                self.payload(
                    "PostToolUse",
                    workspace,
                    tool_name="apply_patch",
                    tool_use_id="legacy-mutation",
                ),
                state_root,
                profile,
            )
            self.assertNotIn("decision", reserved)
            self.assertNotIn("decision", recorded)
            self.assertEqual(self.status(state_root, profile)["mutation_epoch"], 1)
            shutil.rmtree(lifecycle_gate._filesystem_path(state_root / "deliveries"))

    def test_legacy_receipted_state_migrates_before_stop_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_root, profile, workspace = self.make_fixture(temporary)
            receipted = self.empty_receipt(root, state_root, profile, workspace)
            legacy, current = self.rewrite_active_state_as_legacy(state_root, receipted)

            exported = run_cli(
                self,
                state_root,
                profile,
                "export-replay",
                "--session-id",
                "session",
                "--turn-id",
                "turn",
            )
            stopped = run_hook(
                self,
                self.payload("Stop", workspace, last_assistant_message="Delivery complete."),
                state_root,
                profile,
            )

            self.assertEqual(exported["state_relative_path"], current.relative_to(state_root).as_posix())
            self.assertEqual(lifecycle_gate.load(legacy), receipted)
            self.assertNotIn("decision", stopped)
            self.assertEqual(self.status(state_root, profile)["status"], "completed")
            shutil.rmtree(lifecycle_gate._filesystem_path(state_root / "deliveries"))

    def test_replay_export_is_lifecycle_generated_and_references_persisted_artifacts(self) -> None:
        """A standalone receipt/output wrapper must not substitute for gate authority."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_root, profile, workspace = self.make_fixture(temporary)
            state = self.empty_receipt(root, state_root, profile, workspace)
            exported = run_cli(
                self,
                state_root,
                profile,
                "export-replay",
                "--session-id",
                "session",
                "--turn-id",
                "turn",
            )
            self.assertEqual(exported["schema_version"], 1)
            self.assertEqual(exported["authority"], "lifecycle_gate_export_v1")
            self.assertEqual(exported["bundle_sha256"], state["bundle_sha256"])
            self.assertEqual(exported["output_sha256"], state["output_sha256"])
            self.assertEqual(exported["profile_sha256"], state["profile_sha256"])
            self.assertEqual(exported["review_output"], state["review_output"])
            self.assertEqual(exported["receipt"], state["receipt"])
            persisted = state_root.joinpath(*exported["state_relative_path"].split("/"))
            self.assertTrue(persisted.is_file())
            self.assertEqual(hashlib.sha256(persisted.read_bytes()).hexdigest(), exported["state_sha256"])

    def test_replay_export_authenticates_nested_manifest_named_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_root, profile, workspace = self.make_fixture(temporary)
            nested = workspace / "nested" / "manifest.json"
            nested.parent.mkdir()
            nested.write_text('{"nested":true}\n', encoding="utf-8")
            for command in (
                ["git", "add", "nested/manifest.json"],
                ["git", "commit", "-m", "nested manifest fixture"],
            ):
                result = run_process(command, cwd=workspace)
                self.assertEqual(result.returncode, 0, result.stderr.decode())

            run_hook(
                self,
                self.payload("UserPromptSubmit", workspace, prompt="Implement the requested change."),
                state_root,
                profile,
            )
            run_cli(
                self,
                state_root,
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
                "nested/manifest.json",
            )
            state = run_cli(
                self,
                state_root,
                profile,
                "freeze",
                "--session-id",
                "session",
                "--turn-id",
                "turn",
                "--cwd",
                str(workspace),
                "--paths",
                "nested/manifest.json",
            )
            state = self.start_reviewer(state_root, profile, workspace)
            self.assertNotIn("decision", self.stop_reviewer(state_root, profile, workspace, self.review_output(state)))
            self.disposition(root, state_root, profile, {"schema_version": 1, "generation": 0, "dispositions": []})
            exported = run_cli(
                self,
                state_root,
                profile,
                "export-replay",
                "--session-id",
                "session",
                "--turn-id",
                "turn",
            )
            self.assertEqual(exported["bundle_sha256"], state["bundle_sha256"])

            frozen_nested = (
                state_root
                / "bundles"
                / str(state["bundle_sha256"])
                / "evidence"
                / "worktree"
                / "nested"
                / "manifest.json"
            )
            os.chmod(frozen_nested, 0o600)
            frozen_nested.write_text('{"nested":false}\n', encoding="utf-8")
            rejected = run_cli(
                self,
                state_root,
                profile,
                "export-replay",
                "--session-id",
                "session",
                "--turn-id",
                "turn",
                expected=2,
            )
            self.assertIn("digest", str(rejected["detail"]))

    def test_freeze_timeout_is_bounded_and_configurable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_root, profile, workspace = self.make_fixture(temporary)
            self.arm(state_root, profile, workspace)
            rejected = run_cli(
                self,
                state_root,
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
                "--max-freeze-seconds",
                "0",
                expected=2,
            )
            self.assertIn("between 1 and 300", str(rejected["detail"]))
            frozen = run_cli(
                self,
                state_root,
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
                "--max-freeze-seconds",
                "180",
            )
            self.assertEqual(frozen["status"], "reviewing")

    def test_worktree_evidence_reads_consume_the_shared_freeze_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / "large.bin"
            source.write_bytes(b"a" * (2 * 1024 * 1024))
            observations = iter((0.0, 0.1, 0.2, 0.4, 0.7, 1.0))

            with self.assertRaisesRegex(ValueError, "evidence deadline exceeded"):
                lifecycle_gate._bounded_regular_file(
                    source,
                    root,
                    max_bytes=3 * 1024 * 1024,
                    deadline=1.0,
                    clock=lambda: next(observations, 1.0),
                )

    def test_git_head_resolution_consumes_the_shared_freeze_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            for object_id in ("1" * 40, "2" * 64):
                calls: list[tuple[list[str], float]] = []
                clock_values = iter((0.0, 0.2, 0.3, 0.5))

                def runner(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
                    calls.append((arguments, float(kwargs["timeout"])))
                    stdout = b"true\n" if len(calls) == 1 else object_id.encode("ascii") + b"\n"
                    return subprocess.CompletedProcess(arguments, 0, stdout, b"")

                head = lifecycle_gate._git_head(
                    workspace,
                    deadline=1.0,
                    clock=lambda: next(clock_values, 1.0),
                    runner=runner,
                )
                self.assertEqual(head, object_id)
                self.assertEqual([round(timeout, 1) for _, timeout in calls], [1.0, 0.7])

            for invalid in ("1" * 39, "1" * 41, "1" * 63, "1" * 65, "A" * 40, "g" * 40):
                responses = iter((b"true\n", invalid.encode("ascii") + b"\n"))

                def invalid_runner(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
                    return subprocess.CompletedProcess(arguments, 0, next(responses), b"")

                with self.assertRaisesRegex(ValueError, "Git HEAD resolution is malformed"):
                    lifecycle_gate._git_head(
                        workspace,
                        deadline=1.0,
                        clock=lambda: 0.0,
                        runner=invalid_runner,
                    )

            def timed_out(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
                raise subprocess.TimeoutExpired(arguments, kwargs["timeout"])

            with self.assertRaisesRegex(ValueError, "evidence deadline exceeded"):
                lifecycle_gate._git_head(
                    workspace,
                    deadline=1.0,
                    clock=lambda: 0.0,
                    runner=timed_out,
                )

    def test_sha256_repository_freezes_with_full_object_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_root = root / "state"
            profile = root / "sol_reviewer.toml"
            shutil.copyfile(PROFILE, profile)
            workspace = root / "workspace"
            result = run_process(["git", "init", "--object-format=sha256", str(workspace)])
            if result.returncode != 0:
                self.skipTest("bundled Git does not support SHA-256 repositories")
            (workspace / "owned.txt").write_text("base\n", encoding="utf-8")
            for command in (
                ["git", "config", "user.email", "test@example.com"],
                ["git", "config", "user.name", "Test User"],
                ["git", "add", "owned.txt"],
                ["git", "commit", "-m", "base"],
            ):
                result = run_process(command, cwd=workspace)
                self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.arm(state_root, profile, workspace)
            frozen = self.freeze(state_root, profile, workspace)
            bundle_root = state_root / "bundles" / frozen["bundle_sha256"]
            snapshot = json.loads((bundle_root / "snapshot.json").read_text(encoding="utf-8"))
            self.assertEqual(len(snapshot["base"]), 64)
            self.assertEqual(len(snapshot["head"]), 64)

    def test_freeze_snapshot_budget_cannot_be_rebased_from_head_consumption(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            state_root, profile, workspace = self.make_fixture(temporary)
            self.arm(state_root, profile, workspace)
            state = lifecycle_gate.load_active(state_root, "session", "turn")
            self.assertIsNotNone(state)
            verification_root = root / "verification"
            verification_root.mkdir()
            stdout = b"Ran 1 test\nOK\n"
            stderr = b""
            synthetic = b'{"events":1,"status":"passed"}\n'
            (verification_root / "stdout.log").write_bytes(stdout)
            (verification_root / "stderr.log").write_bytes(stderr)
            (verification_root / "synthetic.json").write_bytes(synthetic)
            verification_path = verification_root / "verification.json"
            verification_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "platform": {"system": "Windows", "release": "11", "machine": "test", "python": "3.13"},
                        "commands": [
                            {
                                "id": "focused-tests",
                                "command": "python -B -m unittest -v",
                                "cwd": ".",
                                "exit_code": 0,
                                "test_counts": {"passed": 1, "failed": 0, "errors": 0, "skipped": 0},
                                "stdout": {"path": "stdout.log", "sha256": hashlib.sha256(stdout).hexdigest(), "size_bytes": len(stdout)},
                                "stderr": {"path": "stderr.log", "sha256": hashlib.sha256(stderr).hexdigest(), "size_bytes": len(stderr)},
                            }
                        ],
                        "observations": [
                            {
                                "id": "synthetic-smoke",
                                "subject": "handler_contract_smoke",
                                "provenance": "synthetic",
                                "status": "passed",
                                "detail": "Focused test fixture passed.",
                                "artifact": {"path": "synthetic.json", "sha256": hashlib.sha256(synthetic).hexdigest(), "size_bytes": len(synthetic)},
                            },
                            {
                                "id": "live-reviewer",
                                "subject": "subagent_provenance",
                                "provenance": "live",
                                "status": "unavailable",
                                "detail": "Live provenance is not available in this test.",
                                "artifact": None,
                            },
                            {
                                "id": "live-mutation",
                                "subject": "mutation_observation",
                                "provenance": "live",
                                "status": "unavailable",
                                "detail": "Live mutation provenance is unavailable in this test.",
                                "artifact": None,
                            },
                            {
                                "id": "live-trust",
                                "subject": "hook_trust",
                                "provenance": "live",
                                "status": "not_run",
                                "detail": "Trust approval is not available in this test.",
                                "artifact": None,
                            },
                            {
                                "id": "live-restart",
                                "subject": "runtime_restart",
                                "provenance": "live",
                                "status": "not_run",
                                "detail": "Runtime restart is not available in this test.",
                                "artifact": None,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            captured: dict[str, Any] = {}
            clock = iter((0.0, 0.2, 0.8, 0.8))

            def fixed_clock() -> float:
                return next(clock, 0.8)

            def fake_git_head(workspace_path: Path, deadline: float, *_) -> str:
                captured["head_deadline"] = deadline
                _ = lifecycle_gate.time.monotonic()
                return "1" * 40

            def fake_snapshot(
                workspace_path: Path,
                snapshot_paths: list[str],
                *,
                limits: lifecycle_gate.SnapshotLimits,
                base: str | None,
                absolute_deadline: float | None,
            ) -> dict[str, Any]:
                captured["snapshot_limits"] = limits.max_seconds
                captured["snapshot_base"] = base
                captured["snapshot_paths"] = snapshot_paths
                captured["snapshot_deadline"] = absolute_deadline
                return {"snapshot_sha256": "f" * 64, "files": []}

            def fake_bundle_evidence(*_args: Any, **_kwargs: Any) -> dict[str, bytes]:
                return {}

            def fake_build_bundle(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
                return {"bundle_sha256": "b" * 64}

            def fake_build_verification(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
                return {"record": {}, "record_bytes": b"{}", "sha256": "a" * 64, "bundle_files": {}}

            original_clock = lifecycle_gate.time.monotonic
            original_git_head = lifecycle_gate._git_head
            original_snapshot = lifecycle_gate.build_git_snapshot
            original_bundle = lifecycle_gate._bundle_evidence
            original_build_bundle = lifecycle_gate.build_bundle
            original_verification = lifecycle_gate.build_verification_evidence
            lifecycle_gate.time.monotonic = fixed_clock
            lifecycle_gate._git_head = fake_git_head
            lifecycle_gate.build_git_snapshot = fake_snapshot
            lifecycle_gate._bundle_evidence = fake_bundle_evidence
            lifecycle_gate.build_bundle = fake_build_bundle
            lifecycle_gate.build_verification_evidence = fake_build_verification
            try:
                frozen = lifecycle_gate._freeze(
                    state,
                    argparse.Namespace(
                        cwd=str(workspace),
                        paths=["owned.txt"],
                        verification_manifest=str(verification_path),
                        production_manifest=None,
                        max_freeze_seconds=1.0,
                    ),
                    state_root,
                    profile,
                )
            finally:
                lifecycle_gate.time.monotonic = original_clock
                lifecycle_gate._git_head = original_git_head
                lifecycle_gate.build_git_snapshot = original_snapshot
                lifecycle_gate._bundle_evidence = original_bundle
                lifecycle_gate.build_bundle = original_build_bundle
                lifecycle_gate.build_verification_evidence = original_verification
            self.assertEqual(captured["snapshot_base"], "1" * 40)
            self.assertEqual(captured["snapshot_limits"], 1.0)
            self.assertEqual(captured["snapshot_deadline"], 1.0)
            self.assertEqual(captured["head_deadline"], 1.0)
            self.assertEqual(frozen["status"], "reviewing")
            self.assertEqual(captured["snapshot_paths"], ["owned.txt"])

    def test_prompt_classification_honors_explicit_exemptions_without_bypassing_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_root, profile, workspace = self.make_fixture(temporary)
            for turn, prompt, expected in (
                ("accepted", "Implement the plan", "pending"),
                ("accepted-plan-only", "Implement the plan only after review", "pending"),
                ("repair", "diagnose and fix this", "pending"),
                ("repair-read-only", "diagnose and fix this in read-only mode", "pending"),
                ("review-update", "review then update it", "pending"),
                ("review-only-then-update", "review only the proposal, then update it", "pending"),
                ("plan-mixed", "plan only how to fix this", "exempt"),
                ("review-mixed", "review only the proposed update", "exempt"),
                ("read-mixed", "read-only: explain how to implement this", "exempt"),
                ("no-change-mixed", "do not change anything; explain how to fix this", "exempt"),
            ):
                result = run_hook(
                    self,
                    {
                        **self.payload("UserPromptSubmit", workspace, prompt=prompt),
                        "session_id": f"session-{turn}",
                        "turn_id": turn,
                    },
                    state_root,
                    profile,
                )
                self.assertIn(expected, result["hookSpecificOutput"]["additionalContext"].lower())
                state = lifecycle_gate.load_active(state_root, f"session-{turn}", turn)
                self.assertIsNotNone(state)
                self.assertEqual(state["classification"], expected)
                if expected == "exempt":
                    self.assertEqual(state["exempt_reason"], "automatic: explicit read-only or plan-only prompt")
                else:
                    self.assertIsNone(state["exempt_reason"])

    def test_supported_mutation_aliases_are_complete_and_long_lived_ids_are_idempotent(self) -> None:
        direct = ("apply_patch", "functions.apply_patch", "Edit", "Write", "mcp__filesystem__write_file", "mcp__filesystem__move_file")
        for name in direct:
            self.assertTrue(lifecycle_gate.is_mutation({"tool_name": name, "tool_input": {}}), name)
        for name, command in (
            ("Bash", "echo changed > owned.txt"),
            ("shell_command", "Set-Content -LiteralPath owned.txt -Value changed"),
            ("functions.shell_command", "git apply change.patch"),
            ("exec_command", "mv a b"),
        ):
            self.assertTrue(lifecycle_gate.is_mutation({"tool_name": name, "tool_input": {"command": command}}), name)
        self.assertFalse(lifecycle_gate.is_mutation({"tool_name": "mcp__filesystem__read_file", "tool_input": {"path": "x"}}))
        self.assertFalse(lifecycle_gate.is_mutation({"tool_name": "Bash", "tool_input": {"command": "git status"}}))

        with tempfile.TemporaryDirectory() as temporary:
            state_root, profile, workspace = self.make_fixture(temporary)
            self.arm(state_root, profile, workspace)
            for index in range(300):
                lifecycle_gate.post_tool(
                    self.payload(
                        "PostToolUse",
                        workspace,
                        tool_name="apply_patch",
                        tool_use_id=f"tool-{index}",
                        tool_input={},
                    ),
                    state_root,
                )
            for index in range(50):
                lifecycle_gate.post_tool(
                    self.payload(
                        "PostToolUse",
                        workspace,
                        tool_name="apply_patch",
                        tool_use_id=f"tool-{index}",
                        tool_input={},
                    ),
                    state_root,
                )
            state = self.status(state_root, profile)
            self.assertEqual(state["mutation_epoch"], 300)
            self.assertEqual(len(state["seen_tool_use_ids"]), 300)

    def test_mutation_hooks_fail_closed_until_material_classification_and_late_post_arms(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_root, profile, workspace = self.make_fixture(temporary)
            mutation = self.payload(
                "PreToolUse",
                workspace,
                tool_name="apply_patch",
                tool_use_id="mutation-1",
                tool_input={},
            )

            absent = run_hook(self, mutation, state_root, profile)
            self.assertEqual(absent["decision"], "block")
            pending = self.status(state_root, profile)
            self.assertEqual(pending["classification"], "pending")
            self.assertEqual(pending["status"], "pending_classification")
            self.assertEqual(pending["inflight_tool_use_ids"], [])

            still_pending = run_hook(self, {**mutation, "tool_use_id": "mutation-2"}, state_root, profile)
            self.assertEqual(still_pending["decision"], "block")
            run_cli(
                self,
                state_root,
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
            allowed = run_hook(self, {**mutation, "tool_use_id": "mutation-3"}, state_root, profile)
            self.assertNotIn("decision", allowed)
            material = self.status(state_root, profile)
            self.assertEqual(material["inflight_tool_use_ids"], ["mutation-3"])

        with tempfile.TemporaryDirectory() as temporary:
            state_root, profile, workspace = self.make_fixture(temporary)
            run_hook(
                self,
                self.payload("UserPromptSubmit", workspace, prompt="Read-only: inspect this."),
                state_root,
                profile,
            )
            late = run_hook(
                self,
                self.payload(
                    "PostToolUse",
                    workspace,
                    tool_name="apply_patch",
                    tool_use_id="late-1",
                    tool_input={},
                ),
                state_root,
                profile,
            )
            self.assertEqual(late["decision"], "block")
            armed = self.status(state_root, profile)
            self.assertEqual(armed["classification"], "pending")
            self.assertEqual(armed["status"], "pending_classification")
            self.assertEqual(armed["mutation_epoch"], 1)
            self.assertEqual(armed["seen_tool_use_ids"], ["late-1"])

    def test_freeze_preserves_inflight_lease_and_reconcile_is_explicit_monotonic_and_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_root, profile, workspace = self.make_fixture(temporary)
            self.arm(state_root, profile, workspace)
            run_hook(
                self,
                self.payload(
                    "PreToolUse",
                    workspace,
                    tool_name="apply_patch",
                    tool_use_id="failed-tool",
                    tool_input={},
                ),
                state_root,
                profile,
            )
            failed = run_cli(
                self,
                state_root,
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
                expected=2,
            )
            self.assertIn("in flight", failed["detail"])
            leased = self.status(state_root, profile)
            self.assertEqual(leased["inflight_tool_use_ids"], ["failed-tool"])
            self.assertEqual(leased["mutation_epoch"], 0)

            reconciled = run_cli(
                self,
                state_root,
                profile,
                "reconcile",
                "--session-id",
                "session",
                "--turn-id",
                "turn",
                "--tool-use-id",
                "failed-tool",
                "--evidence",
                "tool returned a confirmed failure before applying its edit",
            )
            self.assertEqual(reconciled["inflight_tool_use_ids"], [])
            self.assertEqual(reconciled["seen_tool_use_ids"], ["failed-tool"])
            self.assertEqual(reconciled["mutation_epoch"], 1)
            self.assertEqual(reconciled["status"], "armed")
            self.freeze(state_root, profile, workspace)

            reviewer = self.start_reviewer(state_root, profile, workspace)
            aborted = run_cli(
                self,
                state_root,
                profile,
                "abort",
                "--session-id",
                "session",
                "--turn-id",
                "turn",
                "--scope",
                "reviewer",
                "--attempt-id",
                str(reviewer["attempt_id"]),
                "--evidence",
                "reviewer process terminated without a usable final message",
            )
            self.assertEqual(aborted["status"], "stale")
            self.assertEqual(aborted["mutation_epoch"], 2)
            self.assertIn(reviewer["attempt_id"], aborted["consumed_attempt_ids"])
            self.assertIsNone(aborted["receipt"])

    def test_session_unresolved_material_delivery_survives_turn_changes_until_completion_or_abandon(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_root, profile, workspace = self.make_fixture(temporary)
            first = self.arm(state_root, profile, workspace)
            later_prompt = run_hook(
                self,
                {**self.payload("UserPromptSubmit", workspace, prompt="Status only, no changes."), "turn_id": "later"},
                state_root,
                profile,
            )
            self.assertIn("unresolved", later_prompt["hookSpecificOutput"]["additionalContext"].lower())
            later = run_cli(
                self,
                state_root,
                profile,
                "status",
                "--session-id",
                "session",
                "--turn-id",
                "later",
            )
            self.assertEqual(later["delivery_id"], first["delivery_id"])
            self.assertEqual(later["classification"], "material")
            stopped = run_hook(
                self,
                {**self.payload("Stop", workspace, last_assistant_message="Status reported."), "turn_id": "later"},
                state_root,
                profile,
            )
            self.assertEqual(stopped["decision"], "block")

            abandoned = run_cli(
                self,
                state_root,
                profile,
                "abort",
                "--session-id",
                "session",
                "--turn-id",
                "later",
                "--scope",
                "delivery",
                "--evidence",
                "operator explicitly abandoned this delivery",
            )
            self.assertEqual(abandoned["status"], "blocked")
            self.assertEqual(abandoned["blocked_origin"], "operator-abandon")
            new_turn = run_hook(
                self,
                {**self.payload("UserPromptSubmit", workspace, prompt="Read-only: show repository status."), "turn_id": "new"},
                state_root,
                profile,
            )
            self.assertIn("exempt", new_turn["hookSpecificOutput"]["additionalContext"].lower())

    def test_accepted_generation_rollover_recovers_every_injected_crash_window_monotonically(self) -> None:
        for fault in ("rollover_after_prepare", "rollover_after_old", "rollover_after_new", "rollover_after_pointer"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                state_root, profile, workspace = self.make_fixture(temporary)
                self.arm(state_root, profile, workspace)
                self.freeze(state_root, profile, workspace)
                generation_zero = self.start_reviewer(state_root, profile, workspace)
                finding = {
                    "id": "F-1",
                    "severity": "high",
                    "claim": "A defect remains.",
                    "evidence": [],
                    "correction": "Correct it.",
                    "verification": "Run the focused test.",
                }
                self.assertNotIn(
                    "decision",
                    self.stop_reviewer(
                        state_root,
                        profile,
                        workspace,
                        self.review_output(generation_zero, verdict="fail", findings=[finding]),
                    ),
                )
                self.rewrite_active_state_as_legacy(
                    state_root,
                    self.status(state_root, profile),
                )
                ledger_path = root / "ledger.json"
                ledger_path.write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "generation": 0,
                            "dispositions": [
                                {"finding_id": "F-1", "decision": "accepted", "new_generation": 1}
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                run_cli_with_fault(
                    self,
                    state_root,
                    profile,
                    fault,
                    "disposition",
                    "--session-id",
                    "session",
                    "--turn-id",
                    "turn",
                    "--file",
                    str(ledger_path),
                )
                recovered = self.status(state_root, profile)
                self.assertEqual(recovered["generation"], 1)
                self.assertEqual(recovered["status"], "stale")
                self.assertEqual(recovered["consumed_attempt_ids"], [generation_zero["attempt_id"]])
                self.assertIsNone(recovered["receipt"])
                again = self.status(state_root, profile)
                self.assertEqual(again, recovered)
                generations = {path.name for path in (state_root / "deliveries").rglob("generation-*.json")}
                self.assertEqual(generations, {"generation-0.json", "generation-1.json"})
                shutil.rmtree(lifecycle_gate._filesystem_path(state_root / "deliveries"))

    def test_freeze_builds_canonical_reviewable_bundle_and_start_binds_agent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_root, profile, workspace = self.make_fixture(temporary)
            self.arm(state_root, profile, workspace)
            state = self.freeze(state_root, profile, workspace)
            bundle = state_root / "bundles" / str(state["bundle_sha256"])
            manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(
                set(manifest),
                {
                    "snapshot.json",
                    "review-contract.json",
                    "review-lenses.md",
                    "review-packet.json",
                    "verification-evidence.json",
                    "verification/artifacts/lifecycle-fixture.stderr",
                    "verification/artifacts/lifecycle-fixture.stdout",
                    "verification/artifacts/synthetic-handler.evidence",
                    "evidence/base/owned.txt",
                    "evidence/head/owned.txt",
                    "evidence/index/owned.txt",
                    "evidence/worktree/owned.txt",
                },
            )
            self.assertEqual(
                (bundle / "evidence" / "worktree" / "owned.txt").read_bytes(),
                (workspace / "owned.txt").read_bytes(),
            )
            self.assertEqual(
                hashlib.sha256((bundle / "review-lenses.md").read_bytes()).hexdigest(),
                state["lens_sha256"],
            )
            started = run_hook(
                self,
                self.payload("SubagentStart", workspace, agent_id="reviewer-1", agent_type="sol_reviewer"),
                state_root,
                profile,
            )
            context = started["hookSpecificOutput"]["additionalContext"]
            self.assertIn(str(Path("state") / "bundles" / str(state["bundle_sha256"])), context)
            self.assertIn(str(state["attempt_id"]), context)
            rebound = self.status(state_root, profile)
            self.assertEqual(rebound["reviewer_agent"], "reviewer-1")

    def test_profile_missing_or_changed_fails_closed_at_start_stop_and_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_root, profile, workspace = self.make_fixture(temporary)
            self.arm(state_root, profile, workspace)
            self.freeze(state_root, profile, workspace)
            original = profile.read_bytes()
            profile.unlink()
            missing = run_hook(
                self,
                self.payload("SubagentStart", workspace, agent_id="reviewer-1", agent_type="sol_reviewer"),
                state_root,
                profile,
            )
            self.assertEqual(missing["decision"], "block")
            profile.write_bytes(original)
            state = self.start_reviewer(state_root, profile, workspace)
            profile.write_bytes(original + b"\n# changed\n")
            changed = self.stop_reviewer(state_root, profile, workspace, self.review_output(state))
            self.assertEqual(changed["decision"], "block")
            profile.write_bytes(original)
            accepted = self.stop_reviewer(state_root, profile, workspace, self.review_output(state))
            self.assertNotIn("decision", accepted)
            self.disposition(root, state_root, profile, {"schema_version": 1, "generation": 0, "dispositions": []})
            profile.write_bytes(original + b"\n# changed again\n")
            stopped = run_hook(
                self,
                self.payload("Stop", workspace, last_assistant_message="Delivered."),
                state_root,
                profile,
            )
            self.assertEqual(stopped["decision"], "block")

    def test_local_receipt_binds_actual_output_and_pending_then_final_disposition_digests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_root, profile, workspace = self.make_fixture(temporary)
            self.arm(state_root, profile, workspace)
            self.freeze(state_root, profile, workspace)
            state = self.start_reviewer(state_root, profile, workspace)
            output = self.review_output(state)
            accepted = self.stop_reviewer(state_root, profile, workspace, output)
            self.assertNotIn("decision", accepted)
            pending = self.status(state_root, profile)
            self.assertEqual(
                pending["receipt"]["output_sha256"],
                hashlib.sha256(lifecycle_gate.canonical_bytes(output)).hexdigest(),
            )
            self.assertEqual(pending["receipt"]["disposition_sha256"], pending["pending_disposition_sha256"])
            ledger = {"schema_version": 1, "generation": 0, "dispositions": []}
            final = self.disposition(root, state_root, profile, ledger)
            self.assertEqual(
                final["receipt"]["disposition_sha256"],
                hashlib.sha256(lifecycle_gate.canonical_bytes(ledger)).hexdigest(),
            )
            stopped = run_hook(self, self.payload("Stop", workspace, last_assistant_message="Delivered."), state_root, profile)
            self.assertNotIn("decision", stopped)
            second = run_hook(
                self,
                self.payload("Stop", workspace, last_assistant_message="Delivered.", stop_hook_active=True),
                state_root,
                profile,
            )
            self.assertNotIn("decision", second)

    def test_replay_across_agent_attempt_and_generation_is_rejected_and_acceptance_refreezes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_root, profile, workspace = self.make_fixture(temporary)
            self.arm(state_root, profile, workspace)
            self.freeze(state_root, profile, workspace)
            generation_zero = self.start_reviewer(state_root, profile, workspace, "reviewer-1")
            finding = {
                "id": "F-1",
                "severity": "high",
                "claim": "A defect remains.",
                "evidence": [],
                "correction": "Correct it.",
                "verification": "Run the focused test.",
            }
            output_zero = self.review_output(generation_zero, verdict="fail", findings=[finding])
            wrong_attempt = {**output_zero, "attempt_id": "not-the-frozen-attempt"}
            self.assertEqual(self.stop_reviewer(state_root, profile, workspace, wrong_attempt)["decision"], "block")
            self.assertNotIn("decision", self.stop_reviewer(state_root, profile, workspace, output_zero))
            accepted = self.disposition(
                root,
                state_root,
                profile,
                {
                    "schema_version": 1,
                    "generation": 0,
                    "dispositions": [{"finding_id": "F-1", "decision": "accepted", "new_generation": 1}],
                },
            )
            self.assertEqual(accepted["generation"], 1)
            self.assertEqual(accepted["status"], "stale")
            self.assertIsNone(accepted["receipt"])
            self.assertIsNone(accepted["review_output"])
            generations = {
                path.name
                for path in (state_root / "deliveries").rglob("generation-*.json")
            }
            self.assertEqual(generations, {"generation-0.json", "generation-1.json"})
            blocked = run_hook(self, self.payload("Stop", workspace, last_assistant_message="Done."), state_root, profile)
            self.assertEqual(blocked["decision"], "block")

            (workspace / "owned.txt").write_text("fixed\n", encoding="utf-8")
            generation_one = self.freeze(state_root, profile, workspace)
            self.assertEqual(generation_one["generation"], 1)
            self.assertNotEqual(generation_one["attempt_id"], generation_zero["attempt_id"])
            generation_one = self.start_reviewer(state_root, profile, workspace, "reviewer-2")
            replay = self.stop_reviewer(state_root, profile, workspace, output_zero, "reviewer-2")
            self.assertEqual(replay["decision"], "block")
            output_one = self.review_output(generation_one)
            wrong_agent = self.stop_reviewer(state_root, profile, workspace, output_one, "reviewer-1")
            self.assertEqual(wrong_agent["decision"], "block")
            self.assertNotIn("decision", self.stop_reviewer(state_root, profile, workspace, output_one, "reviewer-2"))
            replay_same = self.stop_reviewer(state_root, profile, workspace, output_one, "reviewer-2")
            self.assertEqual(replay_same["decision"], "block")

    def test_blocking_rejection_requires_primary_evidence_and_can_then_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_root, profile, workspace = self.make_fixture(temporary)
            self.arm(state_root, profile, workspace)
            self.freeze(state_root, profile, workspace)
            state = self.start_reviewer(state_root, profile, workspace)
            bundle = state_root / "bundles" / str(state["bundle_sha256"])
            manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
            evidence = {
                "kind": "bundle",
                "uri": f"bundle://{state['bundle_sha256']}/snapshot.json",
                "sha256": manifest["snapshot.json"],
                "selector": {"kind": "line_range", "start": 1, "end": 1},
            }
            finding = {
                "id": "F-1",
                "severity": "critical",
                "claim": "The review assumption is wrong.",
                "evidence": [evidence],
                "correction": "Change the assumption.",
                "verification": "Inspect the immutable snapshot.",
            }
            self.assertNotIn("decision", self.stop_reviewer(state_root, profile, workspace, self.review_output(state, verdict="fail", findings=[finding])))
            unsupported = {
                "schema_version": 1,
                "generation": 0,
                "dispositions": [{"finding_id": "F-1", "decision": "rejected", "primary_counterevidence": "trust me"}],
            }
            self.disposition(root, state_root, profile, unsupported, expected=2)
            self.assertEqual(
                run_hook(self, self.payload("Stop", workspace, last_assistant_message="Delivered."), state_root, profile)["decision"],
                "block",
            )
            supported = {
                "schema_version": 1,
                "generation": 0,
                "dispositions": [{"finding_id": "F-1", "decision": "rejected", "primary_counterevidence": [evidence]}],
            }
            self.disposition(root, state_root, profile, supported)
            self.assertNotIn(
                "decision",
                run_hook(self, self.payload("Stop", workspace, last_assistant_message="Delivered."), state_root, profile),
            )

    def test_blocking_rejection_counterevidence_is_resolved_before_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_root, profile, workspace = self.make_fixture(temporary)
            state, evidence = self.blocking_review(state_root, profile, workspace)

            invalid_counterevidence = {
                "foreign bundle": {
                    **evidence,
                    "uri": f"bundle://{'b' * 64}/snapshot.json",
                },
                "missing bundle path": {
                    **evidence,
                    "uri": f"bundle://{state['bundle_sha256']}/missing.txt",
                },
                "wrong raw digest": {**evidence, "sha256": "c" * 64},
                "missing selector": {
                    "kind": "bundle",
                    "uri": evidence["uri"],
                    "sha256": evidence["sha256"],
                },
                "absent selector": {
                    **evidence,
                    "selector": {"kind": "symbol", "value": "DefinitelyAbsent"},
                },
                "generic digest": {
                    "kind": "digest",
                    "uri": "https://example.com/source.txt",
                    "authority": {"kind": "archive", "source": "https://example.com/archive"},
                    "sha256": evidence["sha256"],
                },
                "opaque version": {
                    "kind": "opaque_version",
                    "uri": "https://example.com/source.txt",
                    "authority": {"kind": "archive", "source": "https://example.com/archive"},
                    "version": "release-1",
                    "immutable": True,
                },
            }
            for label, counterevidence in invalid_counterevidence.items():
                with self.subTest(label=label):
                    rejected = self.rejection_ledger(counterevidence)
                    result = self.disposition(root, state_root, profile, rejected, expected=2)
                    self.assertIn("counterevidence", result["detail"].casefold())
                    self.assertIsNone(self.status(state_root, profile)["ledger"])

            supported = self.rejection_ledger(evidence)
            persisted = self.disposition(root, state_root, profile, supported)
            self.assertEqual(persisted["ledger"], supported)

    def test_blocking_rejection_accepts_resolved_pinned_git_counterevidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_root, profile, workspace = self.make_fixture(temporary)
            repository = "https://example.com/acme/review-fixture.git"
            configured = run_process(["git", "remote", "add", "origin", repository], cwd=workspace)
            self.assertEqual(configured.returncode, 0, configured.stderr.decode())
            commit = run_process(["git", "rev-parse", "HEAD"], cwd=workspace)
            self.assertEqual(commit.returncode, 0, commit.stderr.decode())
            commit_id = commit.stdout.decode("ascii").strip()

            self.blocking_review(state_root, profile, workspace, severity="critical")
            counterevidence = {
                "kind": "git_commit",
                "repository": repository,
                "commit": commit_id,
                "path": "owned.txt",
                "sha256": hashlib.sha256(b"base\n").hexdigest(),
                "selector": {"kind": "line_range", "start": 1, "end": 1},
            }
            for label, invalid in {
                "repository mismatch": {
                    **counterevidence,
                    "repository": "https://example.com/acme/other.git",
                },
                "unavailable commit": {**counterevidence, "commit": "f" * 40},
                "raw digest mismatch": {**counterevidence, "sha256": "e" * 64},
                "absent selector": {
                    **counterevidence,
                    "selector": {"kind": "symbol", "value": "DefinitelyAbsent"},
                },
            }.items():
                with self.subTest(label=label):
                    invalid_ledger = self.rejection_ledger(invalid)
                    rejected = self.disposition(
                        root,
                        state_root,
                        profile,
                        invalid_ledger,
                        expected=2,
                    )
                    self.assertIn("counterevidence", rejected["detail"].casefold())
                    self.assertIsNone(self.status(state_root, profile)["ledger"])

            ledger = self.rejection_ledger(counterevidence)
            persisted = self.disposition(root, state_root, profile, ledger)
            self.assertEqual(persisted["ledger"], ledger)
            self.assertNotIn(
                "decision",
                run_hook(
                    self,
                    self.payload("Stop", workspace, last_assistant_message="Delivered."),
                    state_root,
                    profile,
                ),
            )
            exported = run_cli(
                self,
                state_root,
                profile,
                "export-replay",
                "--session-id",
                "session",
                "--turn-id",
                "turn",
            )
            self.assertEqual(exported["receipt"], persisted["receipt"])

    def test_final_stop_revalidates_tampered_persisted_counterevidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_root, profile, workspace = self.make_fixture(temporary)
            _, evidence = self.blocking_review(state_root, profile, workspace)
            valid_ledger = self.rejection_ledger(evidence)
            state = self.disposition(root, state_root, profile, valid_ledger)
            tampered_ledger = copy.deepcopy(valid_ledger)
            tampered_ledger["dispositions"][0]["primary_counterevidence"][0]["uri"] = (
                f"bundle://{'b' * 64}/snapshot.json"
            )
            disposition_sha = hashlib.sha256(lifecycle_gate.canonical_bytes(tampered_ledger)).hexdigest()
            state["ledger"] = tampered_ledger
            state["dispositions"] = disposition_sha
            state["receipt"]["disposition_sha256"] = disposition_sha
            lifecycle_gate.save_active(state_root, state)

            stopped = run_hook(
                self,
                self.payload("Stop", workspace, last_assistant_message="Delivered."),
                state_root,
                profile,
            )
            self.assertEqual(stopped["decision"], "block")
            self.assertIn("counterevidence", stopped["reason"].casefold())

    def test_export_replay_revalidates_tampered_persisted_counterevidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_root, profile, workspace = self.make_fixture(temporary)
            _, evidence = self.blocking_review(
                state_root,
                profile,
                workspace,
                severity="critical",
            )
            valid_ledger = self.rejection_ledger(evidence)
            state = self.disposition(root, state_root, profile, valid_ledger)
            tampered_ledger = copy.deepcopy(valid_ledger)
            tampered_ledger["dispositions"][0]["primary_counterevidence"] = [{
                "kind": "digest",
                "uri": "https://example.com/source.txt",
                "authority": {"kind": "archive", "source": "https://example.com/archive"},
                "sha256": "d" * 64,
            }]
            disposition_sha = hashlib.sha256(lifecycle_gate.canonical_bytes(tampered_ledger)).hexdigest()
            state["ledger"] = tampered_ledger
            state["dispositions"] = disposition_sha
            state["receipt"]["disposition_sha256"] = disposition_sha
            lifecycle_gate.save_active(state_root, state)

            exported = run_cli(
                self,
                state_root,
                profile,
                "export-replay",
                "--session-id",
                "session",
                "--turn-id",
                "turn",
                expected=2,
            )
            self.assertIn("counterevidence", exported["detail"].casefold())

    def test_concurrent_post_reviewer_stop_and_stop_do_not_lose_epochs_or_accept_stale_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_root, profile, workspace = self.make_fixture(temporary)
            receipt = self.empty_receipt(root, state_root, profile, workspace)
            output = receipt["review_output"]
            tool_payloads = [
                self.payload(
                    "PostToolUse",
                    workspace,
                    tool_name="apply_patch",
                    tool_use_id=f"concurrent-{index}",
                    tool_input={},
                )
                for index in range(12)
            ]
            for payload in tool_payloads:
                run_hook(self, {**payload, "hook_event_name": "PreToolUse"}, state_root, profile)

            calls = [
                lambda payload=payload: run_hook(self, payload, state_root, profile)
                for payload in tool_payloads
            ]
            calls.extend(
                [
                    lambda: self.stop_reviewer(state_root, profile, workspace, output),
                    lambda: run_hook(
                        self,
                        self.payload("Stop", workspace, last_assistant_message="Delivered.", stop_hook_active=True),
                        state_root,
                        profile,
                    ),
                ]
            )
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(calls)) as executor:
                results = list(executor.map(lambda call: call(), calls))
            self.assertEqual(results[-1]["decision"], "block")
            self.assertEqual(results[-2]["decision"], "block")
            stale = self.status(state_root, profile)
            self.assertEqual(stale["mutation_epoch"], 12)
            self.assertEqual(stale["status"], "stale")
            self.assertIsNone(stale["receipt"])
            self.assertEqual(stale["inflight_tool_use_ids"], [])

    def test_current_snapshot_change_and_both_incomplete_stops_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_root, profile, workspace = self.make_fixture(temporary)
            self.empty_receipt(root, state_root, profile, workspace)
            (workspace / "owned.txt").write_text("out-of-band\n", encoding="utf-8")
            for active in (False, True):
                stopped = run_hook(
                    self,
                    self.payload("Stop", workspace, last_assistant_message="Delivered.", stop_hook_active=active),
                    state_root,
                    profile,
                )
                self.assertEqual(stopped["decision"], "block")

    def test_blocked_reviewer_needs_persisted_evidence_and_only_incomplete_marker_exits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_root, profile, workspace = self.make_fixture(temporary)
            self.arm(state_root, profile, workspace)
            self.freeze(state_root, profile, workspace)
            state = self.start_reviewer(state_root, profile, workspace)
            unsupported = self.stop_reviewer(
                state_root,
                profile,
                workspace,
                self.review_output(state, verdict="blocked"),
            )
            self.assertEqual(unsupported["decision"], "block")
            evidenced = self.stop_reviewer(
                state_root,
                profile,
                workspace,
                self.review_output(state, verdict="blocked", risks=["Repository authority is unavailable."]),
            )
            self.assertEqual(evidenced["decision"], "block")
            persisted = self.status(state_root, profile)
            self.assertEqual(persisted["status"], "blocked")
            self.assertRegex(persisted["blocked_evidence_sha256"], r"^[0-9a-f]{64}$")
            for message in (
                "Delivered successfully.",
                "Blocked by infrastructure.",
                "[adversarial-review-blocked] Incomplete, but completed successfully.",
            ):
                self.assertEqual(
                    run_hook(self, self.payload("Stop", workspace, last_assistant_message=message), state_root, profile)["decision"],
                    "block",
                )
            allowed = run_hook(
                self,
                self.payload(
                    "Stop",
                    workspace,
                    last_assistant_message="[adversarial-review-blocked] Incomplete: repository authority remains unavailable.",
                ),
                state_root,
                profile,
            )
            self.assertNotIn("decision", allowed)
            self.assertIn("not completed", allowed["hookSpecificOutput"]["additionalContext"])
            later = run_hook(
                self,
                {
                    **self.payload("UserPromptSubmit", workspace, prompt="Read-only: report status."),
                    "turn_id": "later",
                },
                state_root,
                profile,
            )
            self.assertIn("unresolved", later["hookSpecificOutput"]["additionalContext"].lower())
            self.assertNotIn("gate exempt:", later["hookSpecificOutput"]["additionalContext"].lower())

    def test_explicit_infrastructure_block_requires_evidence_and_incomplete_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_root, profile, workspace = self.make_fixture(temporary)
            self.arm(state_root, profile, workspace)
            run_cli(
                self,
                state_root,
                profile,
                "block",
                "--session-id",
                "session",
                "--turn-id",
                "turn",
                "--evidence",
                "immutable repository authority is unavailable",
            )
            self.assertEqual(
                run_hook(self, self.payload("Stop", workspace, last_assistant_message="Done."), state_root, profile)["decision"],
                "block",
            )
            allowed = run_hook(
                self,
                self.payload(
                    "Stop",
                    workspace,
                    last_assistant_message="[adversarial-review-blocked] Incomplete: immutable repository authority is unavailable.",
                ),
                state_root,
                profile,
            )
            self.assertNotIn("decision", allowed)


if __name__ == "__main__":
    unittest.main()

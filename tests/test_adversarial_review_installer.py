"""Behavioral tests for the one-way adversarial-review installer."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "skills" / "adversarial-code-review" / "scripts" / "install_review_gate.py"
MANAGED_MARKER = "adversarial-code-review"
INSTALLER_SPEC = importlib.util.spec_from_file_location("adversarial_review_installer", INSTALLER)
assert INSTALLER_SPEC is not None and INSTALLER_SPEC.loader is not None
installer_module = importlib.util.module_from_spec(INSTALLER_SPEC)
INSTALLER_SPEC.loader.exec_module(installer_module)


class InstallerTests(unittest.TestCase):
    def invoke(
        self,
        *args: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(INSTALLER), *args],
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, **(env or {})},
        )

    def make_home(self, root: Path) -> Path:
        home = root / "home"
        home.mkdir()
        (home / "config.toml").write_text(
            'model = "x"\n[agents]\nmax_depth = 2\n',
            encoding="utf-8",
            newline="\r\n",
        )
        hooks = {
            "trustedHandlerHashes": {"keep-handler": "keep-hash"},
            "localMetadata": {"keep": True},
            "hooks": {
                "Stop": [{"matcher": "^unrelated$", "hooks": [{"type": "command", "command": "keep", "trust": "keep"}]}],
                "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "keep-prompt"}]}],
            },
        }
        (home / "hooks.json").write_text(json.dumps(hooks, indent=2), encoding="utf-8")
        (home / "AGENTS.md").write_bytes(b"# local\r\nkeep this\r\n")
        return home

    def make_current_main_home(self, root: Path) -> Path:
        """Model the current six-profile installation before adding the gate."""
        home = root / "current-main-home"
        (home / "agents").mkdir(parents=True)
        for name in (
            "spark_scanner",
            "spark_worker",
            "luna_scanner",
            "luna_worker",
            "sol_worker",
            "sol_advisor",
        ):
            shutil.copy2(ROOT / "agents" / f"{name}.toml", home / "agents" / f"{name}.toml")
        routing_test = home / "skills" / "delivery-orchestration" / "scripts" / "test_routing_policy.py"
        routing_test.parent.mkdir(parents=True)
        routing_test.write_text(
            'raise SystemExit("stale six-profile validator")\n',
            encoding="utf-8",
        )
        (routing_test.parent / "local-validator-helper.py").write_text(
            "# preserve adjacent user-owned helper\n",
            encoding="utf-8",
        )
        plan_root = home / "skills" / "plan-review-ladder"
        for relative in (
            "SKILL.md",
            "agents/openai.yaml",
            "references/review-lenses.md",
            "scripts/packet_integrity.py",
            "scripts/test_packet_integrity.py",
            "scripts/test_plan_routing.py",
        ):
            target = plan_root.joinpath(*relative.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"# stale current-main {relative}\n", encoding="utf-8")
        (plan_root / "scripts" / "local-plan-helper.py").write_text(
            "# preserve adjacent user-owned plan helper\n",
            encoding="utf-8",
        )

        text = (ROOT / "config.toml").read_text(encoding="utf-8")
        prefix, segments = installer_module._table_segments(text)
        kept = [
            segment.rstrip("\r\n")
            for header, segment in segments
            if header != "[agents.sol_reviewer]"
            and not (
                header == "[[skills.config]]"
                and "./skills/adversarial-code-review/SKILL.md" in segment
            )
        ]
        (home / "config.toml").write_text(
            "\n\n".join([prefix.rstrip("\r\n"), *kept]).rstrip() + "\n",
            encoding="utf-8",
        )
        hooks = json.loads((ROOT / "hooks.json").read_text(encoding="utf-8"))
        for event, entries in hooks["hooks"].items():
            preserved = [installer_module._remove_gate_handlers(entry) for entry in entries]
            hooks["hooks"][event] = [entry for entry in preserved if entry is not None]
        (home / "hooks.json").write_text(json.dumps(hooks, indent=2), encoding="utf-8")
        (home / "AGENTS.md").write_text(
            "# existing global agreements\n"
            "- Use only the six configured custom profiles.\n",
            encoding="utf-8",
        )
        return home

    def install(self, home: Path, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return self.invoke("install", "--source-root", str(ROOT), "--codex-home", str(home), env=env)

    def recovery_fixture(self, root: Path) -> tuple[Path, str, Path, dict[str, bytes]]:
        home = root / "recovery-home"
        managed = home / "managed"
        managed.mkdir(parents=True)
        preimages = {
            "managed/a.txt": b"old-a\n",
            "managed/b.txt": b"old-b\n",
        }
        for relative, data in preimages.items():
            (home / relative).write_bytes(data)
        transaction_id = "a" * 32
        writes = {
            "managed/a.txt": b"new-a\n",
            "managed/b.txt": b"new-b\n",
            "managed/new.txt": b"created\n",
        }
        with installer_module._install_lock(home):
            transaction = installer_module._prepare_transaction(home, transaction_id, writes, set())
        return home, transaction_id, transaction, writes

    def update_journal(self, transaction: Path, **updates: object) -> dict[str, object]:
        journal_path = transaction / "journal.json"
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        journal.update(updates)
        if journal.get("schema_version") == 2:
            home = transaction.parents[1]
            identities: dict[str, object] = {}
            for relative in journal.get("applied", []):
                metadata = installer_module._lstat(home / relative)
                identities[relative] = installer_module._leaf_identity(metadata) if metadata is not None else None
            journal["postimage_identities"] = identities
        installer_module._atomic_json(journal_path, journal)
        return journal

    def test_runtime_bytecode_is_nontransactional_and_legacy_cache_drift_does_not_block_install(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = self.make_home(Path(temporary))
            relative = "skills/adversarial-code-review/scripts/__pycache__/legacy.pyc"
            cache = home / relative
            cache.parent.mkdir(parents=True)
            cache.write_bytes(b"generated-runtime-cache")

            self.assertNotIn(relative, installer_module._managed_extras(home))

            transaction_id = "f" * 32
            with installer_module._install_lock(home):
                transaction = installer_module._prepare_transaction(
                    home,
                    transaction_id,
                    {},
                    {relative},
                )
            _, manifest, journal = installer_module._validated_transaction(home, transaction_id)
            cache.unlink()
            self.update_journal(
                transaction,
                status="completed",
                applied=sorted(manifest["paths"]),
                next_path=None,
            )

            backup = transaction / "backup" / relative
            backup.write_bytes(b"rewritten-generated-runtime-cache")
            with self.assertRaisesRegex(ValueError, "backup authentication failed"):
                installer_module._validated_transaction(home, transaction_id)
            self.assertEqual(installer_module._active_completed_head(home), transaction_id)

            result = self.install(home)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_prepared_recovery_does_not_rewrite_untouched_preimages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home, transaction_id, transaction, _ = self.recovery_fixture(Path(temporary))
            a = home / "managed/a.txt"
            b = home / "managed/b.txt"
            old_timestamp = 1_700_000_000_000_000_000
            os.utime(a, ns=(old_timestamp, old_timestamp))
            os.utime(b, ns=(old_timestamp, old_timestamp))

            with installer_module._install_lock(home):
                recovered = installer_module._recover_incomplete(home)

            self.assertEqual(recovered, [transaction_id])
            self.assertEqual(a.stat().st_mtime_ns, old_timestamp)
            self.assertEqual(b.stat().st_mtime_ns, old_timestamp)
            self.assertFalse((home / "managed/new.txt").exists())
            journal = json.loads((transaction / "journal.json").read_text(encoding="utf-8"))
            self.assertEqual(journal["status"], "rolled_back")
            self.assertEqual(journal["applied"], [])
            self.assertIsNone(journal["next_path"])

    def test_schema_v1_prepared_journal_remains_recoverable(self) -> None:
        """Bumping leaf-identity metadata must not strand predecessor journals."""
        with tempfile.TemporaryDirectory() as temporary:
            home, transaction_id, transaction, _ = self.recovery_fixture(Path(temporary))
            manifest_path = transaction / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["schema_version"] = 1
            for record in manifest["paths"].values():
                record.pop("identity")
            manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
            installer_module._atomic_write(manifest_path, manifest_bytes)
            journal_path = transaction / "journal.json"
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            journal["schema_version"] = 1
            journal["manifest_sha256"] = installer_module.sha(manifest_bytes)
            journal.pop("postimage_identities")
            installer_module._atomic_json(journal_path, journal)

            with installer_module._install_lock(home):
                recovered = installer_module._recover_incomplete(home)

            self.assertEqual(recovered, [transaction_id])
            self.assertEqual(
                json.loads(journal_path.read_text(encoding="utf-8"))["status"],
                "rolled_back",
            )

    def test_recovery_accepts_before_and_after_replace_next_path_states(self) -> None:
        for replaced in (False, True):
            with self.subTest(replaced=replaced), tempfile.TemporaryDirectory() as temporary:
                home, transaction_id, transaction, writes = self.recovery_fixture(Path(temporary))
                a = home / "managed/a.txt"
                b = home / "managed/b.txt"
                old_timestamp = 1_700_000_000_000_000_000
                os.utime(b, ns=(old_timestamp, old_timestamp))
                self.update_journal(transaction, status="applying", next_path="managed/a.txt")
                if replaced:
                    a.write_bytes(writes["managed/a.txt"])

                with installer_module._install_lock(home):
                    recovered = installer_module._recover_incomplete(home)

                self.assertEqual(recovered, [transaction_id])
                self.assertEqual(a.read_bytes(), b"old-a\n")
                self.assertEqual(b.stat().st_mtime_ns, old_timestamp)
                self.assertFalse((home / "managed/new.txt").exists())
                journal = json.loads((transaction / "journal.json").read_text(encoding="utf-8"))
                self.assertEqual(journal["status"], "rolled_back")
                self.assertEqual(journal["applied"], [])
                self.assertIsNone(journal["next_path"])

    def test_incomplete_recovery_refuses_untouched_and_potentially_applied_drift_atomically(self) -> None:
        for drifted in ("managed/a.txt", "managed/new.txt"):
            with self.subTest(drifted=drifted), tempfile.TemporaryDirectory() as temporary:
                home, transaction_id, transaction, writes = self.recovery_fixture(Path(temporary))
                self.update_journal(
                    transaction,
                    status="applying",
                    applied=["managed/a.txt"],
                    next_path="managed/b.txt",
                )
                (home / "managed/a.txt").write_bytes(writes["managed/a.txt"])
                (home / "managed/b.txt").write_bytes(writes["managed/b.txt"])
                drift_target = home / drifted
                drift_target.write_bytes(b"third-party-drift\n")
                before = {
                    relative: (home / relative).read_bytes() if (home / relative).is_file() else None
                    for relative in writes
                }
                journal_before = (transaction / "journal.json").read_bytes()

                with self.assertRaisesRegex(ValueError, "drift"):
                    with installer_module._install_lock(home):
                        installer_module._recover_incomplete(home)

                after = {
                    relative: (home / relative).read_bytes() if (home / relative).is_file() else None
                    for relative in writes
                }
                self.assertEqual(after, before)
                self.assertEqual((transaction / "journal.json").read_bytes(), journal_before)

    def test_mid_rollback_progress_is_restartable_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home, transaction_id, transaction, writes = self.recovery_fixture(Path(temporary))
            self.update_journal(
                transaction,
                status="applying",
                applied=["managed/a.txt", "managed/b.txt"],
                next_path="managed/new.txt",
            )
            for relative, data in writes.items():
                (home / relative).write_bytes(data)

            original_atomic_json = installer_module._atomic_json
            interrupted = False

            def interrupt_after_first_progress(path: Path, value: dict[str, object]) -> None:
                nonlocal interrupted
                original_atomic_json(path, value)
                if (
                    not interrupted
                    and path == transaction / "journal.json"
                    and value.get("status") == "rolling_back"
                    and value.get("next_path") is None
                    and len(value.get("applied", [])) == 2
                ):
                    interrupted = True
                    raise RuntimeError("simulated rollback crash")

            installer_module._atomic_json = interrupt_after_first_progress
            try:
                with self.assertRaisesRegex(RuntimeError, "simulated rollback crash"):
                    installer_module._rollback_transaction(home, transaction_id, acquire=True)
            finally:
                installer_module._atomic_json = original_atomic_json

            interrupted_journal = json.loads((transaction / "journal.json").read_text(encoding="utf-8"))
            self.assertEqual(interrupted_journal["status"], "rolling_back")
            self.assertEqual(interrupted_journal["applied"], ["managed/a.txt", "managed/b.txt"])
            self.assertFalse((home / "managed/new.txt").exists())
            self.assertEqual((home / "managed/a.txt").read_bytes(), writes["managed/a.txt"])
            self.assertEqual((home / "managed/b.txt").read_bytes(), writes["managed/b.txt"])

            with installer_module._install_lock(home):
                self.assertEqual(installer_module._recover_incomplete(home), [transaction_id])
                self.assertEqual(installer_module._recover_incomplete(home), [])

            self.assertEqual((home / "managed/a.txt").read_bytes(), b"old-a\n")
            self.assertEqual((home / "managed/b.txt").read_bytes(), b"old-b\n")
            self.assertFalse((home / "managed/new.txt").exists())
            final_journal = json.loads((transaction / "journal.json").read_text(encoding="utf-8"))
            self.assertEqual(final_journal["status"], "rolled_back")
            self.assertEqual(final_journal["applied"], [])
            self.assertIsNone(final_journal["next_path"])

    def test_preview_install_verify_idempotent_stateful_smoke_and_rollback(self) -> None:
        """Removing real lifecycle execution or raw rollback must fail this test."""
        with tempfile.TemporaryDirectory() as temporary:
            home = self.make_home(Path(temporary))
            original = {name: (home / name).read_bytes() for name in ("config.toml", "hooks.json", "AGENTS.md")}

            preview = self.invoke("preview", "--source-root", str(ROOT), "--codex-home", str(home))
            self.assertEqual(preview.returncode, 0, preview.stderr)
            preview_data = json.loads(preview.stdout)
            self.assertTrue(preview_data["copy"])
            self.assertEqual(preview_data["semantic"], ["AGENTS.md", "config.toml", "hooks.json"])

            installed = self.install(home)
            self.assertEqual(installed.returncode, 0, installed.stderr)
            receipt = json.loads(installed.stdout)
            self.assertIsNone(receipt["handler_contract_smoke"])
            self.assertIn("No adversarial lifecycle hooks are registered", receipt["next"])
            self.assertNotIn("approve changed handlers", receipt["next"])
            self.assertNotIn("live provenance smoke", receipt["next"])
            transaction = home / ".adversarial-review-install" / receipt["transaction_id"]
            self.assertTrue((transaction / "manifest.json").is_file())
            self.assertEqual(json.loads((transaction / "journal.json").read_text(encoding="utf-8"))["status"], "completed")

            verified = self.invoke("verify", "--source-root", str(ROOT), "--codex-home", str(home))
            self.assertEqual(verified.returncode, 0, verified.stderr)
            verified_data = json.loads(verified.stdout)
            self.assertTrue(verified_data["ok"])
            self.assertIsNone(verified_data["handler_contract_smoke"])

            smoke = self.invoke("smoke", "--source-root", str(ROOT), "--codex-home", str(home))
            self.assertEqual(smoke.returncode, 0, smoke.stderr)
            smoke_data = json.loads(smoke.stdout)
            self.assertTrue(smoke_data["ok"])
            self.assertTrue(smoke_data["wrong_profile_rejected"])
            self.assertTrue(smoke_data["copied_output_rejected"])
            self.assertTrue(smoke_data["replayed_output_rejected"])
            self.assertTrue(smoke_data["correct_profile_provenance"])
            self.assertTrue(smoke_data["final_stop_accepted"])
            self.assertTrue(smoke_data["prompt_pending_classification"])
            self.assertTrue(smoke_data["managed_mutation_reserved"])
            self.assertTrue(smoke_data["managed_mutation_recorded_once"])
            self.assertEqual(smoke_data["fixture_observations"]["mutation_epoch_before"], 0)
            self.assertEqual(smoke_data["fixture_observations"]["mutation_epoch_after"], 1)
            self.assertEqual(smoke_data["fixture_observations"]["inflight_after_pre"], ["fixture-mutation-1"])
            self.assertEqual(smoke_data["fixture_observations"]["inflight_after_post"], [])
            self.assertEqual(
                smoke_data["events"],
                ["UserPromptSubmit", "PreToolUse", "PostToolUse", "SubagentStart", "SubagentStop", "Stop"],
            )

            again = self.install(home)
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertTrue(json.loads(again.stdout)["idempotent"])

            rolled_back = self.invoke(
                "rollback", "--codex-home", str(home), "--transaction-id", receipt["transaction_id"]
            )
            self.assertEqual(rolled_back.returncode, 0, rolled_back.stderr)
            for name, data in original.items():
                self.assertEqual((home / name).read_bytes(), data)

    def test_install_verify_and_explicit_smoke_do_not_recreate_managed_bytecode(self) -> None:
        """Package operations must not write runtime cache into managed roots."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = self.make_home(root)
            installed = self.install(home)
            self.assertEqual(installed.returncode, 0, installed.stderr)
            verified = self.invoke("verify", "--source-root", str(ROOT), "--codex-home", str(home))
            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
            smoked = self.invoke("smoke", "--source-root", str(ROOT), "--codex-home", str(home))
            self.assertEqual(smoked.returncode, 0, smoked.stdout + smoked.stderr)

            managed_root = home / "skills" / "adversarial-code-review"
            runtime_leaves = sorted(
                path.relative_to(home).as_posix()
                for path in managed_root.rglob("*")
                if path.name == "__pycache__" or path.suffix == ".pyc"
            )
            self.assertEqual(runtime_leaves, [])
            again = self.install(home)
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertTrue(json.loads(again.stdout)["idempotent"])

    def test_config_merge_preserves_header_like_multiline_strings_comments_and_unmanaged_values(self) -> None:
        """Treating header-looking string content as TOML structure must fail."""
        original_text = (
            'model = "x"\r\n'
            'description = """Structural-looking basic string lines:\r\n'
            'escaped delimiter \\""" remains part of the value\r\n'
            '[agents.sol_reviewer]\r\n'
            'description = "not a table"\r\n'
            '[[skills.config]]\r\n'
            'path = "./skills/adversarial-code-review/SKILL.md"\r\n'
            '"""\r\n'
            "literal = '''Structural-looking literal string lines:\r\n"
            "[agents.sol_reviewer]\r\n"
            "[[skills.config]]\r\n"
            "path = './skills/adversarial-code-review/SKILL.md'\r\n"
            "'''\r\n"
            'same_line_basic = """same-line close before a real header"""\r\n'
            "same_line_literal = '''same-line literal close before a real header'''\r\n"
            '# [agents.sol_reviewer]\r\n'
            '# [[skills.config]]\r\n'
            '[agents]\r\n'
            'max_depth = 2\r\n'
            '[agents.sol_reviewer]\r\n'
            'description = "stale reviewer"\r\n'
            'config_file = "./agents/stale.toml"\r\n'
            '[[skills.config]]\r\n'
            'path = "./skills/unrelated/SKILL.md"\r\n'
            'description = "Mentions ./skills/adversarial-code-review/SKILL.md as inert text"\r\n'
            '# ./skills/adversarial-code-review/SKILL.md is not this entry path\r\n'
            '[[skills.config]]\r\n'
            'path = "./skills/adversarial-code-review/SKILL.md"\r\n'
            'enabled = false\r\n'
            '[unmanaged] # preserve trailing header comment\r\n'
            'answer = 42\r\n'
            '# [agents.sol_reviewer]\r\n'
            '# [[skills.config]]\r\n'
        )
        preserved_prefix = original_text.split('[agents]\r\n', 1)[0]
        preserved_suffix = (
            '[unmanaged] # preserve trailing header comment\r\n'
            'answer = 42\r\n'
            '# [agents.sol_reviewer]\r\n'
            '# [[skills.config]]\r\n'
        )
        before = tomllib.loads(original_text)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = self.make_home(root)
            (home / "config.toml").write_bytes(original_text.encode("utf-8"))

            result = self.install(home)

            self.assertEqual(result.returncode, 0, result.stderr)
            installed_bytes = (home / "config.toml").read_bytes()
            installed_text = installed_bytes.decode("utf-8")
            after = tomllib.loads(installed_text)
            self.assertTrue(installed_text.startswith(preserved_prefix))
            self.assertIn(preserved_suffix, installed_text)
            self.assertEqual(after["description"], before["description"])
            self.assertEqual(after["literal"], before["literal"])
            self.assertEqual(after["same_line_basic"], before["same_line_basic"])
            self.assertEqual(after["same_line_literal"], before["same_line_literal"])
            self.assertEqual(after["agents"]["max_depth"], before["agents"]["max_depth"])
            self.assertEqual(after["unmanaged"], before["unmanaged"])
            self.assertEqual(after["agents"]["sol_reviewer"]["config_file"], "./agents/sol_reviewer.toml")
            self.assertIn(
                {
                    "path": "./skills/unrelated/SKILL.md",
                    "description": "Mentions ./skills/adversarial-code-review/SKILL.md as inert text",
                },
                after["skills"]["config"],
            )
            self.assertEqual(
                [entry for entry in after["skills"]["config"] if entry.get("path") == "./skills/adversarial-code-review/SKILL.md"],
                [{"path": "./skills/adversarial-code-review/SKILL.md", "enabled": True}],
            )

            again = self.install(home)
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertTrue(json.loads(again.stdout)["idempotent"])
            self.assertEqual((home / "config.toml").read_bytes(), installed_bytes)

            transaction_id = json.loads(result.stdout)["transaction_id"]
            rolled_back = self.invoke(
                "rollback", "--codex-home", str(home), "--transaction-id", transaction_id
            )
            self.assertEqual(rolled_back.returncode, 0, rolled_back.stderr)
            self.assertEqual((home / "config.toml").read_bytes(), original_text.encode("utf-8"))

        with tempfile.TemporaryDirectory() as temporary:
            home = self.make_home(Path(temporary))
            (home / "config.toml").write_bytes(original_text.encode("utf-8"))

            failed = self.install(home, env={"CODEX_ADVERSARIAL_INSTALL_FAIL_STEP": "validators"})

            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual((home / "config.toml").read_bytes(), original_text.encode("utf-8"))

    def test_apply_rejects_a_same_content_leaf_identity_swap_before_live_writes(self) -> None:
        """Digest-only preparation must not overwrite a replaced managed leaf."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = self.make_home(root)
            originals = {name: (home / name).read_bytes() for name in ("config.toml", "hooks.json", "AGENTS.md")}
            target = home / "config.toml"
            original_identity = (target.stat().st_dev, target.stat().st_ino)
            original_validated_transaction = installer_module._validated_transaction
            swapped = False

            def swap_after_preparation(
                candidate_home: Path,
                transaction_id: str,
            ) -> tuple[Path, dict[str, object], dict[str, object]]:
                nonlocal swapped
                transaction, manifest, journal = original_validated_transaction(candidate_home, transaction_id)
                if not swapped and journal["status"] == "prepared":
                    replacement = root / "same-content-config.toml"
                    replacement.write_bytes(target.read_bytes())
                    os.replace(replacement, target)
                    swapped = True
                return transaction, manifest, journal

            installer_module._validated_transaction = swap_after_preparation
            try:
                with self.assertRaisesRegex(ValueError, "identity changed"):
                    installer_module.install(ROOT, home)
            finally:
                installer_module._validated_transaction = original_validated_transaction

            self.assertTrue(swapped)
            self.assertNotEqual((target.stat().st_dev, target.stat().st_ino), original_identity)
            for name, data in originals.items():
                self.assertEqual((home / name).read_bytes(), data)

    @unittest.skipIf(os.name == "nt", "POSIX symlink behavior")
    def test_preview_and_install_reject_managed_leaf_symlinks_before_creating_state(self) -> None:
        """Following existing or broken managed leaf symlinks must fail."""
        for case in ("semantic", "copied", "broken"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                home = self.make_home(root)
                if case == "semantic":
                    target = home / "config.toml"
                    outside = root / "outside-config.toml"
                    outside.write_bytes(target.read_bytes())
                    target.unlink()
                    target.symlink_to(outside)
                else:
                    target = home / "agents" / "sol_reviewer.toml"
                    target.parent.mkdir()
                    outside = root / ("missing-profile.toml" if case == "broken" else "outside-profile.toml")
                    if case == "copied":
                        outside.write_text("outside profile\n", encoding="utf-8")
                    target.symlink_to(outside)
                outside_before = outside.read_bytes() if outside.exists() else None

                preview = self.invoke("preview", "--source-root", str(ROOT), "--codex-home", str(home))
                installed = self.install(home)

                for result in (preview, installed):
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("symlink or reparse", (result.stdout + result.stderr).lower())
                self.assertFalse((home / ".adversarial-review-install").exists())
                self.assertTrue(target.is_symlink())
                self.assertEqual(outside.read_bytes() if outside.exists() else None, outside_before)

    @unittest.skipIf(os.name == "nt", "POSIX symlink behavior")
    def test_apply_revalidates_leaf_topology_and_rollback_refuses_a_reparse_postimage(self) -> None:
        """A link swap after preparation or before rollback must never be replaced."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = self.make_home(root)
            originals = {name: (home / name).read_bytes() for name in ("config.toml", "hooks.json", "AGENTS.md")}
            target = home / "agents" / "sol_reviewer.toml"
            outside = root / "outside-profile.toml"
            outside.write_text("outside profile\n", encoding="utf-8")
            original_validated_transaction = installer_module._validated_transaction
            swapped = False

            def swap_after_preparation(
                candidate_home: Path,
                transaction_id: str,
            ) -> tuple[Path, dict[str, object], dict[str, object]]:
                nonlocal swapped
                transaction, manifest, journal = original_validated_transaction(candidate_home, transaction_id)
                if not swapped and journal["status"] == "prepared":
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.symlink_to(outside)
                    swapped = True
                return transaction, manifest, journal

            installer_module._validated_transaction = swap_after_preparation
            try:
                with self.assertRaises(ValueError):
                    installer_module.install(ROOT, home)
            finally:
                installer_module._validated_transaction = original_validated_transaction

            self.assertTrue(swapped)
            self.assertTrue(target.is_symlink())
            self.assertEqual(outside.read_bytes(), b"outside profile\n")
            for name, data in originals.items():
                self.assertEqual((home / name).read_bytes(), data)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = self.make_home(root)
            result = self.install(home)
            self.assertEqual(result.returncode, 0, result.stderr)
            transaction_id = json.loads(result.stdout)["transaction_id"]
            target = home / "agents" / "sol_reviewer.toml"
            outside = root / "outside-postimage.toml"
            outside.write_bytes(target.read_bytes())
            target.unlink()
            target.symlink_to(outside)

            rolled_back = self.invoke(
                "rollback", "--codex-home", str(home), "--transaction-id", transaction_id
            )

            self.assertNotEqual(rolled_back.returncode, 0)
            self.assertIn("symlink or reparse", (rolled_back.stdout + rolled_back.stderr).lower())
            self.assertTrue(target.is_symlink())
            self.assertEqual(outside.read_bytes(), (ROOT / "agents" / "sol_reviewer.toml").read_bytes())

    @unittest.skipUnless(os.name == "nt", "Windows junction and reparse behavior")
    def test_preview_and_install_reject_managed_leaf_junctions_before_state(self) -> None:
        """Windows reparse-point leaves must survive every rejected operation."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = self.make_home(root)
            outside = root / "outside-directory"
            outside.mkdir()
            sentinel = outside / "sentinel.txt"
            sentinel.write_text("outside\n", encoding="utf-8")
            target = home / "agents" / "sol_reviewer.toml"
            target.parent.mkdir()
            created = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(target), str(outside)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(created.returncode, 0, created.stderr)
            self.assertTrue(
                int(getattr(os.lstat(target), "st_file_attributes", 0))
                & int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
            )
            self.assertTrue(installer_module._is_reparse(target))

            preview = self.invoke("preview", "--source-root", str(ROOT), "--codex-home", str(home))
            installed = self.install(home)

            for result in (preview, installed):
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("symlink or reparse", (result.stdout + result.stderr).lower())
            self.assertFalse((home / ".adversarial-review-install").exists())
            self.assertTrue(installer_module._is_reparse(target))
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "outside\n")
            os.rmdir(target)

    @unittest.skipUnless(os.name == "nt", "Windows reparse attribute behavior")
    def test_generic_windows_reparse_attribute_is_rejected_without_a_junction_hint(self) -> None:
        """Dropping FILE_ATTRIBUTE_REPARSE_POINT inspection must fail."""
        class ReparseMetadata:
            st_mode = stat.S_IFREG
            st_file_attributes = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))

        original_lstat = installer_module._lstat
        installer_module._lstat = lambda path: ReparseMetadata()
        try:
            self.assertTrue(installer_module._is_reparse(Path("ordinary-looking-leaf")))
        finally:
            installer_module._lstat = original_lstat

    @unittest.skipUnless(os.name == "nt", "Windows junction and reparse behavior")
    def test_apply_revalidates_a_windows_junction_swap_before_live_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = self.make_home(root)
            originals = {name: (home / name).read_bytes() for name in ("config.toml", "hooks.json", "AGENTS.md")}
            outside = root / "swap-outside"
            outside.mkdir()
            sentinel = outside / "sentinel.txt"
            sentinel.write_text("outside\n", encoding="utf-8")
            target = home / "agents" / "sol_reviewer.toml"
            original_validated_transaction = installer_module._validated_transaction
            swapped = False

            def swap_to_junction_after_preparation(
                candidate_home: Path,
                transaction_id: str,
            ) -> tuple[Path, dict[str, object], dict[str, object]]:
                nonlocal swapped
                transaction, manifest, journal = original_validated_transaction(candidate_home, transaction_id)
                if not swapped and journal["status"] == "prepared":
                    target.parent.mkdir(parents=True, exist_ok=True)
                    created = subprocess.run(
                        ["cmd", "/c", "mklink", "/J", str(target), str(outside)],
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    if created.returncode != 0:
                        raise RuntimeError(created.stderr)
                    swapped = True
                return transaction, manifest, journal

            installer_module._validated_transaction = swap_to_junction_after_preparation
            try:
                with self.assertRaises(ValueError):
                    installer_module.install(ROOT, home)
            finally:
                installer_module._validated_transaction = original_validated_transaction

            self.assertTrue(swapped)
            self.assertTrue(installer_module._is_reparse(target))
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "outside\n")
            for name, data in originals.items():
                self.assertEqual((home / name).read_bytes(), data)
            os.rmdir(target)

    @unittest.skipUnless(os.name == "nt", "Windows junction and reparse behavior")
    def test_rollback_rejects_a_windows_junction_postimage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = self.make_home(root)
            result = self.install(home)
            self.assertEqual(result.returncode, 0, result.stderr)
            transaction_id = json.loads(result.stdout)["transaction_id"]
            target = home / "agents" / "sol_reviewer.toml"
            target.unlink()
            outside = root / "rollback-outside"
            outside.mkdir()
            sentinel = outside / "sentinel.txt"
            sentinel.write_text("outside\n", encoding="utf-8")
            created = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(target), str(outside)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(created.returncode, 0, created.stderr)

            rolled_back = self.invoke(
                "rollback", "--codex-home", str(home), "--transaction-id", transaction_id
            )

            self.assertNotEqual(rolled_back.returncode, 0)
            self.assertIn("symlink or reparse", (rolled_back.stdout + rolled_back.stderr).lower())
            self.assertTrue(installer_module._is_reparse(target))
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "outside\n")
            os.rmdir(target)

    @unittest.skipUnless(os.name == "nt", "Windows file symlink behavior")
    def test_windows_file_symlinks_and_broken_links_are_rejected_before_state(self) -> None:
        for broken in (False, True):
            with self.subTest(broken=broken), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                home = self.make_home(root)
                target = home / "agents" / "sol_reviewer.toml"
                target.parent.mkdir()
                outside = root / ("missing-profile.toml" if broken else "outside-profile.toml")
                if not broken:
                    outside.write_text("outside profile\n", encoding="utf-8")
                created = subprocess.run(
                    ["cmd", "/c", "mklink", str(target), str(outside)],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                if created.returncode != 0:
                    self.skipTest(f"Windows file symlink creation unavailable: {created.stderr.strip()}")
                outside_before = outside.read_bytes() if outside.exists() else None

                preview = self.invoke("preview", "--source-root", str(ROOT), "--codex-home", str(home))
                installed = self.install(home)

                for result in (preview, installed):
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("symlink or reparse", (result.stdout + result.stderr).lower())
                self.assertFalse((home / ".adversarial-review-install").exists())
                self.assertTrue(target.is_symlink())
                self.assertEqual(outside.read_bytes() if outside.exists() else None, outside_before)
                target.unlink()

    def test_completed_rollback_refuses_legacy_script_with_composite_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = self.make_home(Path(temporary))
            legacy_gate = home / installer_module.LIFECYCLE_GATE_PATH
            legacy_gate.parent.mkdir(parents=True)
            legacy_gate.write_text(
                "def delivery_path(root, state):\n"
                "    if False:\n"
                "        return root / 'deliveries' / delivery_address_sha256(\n"
                "            state['session_id'], state['task_id'], state['delivery_id']\n"
                "        ) / f\"generation-{state['generation']}.json\"\n"
                "    return root / 'deliveries' / 'legacy'\n",
                encoding="utf-8",
            )
            installed = self.install(home)
            self.assertEqual(installed.returncode, 0, installed.stderr)
            transaction_id = json.loads(installed.stdout)["transaction_id"]
            composite_state = (
                home
                / "hooks"
                / "state"
                / "adversarial-review"
                / "deliveries"
                / ("a" * 64)
                / "generation-0.json"
            )
            composite_state.parent.mkdir(parents=True)
            composite_state.write_text("{}\n", encoding="utf-8")

            refused = self.invoke(
                "rollback",
                "--codex-home",
                str(home),
                "--transaction-id",
                transaction_id,
            )

            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("composite lifecycle state", (refused.stdout + refused.stderr).lower())
            transaction = home / ".adversarial-review-install" / transaction_id
            self.assertEqual(
                json.loads((transaction / "journal.json").read_text(encoding="utf-8"))["status"],
                "completed",
            )
            self.assertTrue(
                (
                    home
                    / "skills"
                    / "adversarial-code-review"
                    / "scripts"
                    / "lifecycle_gate.py"
                ).is_file()
            )
            shutil.rmtree(home / "hooks" / "state")
            rolled_back = self.invoke(
                "rollback",
                "--codex-home",
                str(home),
                "--transaction-id",
                transaction_id,
            )
            self.assertEqual(rolled_back.returncode, 0, rolled_back.stderr)

    def test_completed_rollback_accepts_structurally_compatible_predecessor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = self.make_home(Path(temporary))
            compatible_gate = home / installer_module.LIFECYCLE_GATE_PATH
            compatible_gate.parent.mkdir(parents=True)
            compatible_gate.write_text(
                "import hashlib\n"
                "import json\n"
                "DELIVERY_ADDRESSING = 'composite-v1'\n"
                "def delivery_address_sha256(session_id, task_id, delivery_id):\n"
                "    identity = {\n"
                "        'delivery_sha256': hashlib.sha256(delivery_id.encode()).hexdigest(),\n"
                "        'session_sha256': hashlib.sha256(session_id.encode()).hexdigest(),\n"
                "        'task_sha256': hashlib.sha256(task_id.encode()).hexdigest(),\n"
                "    }\n"
                "    return hashlib.sha256(json.dumps(\n"
                "        identity, sort_keys=True, separators=(',', ':')\n"
                "    ).encode()).hexdigest()\n"
                "def delivery_path(root, state):\n"
                "    return root / 'deliveries' / delivery_address_sha256(\n"
                "        state['session_id'], state['task_id'], state['delivery_id']\n"
                "    ) / f\"generation-{state['generation']}.json\"\n",
                encoding="utf-8",
            )
            installed = self.install(home)
            self.assertEqual(installed.returncode, 0, installed.stderr)
            transaction_id = json.loads(installed.stdout)["transaction_id"]
            composite_state = (
                home
                / "hooks"
                / "state"
                / "adversarial-review"
                / "deliveries"
                / ("b" * 64)
                / "generation-0.json"
            )
            composite_state.parent.mkdir(parents=True)
            composite_state.write_text("{}\n", encoding="utf-8")

            rolled_back = self.invoke(
                "rollback",
                "--codex-home",
                str(home),
                "--transaction-id",
                transaction_id,
            )

            self.assertEqual(rolled_back.returncode, 0, rolled_back.stderr)
            self.assertEqual(
                compatible_gate.read_text(encoding="utf-8"),
                "import hashlib\n"
                "import json\n"
                "DELIVERY_ADDRESSING = 'composite-v1'\n"
                "def delivery_address_sha256(session_id, task_id, delivery_id):\n"
                "    identity = {\n"
                "        'delivery_sha256': hashlib.sha256(delivery_id.encode()).hexdigest(),\n"
                "        'session_sha256': hashlib.sha256(session_id.encode()).hexdigest(),\n"
                "        'task_sha256': hashlib.sha256(task_id.encode()).hexdigest(),\n"
                "    }\n"
                "    return hashlib.sha256(json.dumps(\n"
                "        identity, sort_keys=True, separators=(',', ':')\n"
                "    ).encode()).hexdigest()\n"
                "def delivery_path(root, state):\n"
                "    return root / 'deliveries' / delivery_address_sha256(\n"
                "        state['session_id'], state['task_id'], state['delivery_id']\n"
                "    ) / f\"generation-{state['generation']}.json\"\n",
            )
            spec = importlib.util.spec_from_file_location("rolled_back_compatible_gate", compatible_gate)
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            compatible_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(compatible_module)
            state = {
                "session_id": "session",
                "task_id": "task",
                "delivery_id": "delivery",
                "generation": 2,
            }
            identity = {
                "delivery_sha256": hashlib.sha256(b"delivery").hexdigest(),
                "session_sha256": hashlib.sha256(b"session").hexdigest(),
                "task_sha256": hashlib.sha256(b"task").hexdigest(),
            }
            expected_address = hashlib.sha256(
                json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            self.assertEqual(
                compatible_module.delivery_path(Path("root"), state),
                Path("root") / "deliveries" / expected_address / "generation-2.json",
            )

    @unittest.skipUnless(os.name == "nt", "Windows extended-path behavior")
    def test_completed_rollback_discovers_long_override_state_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = self.make_home(root)
            installed = self.install(home)
            self.assertEqual(installed.returncode, 0, installed.stderr)
            transaction_id = json.loads(installed.stdout)["transaction_id"]
            long_state_top = root / ("state-a-" + "a" * 110) / ("state-b-" + "b" * 110)
            state_root = long_state_top / "state"
            composite_state = (
                state_root
                / "deliveries"
                / ("c" * 64)
                / "generation-0.json"
            )
            extended_state = Path("\\\\?\\" + os.path.abspath(composite_state))
            extended_state.parent.mkdir(parents=True)
            extended_state.write_text("{}\n", encoding="utf-8")
            self.assertGreater(len(str(state_root)), 260)

            refused = self.invoke(
                "rollback",
                "--codex-home",
                str(home),
                "--transaction-id",
                transaction_id,
                env={"CODEX_ADVERSARIAL_STATE": str(state_root)},
            )

            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("composite lifecycle state", (refused.stdout + refused.stderr).lower())
            shutil.rmtree(Path("\\\\?\\" + os.path.abspath(long_state_top)))

    def test_install_rolls_back_when_plan_review_skill_metadata_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            shutil.copytree(
                ROOT,
                source,
                ignore=shutil.ignore_patterns(".git", "__pycache__", ".superpowers", "tmp"),
            )
            plan_skill = source / "skills" / "plan-review-ladder" / "SKILL.md"
            plan_skill.write_text(
                plan_skill.read_text(encoding="utf-8").replace(
                    "name: plan-review-ladder",
                    "name: wrong-plan-review-ladder",
                    1,
                ),
                encoding="utf-8",
            )
            home = self.make_home(root)
            originals = {
                name: (home / name).read_bytes()
                for name in ("config.toml", "hooks.json", "AGENTS.md")
            }

            result = self.invoke(
                "install",
                "--source-root",
                str(source),
                "--codex-home",
                str(home),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("plan-review-ladder", (result.stdout + result.stderr).lower())
            for name, data in originals.items():
                self.assertEqual((home / name).read_bytes(), data)
            self.assertFalse((home / "agents" / "sol_reviewer.toml").exists())

    def test_install_preserves_current_main_routing_and_adjacent_hooks(self) -> None:
        """The gate must add one identity without rewriting the six-profile router."""
        with tempfile.TemporaryDirectory() as temporary:
            home = self.make_current_main_home(Path(temporary))
            before = tomllib.loads((home / "config.toml").read_text(encoding="utf-8"))
            hooks_before = (home / "hooks.json").read_text(encoding="utf-8")
            routing_test = home / "skills" / "delivery-orchestration" / "scripts" / "test_routing_policy.py"
            adjacent = routing_test.parent / "local-validator-helper.py"
            adjacent_before = adjacent.read_bytes()
            plan_root = home / "skills" / "plan-review-ladder"
            plan_adjacent = plan_root / "scripts" / "local-plan-helper.py"
            plan_adjacent_before = plan_adjacent.read_bytes()

            result = self.install(home)
            self.assertEqual(result.returncode, 0, result.stderr)
            after = tomllib.loads((home / "config.toml").read_text(encoding="utf-8"))

            for key in (
                "max_depth",
                "max_concurrent_threads_per_session",
                "default_subagent_model",
                "default_subagent_reasoning_effort",
            ):
                self.assertEqual(after["agents"][key], before["agents"][key])
            for name in (
                "spark_scanner",
                "spark_worker",
                "luna_scanner",
                "luna_worker",
                "sol_worker",
                "sol_advisor",
            ):
                self.assertEqual(after["agents"][name], before["agents"][name])
            self.assertEqual(after["agents"]["luna_scanner"]["config_file"], "./agents/luna_scanner.toml")
            with (home / "agents" / "luna_scanner.toml").open("rb") as stream:
                self.assertEqual(tomllib.load(stream)["model_reasoning_effort"], "medium")
            self.assertIn("sol_reviewer", after["agents"])
            self.assertEqual(
                after["agents"]["sol_reviewer"]["description"],
                "On-demand read-only Sol reviewer for root-prepared consequential delivery evidence packets.",
            )
            installed_agents = (home / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("Use only the six configured custom profiles.", installed_agents)
            self.assertIn(
                "The six-profile limit applies only to general-purpose routing",
                installed_agents,
            )
            self.assertEqual(
                routing_test.read_bytes(),
                (ROOT / "skills" / "delivery-orchestration" / "scripts" / "test_routing_policy.py").read_bytes(),
            )
            validation = subprocess.run(
                [sys.executable, "-B", str(routing_test)],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "CODEX_ROUTING_HOME": str(home)},
            )
            self.assertEqual(validation.returncode, 0, validation.stderr)
            self.assertEqual(adjacent.read_bytes(), adjacent_before)
            plan_paths = (
                "SKILL.md",
                "agents/openai.yaml",
                "references/review-lenses.md",
                "scripts/packet_integrity.py",
                "scripts/test_packet_integrity.py",
                "scripts/test_plan_routing.py",
            )
            for relative in plan_paths:
                with self.subTest(plan_path=relative):
                    self.assertEqual(
                        plan_root.joinpath(*relative.split("/")).read_bytes(),
                        (ROOT / "skills" / "plan-review-ladder").joinpath(*relative.split("/")).read_bytes(),
                    )
            for validator_name in ("test_plan_routing.py", "test_packet_integrity.py"):
                validator = plan_root / "scripts" / validator_name
                validation = subprocess.run(
                    [sys.executable, "-B", str(validator)],
                    cwd=validator.parent,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(validation.returncode, 0, validation.stderr)
            self.assertEqual(plan_adjacent.read_bytes(), plan_adjacent_before)

            hooks_after = (home / "hooks.json").read_text(encoding="utf-8")
            for marker in ("plan_gap_goal_hook.py", "instruction_learning_hook.py"):
                self.assertIn(marker, hooks_before)
                self.assertIn(marker, hooks_after)

            again = self.install(home)
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertTrue(json.loads(again.stdout)["idempotent"])

    def test_reinstall_preserves_adjacent_handlers_in_a_shared_managed_group(self) -> None:
        existing = (ROOT / "hooks.json").read_bytes()
        merged = installer_module.hooks_text(existing, ROOT).decode("utf-8")
        for marker in ("plan_gap_goal_hook.py", "instruction_learning_hook.py"):
            self.assertIn(marker, merged)
        self.assertNotIn("lifecycle_gate.py", merged)

    def test_payload_is_exact_production_allowlist_with_one_canonical_packet_helper(self) -> None:
        """Copying tests or a second packet helper must fail this test."""
        with tempfile.TemporaryDirectory() as temporary:
            home = self.make_home(Path(temporary))
            result = self.install(home)
            self.assertEqual(result.returncode, 0, result.stderr)
            expected = set(json.loads(result.stdout)["installed_files"])
            actual = {
                path.relative_to(home).as_posix()
                for root in (
                    home / "skills" / "adversarial-code-review",
                    home / "skills" / "delivery-orchestration",
                    home / "skills" / "plan-review-ladder",
                )
                for path in root.rglob("*")
                if path.is_file()
            }
            expected_managed = {path for path in expected if path.startswith("skills/")}
            self.assertEqual(actual, expected_managed)
            self.assertEqual(
                sorted(path for path in expected if Path(path).name.startswith("test_")),
                [
                    "skills/delivery-orchestration/scripts/test_routing_policy.py",
                    "skills/plan-review-ladder/scripts/test_packet_integrity.py",
                    "skills/plan-review-ladder/scripts/test_plan_routing.py",
                ],
            )
            self.assertEqual(
                [path for path in expected if Path(path).name == "packet_integrity.py"],
                ["skills/plan-review-ladder/scripts/packet_integrity.py"],
            )
            self.assertFalse((home / "skills" / "adversarial-code-review" / "scripts" / "packet_integrity.py").exists())
            self.assertIn(
                "skills/adversarial-code-review/references/evaluation-self-test-results.json",
                expected,
            )
            self.assertIn(
                "skills/adversarial-code-review/references/evaluation-git-identities.json",
                expected,
            )
            self.assertIn(
                "skills/adversarial-code-review/references/evaluation-inputs/python-shell-boundary-corrected.py.txt",
                expected,
            )
            self.assertIn(
                "skills/adversarial-code-review/references/evaluation-replay-workflow.md",
                expected,
            )

    def test_skill_routes_only_consequential_review_and_keeps_low_risk_work_direct(self) -> None:
        """Forward-use guidance must expose the risk boundary and lightweight packet."""
        skill = (ROOT / "skills" / "adversarial-code-review" / "SKILL.md").read_text(encoding="utf-8")
        normalized_skill = " ".join(skill.split())
        contracts = (ROOT / "skills" / "adversarial-code-review" / "references" / "contracts.md").read_text(encoding="utf-8")
        for phrase in (
            "consequential delivery",
            "`AGENTS.md` wording",
            "reversible startup-setting changes",
            "root-prepared evidence packet",
            "Optional review infrastructure",
            "Only a required high-risk review failure blocks delivery",
        ):
            self.assertIn(phrase, normalized_skill)
        self.assertIn("](../scripts/review_contracts.py)", contracts)
        self.assertIn("Strict pass example", contracts)
        self.assertIn("Strict finding example", contracts)
        self.assertIn('"schema_version": 1', contracts)
        workflow = (ROOT / "skills" / "adversarial-code-review" / "references" / "evaluation-replay-workflow.md").read_text(encoding="utf-8")
        for phrase in (
            "freeze the case",
            "Dispatch `sol_reviewer`",
            "export-replay",
            "Capture stdout unchanged",
            "Do not hand-create or edit",
            "--lifecycle-state-root",
            "--claim-empirical-quality",
            "local administrator",
        ):
            self.assertIn(phrase, workflow)
        self.assertIn("one-to-one semantic correspondence", contracts)

    def test_hook_merge_replaces_only_managed_entries_and_preserves_trust_data(self) -> None:
        """Importing adjacent hooks or retaining stale handlers must fail this test."""
        with tempfile.TemporaryDirectory() as temporary:
            home = self.make_home(Path(temporary))
            destination = json.loads((home / "hooks.json").read_text(encoding="utf-8"))
            destination["hooks"]["PreToolUse"] = [
                {"matcher": "^old$", "hooks": [{"type": "command", "command": "old adversarial-code-review lifecycle_gate.py"}]},
                {"matcher": "^keep$", "hooks": [{"type": "command", "command": "keep-pre"}]},
            ]
            (home / "hooks.json").write_text(json.dumps(destination, indent=3), encoding="utf-8")

            result = self.install(home)
            self.assertEqual(result.returncode, 0, result.stderr)
            installed = json.loads((home / "hooks.json").read_text(encoding="utf-8"))
            self.assertEqual(installed["trustedHandlerHashes"], {"keep-handler": "keep-hash"})
            self.assertEqual(installed["localMetadata"], {"keep": True})
            serialized = json.dumps(installed)
            self.assertIn("keep-prompt", serialized)
            self.assertIn("keep-pre", serialized)
            self.assertIn('"trust": "keep"', serialized)
            self.assertNotIn("plan_gap_goal_hook", serialized)
            self.assertNotIn("instruction_learning_hook", serialized)
            self.assertNotIn("old adversarial-code-review", serialized)
            self.assertNotIn("lifecycle_gate.py", serialized)

    def test_semantic_corruption_fails_verify(self) -> None:
        """Fail-open semantic comparisons must fail this test."""
        mutators = {
            "config-agent": lambda home: (home / "config.toml").write_text(
                (home / "config.toml").read_text(encoding="utf-8").replace(
                    './agents/sol_reviewer.toml', './agents/wrong.toml'
                ), encoding="utf-8"
            ),
            "config-skill": lambda home: (home / "config.toml").write_text(
                (home / "config.toml").read_text(encoding="utf-8").replace(
                    './skills/adversarial-code-review/SKILL.md', './skills/wrong/SKILL.md'
                ), encoding="utf-8"
            ),
            "profile-purpose": lambda home: (home / "agents" / "sol_reviewer.toml").write_text(
                (home / "agents" / "sol_reviewer.toml").read_text(encoding="utf-8").replace(
                    "Review only the root-prepared evidence packet", "Review the mutable workspace"
                ), encoding="utf-8"
            ),
            "managed-block": lambda home: (home / "AGENTS.md").write_text(
                (home / "AGENTS.md").read_text(encoding="utf-8").replace(
                    "Only a required high-risk review failure",
                    "Every review failure blocks delivery",
                ), encoding="utf-8"
            ),
        }
        for name, mutate in mutators.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                home = self.make_home(Path(temporary))
                result = self.install(home)
                self.assertEqual(result.returncode, 0, result.stderr)
                mutate(home)
                verified = self.invoke("verify", "--source-root", str(ROOT), "--codex-home", str(home))
                self.assertNotEqual(verified.returncode, 0, verified.stdout)
                self.assertFalse(json.loads(verified.stdout)["ok"])

    def test_install_rolls_back_on_replacement_and_validator_failures(self) -> None:
        """Any post-journal failure leaving partial live bytes must fail this test."""
        for failure in ("replace:2", "validators"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                home = self.make_home(Path(temporary))
                originals = {name: (home / name).read_bytes() for name in ("config.toml", "hooks.json", "AGENTS.md")}
                result = self.install(home, env={"CODEX_ADVERSARIAL_INSTALL_FAIL_STEP": failure})
                self.assertNotEqual(result.returncode, 0)
                for name, data in originals.items():
                    self.assertEqual((home / name).read_bytes(), data)
                self.assertFalse((home / "agents" / "sol_reviewer.toml").exists())

    def test_lifecycle_regression_fails_explicit_smoke_without_blocking_routine_install(self) -> None:
        """Optional lifecycle evaluation must not gate the non-lifecycle package install."""
        mutations = {
            "prompt": ('return "pending", None', 'return "exempt", "automatic: injected regression"'),
            "epoch": (
                'state["mutation_epoch"] += 1\n                changed = True',
                'state["mutation_epoch"] += 0\n                changed = True',
            ),
        }
        for name, (before, after) in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = root / "source"
                shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", "__pycache__", ".superpowers", "tmp"))
                gate = source / "skills" / "adversarial-code-review" / "scripts" / "lifecycle_gate.py"
                text = gate.read_text(encoding="utf-8")
                self.assertIn(before, text)
                gate.write_text(text.replace(before, after, 1), encoding="utf-8")
                home = self.make_home(root)
                installed = self.invoke("install", "--source-root", str(source), "--codex-home", str(home))
                self.assertEqual(installed.returncode, 0, installed.stderr)
                self.assertIsNone(json.loads(installed.stdout)["handler_contract_smoke"])

                verified = self.invoke("verify", "--source-root", str(source), "--codex-home", str(home))
                self.assertEqual(verified.returncode, 0, verified.stderr)
                self.assertTrue(json.loads(verified.stdout)["ok"])

                explicit_smoke = self.invoke("smoke", "--source-root", str(source), "--codex-home", str(home))
                self.assertNotEqual(explicit_smoke.returncode, 0, explicit_smoke.stdout)

    def test_next_install_recovers_an_interrupted_journal_before_applying(self) -> None:
        """Ignoring a prepared/applying recovery journal must fail this test."""
        with tempfile.TemporaryDirectory() as temporary:
            home = self.make_home(Path(temporary))
            transaction_id = "b" * 32
            with installer_module._install_lock(home):
                transaction = installer_module._prepare_transaction(
                    home,
                    transaction_id,
                    {"AGENTS.md": b"partially replaced\n"},
                    set(),
                )
            journal_path = transaction / "journal.json"
            self.update_journal(transaction, status="applying", next_path="AGENTS.md")
            (home / "AGENTS.md").write_bytes(b"partially replaced\n")
            pending = self.invoke("verify", "--source-root", str(ROOT), "--codex-home", str(home))
            self.assertNotEqual(pending.returncode, 0)
            self.assertIn("recovery-journal", pending.stdout)

            recovered = self.install(home)
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            self.assertIn(transaction_id, json.loads(recovered.stdout)["recovered"])
            self.assertEqual(json.loads(journal_path.read_text(encoding="utf-8"))["status"], "rolled_back")
            self.assertEqual(
                self.invoke("verify", "--source-root", str(ROOT), "--codex-home", str(home)).returncode,
                0,
            )

    def test_explicit_completed_rollback_refuses_live_drift_and_a_later_install(self) -> None:
        """Historical rollback must never overwrite user edits or a newer completed install."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = self.make_home(root)
            first = self.install(home)
            self.assertEqual(first.returncode, 0, first.stderr)
            first_id = json.loads(first.stdout)["transaction_id"]

            user_edit = home / "skills" / "adversarial-code-review" / "references" / "contracts.md"
            user_edit.write_text(user_edit.read_text(encoding="utf-8") + "\nuser-owned drift\n", encoding="utf-8")
            drifted = self.invoke("rollback", "--codex-home", str(home), "--transaction-id", first_id)
            self.assertNotEqual(drifted.returncode, 0)
            self.assertIn("drift", (drifted.stdout + drifted.stderr).lower())
            self.assertTrue(user_edit.read_text(encoding="utf-8").endswith("user-owned drift\n"))

            # Restore the exact first postimage, then make a genuinely newer install.
            user_edit.write_bytes((ROOT / user_edit.relative_to(home)).read_bytes())
            source = root / "source-newer"
            shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", "__pycache__", ".superpowers", "tmp"))
            newer_contract = source / user_edit.relative_to(home)
            newer_contract.write_text(newer_contract.read_text(encoding="utf-8") + "\nnewer package revision\n", encoding="utf-8")
            second = self.invoke("install", "--source-root", str(source), "--codex-home", str(home))
            self.assertEqual(second.returncode, 0, second.stderr)
            second_id = json.loads(second.stdout)["transaction_id"]
            self.assertNotEqual(first_id, second_id)

            historical = self.invoke("rollback", "--codex-home", str(home), "--transaction-id", first_id)
            self.assertNotEqual(historical.returncode, 0)
            self.assertIn("later", (historical.stdout + historical.stderr).lower())
            self.assertTrue(user_edit.read_text(encoding="utf-8").endswith("newer package revision\n"))

    @unittest.skipUnless(os.name == "nt", "Windows ACL behavior")
    def test_transaction_backup_and_staging_leaves_have_private_recursive_acls(self) -> None:
        """Relying on chmod instead of a recursive Windows ACL must fail."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = self.make_home(root)
            result = self.install(home)
            self.assertEqual(result.returncode, 0, result.stderr)
            transaction = home / ".adversarial-review-install" / json.loads(result.stdout)["transaction_id"]
            leaves = [
                transaction / "backup" / "AGENTS.md",
                transaction / "staging" / "agents" / "sol_reviewer.toml",
                transaction / "journal.json",
            ]
            identity = subprocess.run(
                ["whoami", "/user", "/fo", "csv", "/nh"], text=True, capture_output=True, check=False
            )
            self.assertEqual(identity.returncode, 0, identity.stderr)
            current_user_sid = next(csv.reader([identity.stdout.strip()]))[1]
            for index, leaf in enumerate(leaves):
                with self.subTest(leaf=leaf.relative_to(transaction)):
                    acl_path = root / f"transaction-{index}.acl"
                    saved = subprocess.run(
                        ["icacls", str(leaf), "/save", str(acl_path), "/c"],
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(saved.returncode, 0, saved.stderr)
                    sddl = acl_path.read_text(encoding="utf-16-le")
                    self.assertNotIn(";;;BU)", sddl)
                    self.assertNotIn(";;;WD)", sddl)
                    self.assertNotIn(";;;AU)", sddl)
                    self.assertIn(current_user_sid, sddl)
                    self.assertIn(";;;SY)", sddl)
                    self.assertIn(";;;BA)", sddl)

    def test_rejects_overlap_runtime_source_symlink_and_unsafe_rollback(self) -> None:
        """Lexical or resolved path escape and unauthenticated rollback must fail this test."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = self.make_home(root)
            overlap = self.invoke("preview", "--source-root", str(home), "--codex-home", str(home))
            self.assertNotEqual(overlap.returncode, 0)

            source = root / "source"
            shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", "__pycache__", ".superpowers", "tmp"))
            (source / "skills" / "adversarial-code-review" / "state").mkdir()
            runtime = self.invoke("preview", "--source-root", str(source), "--codex-home", str(home))
            self.assertNotEqual(runtime.returncode, 0)

            traversal = self.invoke("rollback", "--codex-home", str(home), "--transaction-id", "../escape")
            self.assertNotEqual(traversal.returncode, 0)

            installed = self.install(home)
            self.assertEqual(installed.returncode, 0, installed.stderr)
            transaction_id = json.loads(installed.stdout)["transaction_id"]
            manifest_path = home / ".adversarial-review-install" / transaction_id / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            backed_up = next(path for path, record in manifest["paths"].items() if record["present"])
            manifest["paths"][backed_up]["sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            corrupt = self.invoke("rollback", "--codex-home", str(home), "--transaction-id", transaction_id)
            self.assertNotEqual(corrupt.returncode, 0)

            link_source = root / "link-source"
            try:
                link_source.symlink_to(ROOT, target_is_directory=True)
            except OSError:
                pass
            else:
                linked = self.invoke("preview", "--source-root", str(link_source), "--codex-home", str(home))
                self.assertNotEqual(linked.returncode, 0)

            outside = root / "outside"
            outside.mkdir()
            linked_parent = root / "linked-parent"
            linked_parent.mkdir()
            linked_home = self.make_home(linked_parent)
            skills_link = linked_home / "skills"
            try:
                skills_link.symlink_to(outside, target_is_directory=True)
            except OSError:
                pass
            else:
                escaped = self.install(linked_home)
                self.assertNotEqual(escaped.returncode, 0)


if __name__ == "__main__":
    unittest.main()

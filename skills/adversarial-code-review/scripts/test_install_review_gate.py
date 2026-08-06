from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


INSTALLER = Path(__file__).with_name("install_review_gate.py")
SPEC = importlib.util.spec_from_file_location("install_review_gate_under_test", INSTALLER)
assert SPEC and SPEC.loader
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallerRoutingBoundaryTests(unittest.TestCase):
    def test_preview_and_install_preserve_routing_skill_files_byte_for_byte(self) -> None:
        """Catches an installer manifest that owns/copies routing skill files."""
        self_test = "skills/adversarial-code-review/scripts/test_install_review_gate.py"
        self.assertIn(self_test, installer.COPY_MANIFEST, "test file must be in copy manifest")
        self.assertIn(
            self_test,
            installer.PRODUCTION_REVIEW_PATHS,
            "test file must be in review manifest",
        )
        source_home = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory(prefix="codex-installer-sentinel-") as temp:
            root = Path(temp)
            source = root / "source"
            home = root / "home"
            source.mkdir()
            home.mkdir()

            for relative in installer.COPY_MANIFEST:
                source_path = source_home / relative
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source_path.read_bytes())
            for relative in ("config.toml", "hooks.json", "AGENTS.md"):
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((source_home / relative).read_bytes())
                destination = home / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(target.read_bytes())

            sentinels = {
                "skills/delivery-orchestration/SKILL.md": b"delivery-sentinel\n",
                "skills/delivery-orchestration/references/delegation-topology.md": b"topology-sentinel\n",
                "skills/plan-review-ladder/SKILL.md": b"plan-sentinel\n",
                "skills/plan-review-ladder/scripts/packet_integrity.py": b"packet-sentinel\n",
            }
            stale_paths = {
                path: b"stale-sentinel\n"
                for path in installer.STALE_MANAGED_FILES
            }
            duplicate = home / "skills/adversarial-code-review/scripts/packet_integrity.py"
            duplicate.parent.mkdir(parents=True, exist_ok=True)
            duplicate.write_bytes(b"obsolete-duplicate\n")
            for relative, data in sentinels.items():
                target = home / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            for relative, data in stale_paths.items():
                target = home / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            expected_self_test = (source / self_test).read_bytes()
            installer.validate_source(source)
            foreign_test = source / "skills/adversarial-code-review/scripts/test_foreign_reject.py"
            foreign_test.parent.mkdir(parents=True, exist_ok=True)
            foreign_test.write_bytes(b"print('reject me')\n")
            try:
                with self.assertRaises(ValueError) as error:
                    installer.validate_source(source)
                self.assertIn("non-production source rejected", str(error.exception))
            finally:
                foreign_test.unlink()
            installer.validate_source(source)

            destination_foreign = home / "skills/adversarial-code-review/scripts/test_foreign_reject.py"
            destination_foreign_payload = b"import pathlib\nassert False\n"
            destination_foreign.parent.mkdir(parents=True, exist_ok=True)
            destination_foreign.write_bytes(destination_foreign_payload)
            try:
                with self.assertRaises(ValueError) as error:
                    installer.preview(source, home)
                self.assertIn("unowned file exists inside managed destination", str(error.exception))
                self.assertEqual(destination_foreign.read_bytes(), destination_foreign_payload)
                with self.assertRaises(ValueError) as error:
                    installer.install(source, home)
                self.assertIn("unowned file exists inside managed destination", str(error.exception))
                self.assertEqual(destination_foreign.read_bytes(), destination_foreign_payload)
            finally:
                destination_foreign.unlink()

            preview = installer.preview(source, home)
            for relative in sentinels:
                self.assertNotIn(relative, preview["delete"])
            self.assertNotIn(self_test, preview["delete"])
            for relative in sentinels:
                self.assertNotIn(relative, preview["copy"])
            for relative in stale_paths:
                self.assertIn(relative, preview["delete"])
            self.assertIn(
                "skills/adversarial-code-review/scripts/packet_integrity.py",
                preview["delete"],
            )

            first_install = installer.install(source, home)
            self.assertFalse(first_install["idempotent"])
            for relative, expected in sentinels.items():
                self.assertEqual((home / relative).read_bytes(), expected, relative)
            self.assertEqual((home / self_test).read_bytes(), expected_self_test, self_test)
            verification = installer.verify(source, home)
            self.assertTrue(verification["ok"], verification.get("failures"))

            second_install = installer.install(source, home)
            self.assertTrue(second_install["idempotent"])
            self.assertTrue(second_install["unchanged"])
            self.assertNotEqual(second_install["installed_files"], [])
            for relative, expected in sentinels.items():
                self.assertEqual((home / relative).read_bytes(), expected, relative)
            self.assertFalse(duplicate.exists())


if __name__ == "__main__":
    unittest.main()

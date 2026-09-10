#!/usr/bin/env python3

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import audit_instruction_system as audit


def run_audit(args, env):
    old_env = os.environ.copy()
    os.environ.update(env)
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = audit.main(args)
        return code, buf.getvalue()
    finally:
        os.environ.clear()
        os.environ.update(old_env)


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "code_home"
        self.project = Path(self.tmp.name) / "project"
        self.project.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_markdown_links_accept_existing_relative_targets_with_fragments(self):
        reference = self.project / "references.md"
        target = self.project / "scripts" / "validator.py"
        target.parent.mkdir(parents=True)
        target.write_text("def validate():\n    return True\n", encoding="utf-8")
        reference.write_text(
            "See [validator](./scripts/validator.py#L1-L2).\n",
            encoding="utf-8",
        )

        invalid, sparse = audit.markdown_links(
            reference,
            reference.read_text(encoding="utf-8"),
            self.project,
        )

        self.assertEqual(invalid, [])
        self.assertEqual(sparse, [])

    def test_audit_accepts_links_between_sibling_authoritative_skills(self):
        self.home.mkdir(parents=True)
        skills_root = self.project / ".agents" / "skills"
        producer = skills_root / "producer"
        consumer = skills_root / "consumer"
        (producer / "references").mkdir(parents=True)
        consumer.mkdir(parents=True)
        (producer / "SKILL.md").write_text(
            "---\nname: producer\ndescription: producer\n---\n",
            encoding="utf-8",
        )
        (producer / "references" / "contract.md").write_text(
            "# Contract\n",
            encoding="utf-8",
        )
        (consumer / "SKILL.md").write_text(
            "---\nname: consumer\ndescription: consumer\n---\n\n"
            "Use the [producer contract](../producer/references/contract.md).\n",
            encoding="utf-8",
        )
        qv_src = (
            Path(__file__).resolve().parents[2]
            / ".system"
            / "skill-creator"
            / "scripts"
            / "quick_validate.py"
        )
        qv_dst = self.home / "skills/.system/skill-creator/scripts/quick_validate.py"
        qv_dst.parent.mkdir(parents=True)
        if qv_src.is_file():
            shutil.copy(qv_src, qv_dst)
        else:
            qv_dst.write_text("raise SystemExit(0)", encoding="utf-8")

        code, output = run_audit(
            ["--project-root", str(self.project), "--json"],
            {"CODEX_HOME": str(self.home)},
        )

        self.assertEqual(code, 0, output)
        self.assertNotIn("broken/displaced relative markdown link", output)

    def _write_fixture(self):
        self.home.mkdir(parents=True)
        (self.home / "AGENTS.md").write_text("global line\n", encoding="utf-8")
        nested_project_agents = self.project / "sub" / "AGENTS.md"
        nested_project_agents.parent.mkdir(parents=True, exist_ok=True)
        nested_project_agents.write_text("nested agent\n", encoding="utf-8")
        for container, child in (("packages", "pkg"), ("projects", "app")):
            owned = self.project / container / child / "AGENTS.md"
            owned.parent.mkdir(parents=True, exist_ok=True)
            owned.write_text(f"owned {container} agent\n", encoding="utf-8")
        for relative in (
            "sites/remote/AGENTS.md",
            ".local-scratch/run/AGENTS.md",
            "tools/package-backup/snapshots/nightly/AGENTS.md",
            "dist/generated/AGENTS.md",
        ):
            operational = self.project / relative
            operational.parent.mkdir(parents=True, exist_ok=True)
            operational.write_text("operational agent\n", encoding="utf-8")
        project_root_agents = self.project / "AGENTS.md"
        project_root_agents.write_text("line\n" * 125, encoding="utf-8")

        skills_root = self.home / "skills"
        skill_dir = skills_root / "note.skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: note-skill\ndescription: durable note skill with UTF-8 evidence âœ“\n---\n\n"
            "This is a long duplicate evidence block intentionally repeated across multiple files.\n\n"
            "This line links to [here](./missing.md) and remains local.\n",
            encoding="utf-8",
        )

        shared_root = self.project / ".agents" / "skills" / "shared"
        shared_root.mkdir(parents=True, exist_ok=True)
        (shared_root / "SKILL.md").write_text(
            "---\nname: shared-skill\ndescription: shared\n---\n\n"
            "This is a long duplicate evidence block intentionally repeated across multiple files.\n",
            encoding="utf-8",
        )

        qv_src = (
            Path(__file__).resolve().parents[2]
            / ".system"
            / "skill-creator"
            / "scripts"
            / "quick_validate.py"
        )
        qv_dst_dir = self.home / "skills/.system/skill-creator/scripts"
        qv_dst_dir.mkdir(parents=True, exist_ok=True)
        qv_dst = qv_dst_dir / "quick_validate.py"
        if qv_src.is_file():
            shutil.copy(qv_src, qv_dst)
        else:
            qv_dst.write_text(
                "from pathlib import Path\n"
                "import sys\n\n"
                "if len(sys.argv) != 2:\n"
                "    raise SystemExit(2)\n"
                "skill_dir = Path(sys.argv[1])\n"
                "skill_md = skill_dir / 'SKILL.md'\n"
                "if not skill_md.is_file() or not skill_md.read_text(encoding='utf-8').startswith('---'):\n"
                "    raise SystemExit(1)\n",
                encoding="utf-8",
            )

        inside_skill = shared_root / "resources"
        inside_skill.mkdir()
        (inside_skill / "ok.md").write_text("reference", encoding="utf-8")
        (shared_root / "references.md").write_text(
            "Valid [local](./resources/ok.md), broken [missing](./resources/missing.md).\n",
            encoding="utf-8",
        )
        (self.project / "docs").mkdir(parents=True, exist_ok=True)
        (self.project / "docs" / "ref.md").write_text("doc", encoding="utf-8")

    def test_audit_errors_missing_quick_validate_and_links(self):
        self._write_fixture()
        (self.project / ".agents" / "skills" / "shared" / "notes").mkdir(parents=True, exist_ok=True)
        (self.project / "AGENTS.md").write_text("line\n" * 125, encoding="utf-8")
        if (self.home / "skills/.system/skill-creator/scripts/quick_validate.py").exists():
            (self.home / "skills/.system/skill-creator/scripts/quick_validate.py").unlink()
        code, output = run_audit(
            ["--project-root", str(self.project), "--json"],
            {"CODEX_HOME": str(self.home)},
        )
        self.assertEqual(code, 1)
        self.assertIn("quick_validate.py not found", output)
        self.assertIn("broken/displaced relative markdown link", output)
        self.assertIn("AGENTS file is 125 lines", output)

    def test_audit_errors_for_nonexistent_project_root(self):
        self.home.mkdir(parents=True)
        missing = self.project / "does-not-exist"
        code, output = run_audit(
            ["--project-root", str(missing), "--json"],
            {"CODEX_HOME": str(self.home)},
        )
        self.assertEqual(code, 1)
        self.assertIn("project root does not exist", output.lower())

    def test_quick_validate_decodes_bytes_and_reports_path_and_command(self):
        skill_dir = self.project / "skill"
        skill_dir.mkdir(parents=True)
        quick_validate = self.home / "quick_validate.py"
        quick_validate.parent.mkdir(parents=True)
        quick_validate.write_text("# test\n", encoding="utf-8")
        context = audit.AuditContext(quick_validate_script=quick_validate)
        result = mock.Mock(returncode=1, stdout=b"bad-\xff-output", stderr=b"err-\xfe")

        with mock.patch.object(audit.subprocess, "run", return_value=result) as run:
            audit.run_quick_validate(skill_dir, context)

        self.assertEqual(len(context.errors), 1)
        diagnostic = context.errors[0]
        self.assertIn(str(skill_dir), diagnostic)
        self.assertIn(str(quick_validate), diagnostic)
        self.assertIn("command:", diagnostic)
        self.assertIn("\ufffd", diagnostic)

        command = run.call_args.args[0]
        self.assertFalse(run.call_args.kwargs.get("text", False))
        self.assertIn(str(skill_dir), command)

    def test_audit_reports_invalid_utf8_with_filename(self):
        self.home.mkdir(parents=True)
        invalid = self.home / "AGENTS.md"
        invalid.write_bytes(b"valid prefix\xff\n")
        code, output = run_audit(
            ["--json"],
            {"CODEX_HOME": str(self.home)},
        )
        self.assertEqual(code, 1)
        self.assertIn(json.dumps(str(invalid))[1:-1], output)
        self.assertIn("invalid utf-8", output.lower())

    def test_audit_nested_agents_and_duplicate_leads(self):
        self._write_fixture()
        code, output = run_audit(
            ["--project-root", str(self.project), "--strict-budgets", "--json"],
            {"CODEX_HOME": str(self.home)},
        )
        self.assertEqual(code, 1)
        self.assertIn("duplicate nontrivial block(s)", output.lower())
        self.assertIn("canonical-ownership review", output.lower())
        self.assertNotIn("quick_validate.py failed", output)
        payload = json.loads(output)
        metric_paths = [
            m["path"] for m in payload.get("metrics", []) if m.get("kind") == "AGENTS"
        ]
        normalized = [p.replace("\\", "/") for p in metric_paths]
        self.assertTrue(any("/packages/pkg/AGENTS.md" in p for p in normalized))
        self.assertTrue(any("/projects/app/AGENTS.md" in p for p in normalized))
        self.assertFalse(any("/sub/AGENTS.md" in p for p in normalized))
        self.assertFalse(
            any(
                any(token in p for token in ("/sites/", "/.local-scratch/", "/dist/", "/snapshots/"))
                for p in normalized
            )
        )


def run() -> None:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    run()

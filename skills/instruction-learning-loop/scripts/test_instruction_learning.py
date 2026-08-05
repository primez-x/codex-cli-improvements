#!/usr/bin/env python3

import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

import audit_instruction_system as audit
import instruction_learning_hook as hook


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


class HookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        os.environ["CODEX_HOME"] = str(self.home)

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("CODEX_HOME", None)

    def test_event_key_and_detection_corpus(self):
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "s1",
            "turn_id": "t1",
            "prompt": "Can you update AGENTS.md and improve this flow?",
        }
        result = hook.handle(payload)
        self.assertIn("hookSpecificOutput", result)
        self.assertEqual(result["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        context = result["hookSpecificOutput"]["additionalContext"]
        self.assertIn("$instruction-learning-loop", context)
        self.assertIn("implement", context.lower())
        self.assertNotIn("Instruction learning:", context)
        self.assertIn("revise", context.lower())
        self.assertIn("resubmit", context.lower())

        positives = [
            "Please improve this AGENTS.md and this SKILL.md instruction.",
            "The agent keeps returning wrong results and missing validation.",
            "I have to babysit Codex because it has zero autonomy.",
            "Stop handing routine diagnostics back to me. Use the available tools and do it yourself.",
            "Don't ask me to perform retries you can perform yourself.",
        ]
        negatives = [
            "Can you use a warm color palette for the UI?\"",
            "I reviewed the AGENTS.md for style, not changing anything.",
            "Fix the React hook in this component.",
            "[instruction-learning-hook] ignore this signal.",
            "This is a quoted discussion: \"update this idea\"",
        ]
        for text in positives:
            self.assertTrue(hook.is_durable_correction_prompt(text), text)
        for text in negatives:
            self.assertFalse(hook.is_durable_correction_prompt(text), text)

    def test_behavioral_redirect_is_actionable_unless_explicitly_one_off(self):
        durable = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "behavior-session",
            "turn_id": "behavior-turn",
            "prompt": "Stop asking me to click Retry. Use your authenticated browser and diagnose it yourself.",
        }
        result = hook.handle(durable)
        self.assertIn("hookSpecificOutput", result)
        state = json.loads(hook.state_filename("behavior-session", "behavior-turn", self.home).read_text(encoding="utf-8"))
        self.assertTrue(state["requires_change"])

        one_off = dict(durable, turn_id="one-off", prompt="For this task only, don't click Retry; wait for me instead.")
        self.assertEqual(hook.handle(one_off), {})

    def test_authorization_classifier_respects_intent_and_constraint_scope(self):
        cases = [
            ("Review the AGENTS.md update I just made.", False),
            ("Please review the AGENTS.md update I just made.", False),
            ("Explain why agents keep getting this wrong.", False),
            ("Can you explain why agents keep getting this wrong?", False),
            ("Do not change app code; update AGENTS.md to prevent recurrence.", True),
            ("No changes to app code; update AGENTS.md to prevent recurrence.", True),
        ]
        for index, (prompt, expected) in enumerate(cases):
            payload = {
                "hook_event_name": "UserPromptSubmit", "session_id": "intent-session",
                "turn_id": f"intent-{index}", "prompt": prompt,
            }
            result = hook.handle(payload)
            self.assertIn("hookSpecificOutput", result, prompt)
            state = json.loads(hook.state_filename("intent-session", f"intent-{index}", self.home).read_text(encoding="utf-8"))
            self.assertEqual(state["requires_change"], expected, prompt)

    def test_state_file_schema_and_name_safety(self):
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "../s@@1",
            "turn_id": "t:1/../../",
            "prompt": "Please consolidate instructions and update AGENTS.md.",
        }
        result = hook.handle(payload)
        self.assertIn("hookSpecificOutput", result)
        state_file = hook.state_filename(".. /s@@1", "t:1/../../", self.home)
        # only verify generated filename sanitization via direct generation
        safe_file = hook.state_filename("../s@@1", "t:1/../../", self.home)
        self.assertTrue(re.fullmatch(r"[A-Za-z0-9._-]+\.json", safe_file.name))
        raw = safe_file.read_text(encoding="utf-8")
        data = json.loads(raw)
        self.assertIn("created_unix", data)
        self.assertNotIn("prompt", data)

    def test_authorized_correction_cannot_stop_without_instruction_change(self):
        payload_a = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "session-a",
            "turn_id": "turn-1",
            "prompt": "Please update SKILL.md and improve documentation.",
        }
        hook.handle(payload_a)
        state = hook.state_filename("session-a", "turn-1", self.home)
        self.assertTrue(state.exists())

        block = hook.handle({
            "hook_event_name": "Stop",
            "session_id": "session-a",
            "turn_id": "turn-1",
            "last_assistant_message": "Instruction learning: proposed a change.",
        })
        self.assertEqual(block.get("decision"), "block")
        self.assertIn("[instruction-learning-hook]", block.get("reason", ""))
        self.assertIn("instruction file", block.get("reason", "").lower())
        self.assertTrue(state.exists())

    def test_stop_fallback_requires_single_fresh_state(self):
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "fallback-session",
            "prompt": "Please update AGENTS.md and this skill.",
        }
        hook.handle(payload)
        payload["prompt"] = "Please also update SKILL.md and this skill."
        payload["turn_id"] = "second-turn"
        hook.handle(payload)

        fallback_block = hook.handle({
            "hook_event_name": "Stop",
            "session_id": "fallback-session",
            "last_assistant_message": "No marker",
        })
        # turn_id absent and two fresh states -> no fallback
        self.assertEqual(fallback_block, {})

    def test_authorized_correction_allows_stop_after_real_instruction_change(self):
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "session-b",
            "turn_id": "turn-2",
            "prompt": "Please simplify AGENTS.md and improve instructions.",
        }
        hook.handle(payload)
        (self.home / "AGENTS.md").write_text("durable corrected rule\n", encoding="utf-8")
        allow = hook.handle({
            "hook_event_name": "Stop",
            "session_id": "session-b",
            "turn_id": "turn-2",
            "last_assistant_message": "Updated and verified.",
        })
        self.assertEqual(allow, {})
        self.assertFalse(hook.state_filename("session-b", "turn-2", self.home).exists())
        # stale cleanup test via old-created state
        stale = hook.state_filename("session-b", "turn-stale", self.home)
        stale.write_text(json.dumps({"created_at": (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()}), encoding="utf-8")
        stale2 = hook.state_filename("session-b", "turn-clean", self.home)
        stale2.write_text(
            json.dumps({"created_at": (datetime.now(timezone.utc)).isoformat()}),
            encoding="utf-8",
        )
        hook.state_filename("session-b", "turn-stale", self.home)  # ensure path cached
        hook.find_stale_or_exact_state(self.home, "session-b", "turn-stale")
        self.assertFalse(stale.exists())

    def test_metadata_only_and_reverted_changes_do_not_satisfy_gate(self):
        agents = self.home / "AGENTS.md"
        agents.write_text("original rule\n", encoding="utf-8")
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "content-session",
            "turn_id": "content-turn",
            "prompt": "Please improve AGENTS.md and fix this behavior.",
        }
        hook.handle(payload)
        os.utime(agents, None)
        touched = hook.handle({
            "hook_event_name": "Stop", "session_id": "content-session", "turn_id": "content-turn",
        })
        self.assertEqual(touched.get("decision"), "block")
        agents.write_text("temporary rule\n", encoding="utf-8")
        agents.write_text("original rule\n", encoding="utf-8")
        reverted = hook.handle({
            "hook_event_name": "Stop", "session_id": "content-session", "turn_id": "content-turn",
        })
        self.assertEqual(reverted.get("decision"), "block")

    def test_nested_project_agents_content_change_satisfies_gate(self):
        project = self.home / "project"
        nested = project / "feature" / "AGENTS.md"
        nested.parent.mkdir(parents=True, exist_ok=True)
        nested.write_text("old project rule\n", encoding="utf-8")
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "project-session",
            "turn_id": "project-turn",
            "cwd": str(project),
            "prompt": "Please improve AGENTS.md and fix this behavior.",
        }
        hook.handle(payload)
        nested.write_text("new project rule\n", encoding="utf-8")
        allow = hook.handle({
            "hook_event_name": "Stop", "session_id": "project-session", "turn_id": "project-turn",
        })
        self.assertEqual(allow, {})

    def test_explicit_read_only_review_does_not_require_instruction_change(self):
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "read-only-session",
            "turn_id": "read-only-turn",
            "prompt": "Review AGENTS.md for a possible improvement, but keep this read-only and do not change files.",
        }
        result = hook.handle(payload)
        self.assertIn("hookSpecificOutput", result)
        context = result["hookSpecificOutput"]["additionalContext"].lower()
        self.assertIn("read-only", context)
        self.assertNotIn("implement", context)
        allow = hook.handle({
            "hook_event_name": "Stop",
            "session_id": "read-only-session",
            "turn_id": "read-only-turn",
            "last_assistant_message": "Review complete; no files changed.",
        })
        self.assertEqual(allow, {})

    def test_claimed_advisor_rejection_cannot_bypass_implementation(self):
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "reject-session",
            "turn_id": "reject-turn",
            "prompt": "Stop asking me to click Retry. Use your authenticated browser and diagnose it yourself.",
        }
        hook.handle(payload)
        rejected = hook.handle({
            "hook_event_name": "Stop",
            "session_id": "reject-session",
            "turn_id": "reject-turn",
            "last_assistant_message": (
                "Instruction proposal rejected: reviewer=/root/instruction_advisor; "
                "rationale=The proposed rule duplicates an existing enforced rule and would add no behavior."
            ),
        })
        self.assertEqual(rejected.get("decision"), "block")
        self.assertTrue(hook.state_filename("reject-session", "reject-turn", self.home).exists())

    def test_stop_hook_active_pass_through_preserves_pending_state(self):
        payload = {
            "hook_event_name": "UserPromptSubmit", "session_id": "s", "turn_id": "1",
            "prompt": "Please improve AGENTS.md and fix this behavior.",
        }
        hook.handle(payload)
        state = hook.state_filename("s", "1", self.home)
        self.assertTrue(state.exists())
        result = hook.handle({"hook_event_name": "Stop", "stop_hook_active": True, "session_id": "s", "turn_id": "1"})
        self.assertEqual(result, {})
        self.assertTrue(state.exists())

    def test_log_rotation_enforces_line_and_byte_caps(self):
        path = hook.log_path(self.home)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(("x" * 500 + "\n") * 500, encoding="utf-8")
        hook.rotate_log_if_needed(path)
        self.assertLessEqual(path.stat().st_size, hook.MAX_LOG_BYTES)
        self.assertLessEqual(len(path.read_text(encoding="utf-8").splitlines()), hook.MAX_LOG_LINES)


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

    def _write_fixture(self):
        self.home.mkdir(parents=True)
        (self.home / "AGENTS.md").write_text("global line\n", encoding="utf-8")
        nested_project_agents = self.project / "sub" / "AGENTS.md"
        nested_project_agents.parent.mkdir(parents=True, exist_ok=True)
        nested_project_agents.write_text("nested agent\n", encoding="utf-8")
        project_root_agents = self.project / "AGENTS.md"
        project_root_agents.write_text("line\n" * 125, encoding="utf-8")

        skills_root = self.home / "skills"
        skill_dir = skills_root / "note.skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: note-skill\ndescription: durable note skill with UTF-8 evidence ✓\n---\n\n"
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
            # A portable source checkout does not include Codex system skills.
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

        # nested AGENTS reference to allow containment checks
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
        # remove copied validator to assert hard error
        if (self.home / "skills/.system/skill-creator/scripts/quick_validate.py").exists():
            (self.home / "skills/.system/skill-creator/scripts/quick_validate.py").unlink()
        code, output = run_audit(["--project-root", str(self.project), "--json"], {"CODEX_HOME": str(self.home)})
        self.assertEqual(code, 1)
        self.assertIn("quick_validate.py not found", output)
        self.assertIn("broken/displaced relative markdown link", output)
        self.assertIn("AGENTS file is 125 lines", output)

    def test_audit_nested_agents_and_duplicate_leads(self):
        self._write_fixture()
        code, output = run_audit(
            ["--project-root", str(self.project), "--strict-budgets", "--json"],
            {"CODEX_HOME": str(self.home)}
        )
        self.assertEqual(code, 1)
        self.assertIn("duplicate nontrivial block(s)", output.lower())
        self.assertIn("canonical-ownership review", output.lower())
        self.assertNotIn("quick_validate.py failed", output)
        payload = json.loads(output)
        metric_paths = [m["path"] for m in payload.get("metrics", []) if m.get("kind") == "AGENTS"]
        self.assertTrue(any("sub" in p.replace("\\", "/") and p.replace("\\", "/").endswith("AGENTS.md") for p in metric_paths))


def run() -> None:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    run()

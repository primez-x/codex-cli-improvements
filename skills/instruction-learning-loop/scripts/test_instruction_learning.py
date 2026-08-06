#!/usr/bin/env python3

import io
import importlib.util
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
from unittest import mock

import audit_instruction_system as audit
import instruction_learning_hook as hook


def load_plan_gap_hook():
    path = Path(__file__).resolve().parents[3] / "hooks" / "plan_gap_goal_hook.py"
    spec = importlib.util.spec_from_file_location("plan_gap_goal_hook_under_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load plan gap hook from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


plan_gap_hook = load_plan_gap_hook()


PLAN_IMPLEMENTATION_ACCEPTED = (
    "Implement the plan.",
    "Yes, please implement this plan!",
    "Implement the plan: update AGENTS.md.",
    "Implement the plan: No code changes; update AGENTS.md.",
    "Implement the plan: Review only; implement accepted findings afterward.",
    "Implement the plan: Review only; review the proposal before updating AGENTS.md.",
    "Implement the plan: Do not implement this plan before updating AGENTS.md.",
    "Implement the plan: Do not implement this plan until after applying the approved correction.",
    "Implement the plan: Review only before running the installer.",
    "Implement the plan: No code changes before validating the hook.",
    "Implement the plan: No code changes before testing the hook.",
    "Implement the plan: Do not implement this plan until after building the package.",
    "Implement the plan: Review only; build the package afterward.",
    "Implement the plan: No code changes, but update AGENTS.md.",
    "Implement the plan: Review only, but build the package.",
    "Implement the plan: Do not implement this plan before you update AGENTS.md.",
    "Implement the plan: No code changes; instead update AGENTS.md.",
    "Implement the plan: Review only; then test the hook.",
    "Implement the plan: Review only; build the package. Tests are green.",
    "Implement the plan: No code changes, but update AGENTS.md. Validation is complete.",
    "Implement the plan: Review only; run tests until they pass.",
    "Implement the plan: Review only; fix tests that are failing.",
    "Implement the plan: Review only; document the errors.",
    "Implement the plan: Review only; fix the crashes.",
    "Implement the plan: No code changes; update the feed.",
    "Implement the plan: Review only; implement changes requested.",
    "Implement the plan: No code changes; update AGENTS.md as discussed.",
    "Implement the plan: Review only; build package.",
    "Implement the plan: Review only; run test.",
    "Implement the plan: Review only; update process that failed.",
    "Implement the plan: Review only; run tests that failed.",
    "Implement the plan: Never mind, but update process because it failed.",
    "Implement the plan: Never mind, then update process because it failed.",
    "Implement the plan: Review only: but update process because it failed.",
    "Implement the plan: Proposal only: then update process.",
    "Implement the plan: Proposal only! But update process because it failed.",
    "Implement the plan: Review only? Then build the package.",
    "Implement the plan: Review only -- but build the package.",
    "Implement the plan: Keep this task read-only -- then update AGENTS.md.",
    "Implement the plan: Review only — but build the package.",
    "Implement the plan: Proposal only – then update AGENTS.md.",
    (
        "PLEASE IMPLEMENT THIS PLAN:\n"
        "# Agent hierarchy\n"
        "Use a read-only reviewer.\n"
        "`Do not implement this plan` is a parser test.\n"
        "Do not modify hooks; update AGENTS.md."
    ),
    (
        "Please implement this plan:\n"
        "Do not implement the original hierarchy plan.\n"
        "Update AGENTS.md instead."
    ),
    (
        "Implement the plan:\n"
        "Do not change app code; update AGENTS.md."
    ),
    (
        "Implement the plan:\n"
        "Review only applies to sol_advisor; implement after review."
    ),
    (
        "Implement the plan:\n"
        "No instruction changes to the original hierarchy; update AGENTS.md."
    ),
    (
        "Implement the plan:\n"
        "Do not edit any files in the original hierarchy; update AGENTS.md."
    ),
)


PLAN_IMPLEMENTATION_REJECTED = (
    "PLEASE IMPLEMENT THIS PLAN:",
    "> PLEASE IMPLEMENT THIS PLAN:\n> Update AGENTS.md.",
    '"PLEASE IMPLEMENT THIS PLAN:"\nUpdate AGENTS.md.',
    "`PLEASE IMPLEMENT THIS PLAN:`\nUpdate AGENTS.md.",
    "Please explain how to implement this plan.",
    "Do not implement this plan; explain it.",
    "We should implement this plan later.",
    "PLEASE IMPLEMENT THIS PLAN:\nWait, don't implement it; explain only.",
    "PLEASE IMPLEMENT THIS PLAN:\nNever mind, do not implement this plan.",
    "PLEASE IMPLEMENT THIS PLAN:\nNever mind.",
    "PLEASE IMPLEMENT THIS PLAN:\nActually -- don't implement it.",
    "PLEASE IMPLEMENT THIS PLAN: cancel this request.",
    "PLEASE IMPLEMENT THIS PLAN:\nDo not implement this plan until I approve it.",
    "PLEASE IMPLEMENT THIS PLAN:\nWait, don't implement it because I need to review it first.",
    "PLEASE IMPLEMENT THIS PLAN:\nDo not implement this plan because tests are failing.",
    "PLEASE IMPLEMENT THIS PLAN:\nWait, don't implement it because applying the patch could corrupt data.",
    "PLEASE IMPLEMENT THIS PLAN:\nNever mind because the build is broken.",
    "PLEASE IMPLEMENT THIS PLAN:\nDo not implement this plan until tests pass.",
    "PLEASE IMPLEMENT THIS PLAN:\nDo not implement this plan until the tests pass.",
    "PLEASE IMPLEMENT THIS PLAN:\nDo not implement this plan before the build is green.",
    "PLEASE IMPLEMENT THIS PLAN:\nDo not implement this plan until testing is complete.",
    "PLEASE IMPLEMENT THIS PLAN:\nDo not implement this plan before building finishes.",
    "PLEASE IMPLEMENT THIS PLAN:\nNever mind, build is broken.",
    "PLEASE IMPLEMENT THIS PLAN:\nNever mind, test results are failing.",
    "PLEASE IMPLEMENT THIS PLAN:\nNever mind, build pipeline failed.",
    "PLEASE IMPLEMENT THIS PLAN:\nWait, don't implement it; patch validation failed.",
    "PLEASE IMPLEMENT THIS PLAN:\nNever mind, run failed.",
    "PLEASE IMPLEMENT THIS PLAN:\nNever mind, install failed.",
    "PLEASE IMPLEMENT THIS PLAN:\nNever mind, update is blocked.",
    "PLEASE IMPLEMENT THIS PLAN:\nReview only, but test results fail.",
    "PLEASE IMPLEMENT THIS PLAN:\nNever mind, update AGENTS.md is blocked.",
    "PLEASE IMPLEMENT THIS PLAN:\nNever mind, patch config.toml failed.",
    "PLEASE IMPLEMENT THIS PLAN:\nNever mind, update C:/repo/AGENTS.md is blocked.",
    "PLEASE IMPLEMENT THIS PLAN:\nNever mind, patch https://example.test/config failed.",
    "PLEASE IMPLEMENT THIS PLAN:\nNever mind, patch https://example.test/config?mode=full failed.",
    "PLEASE IMPLEMENT THIS PLAN:\nNever mind, build pipeline crashed.",
    "PLEASE IMPLEMENT THIS PLAN:\nNever mind, test runner timed out.",
    "PLEASE IMPLEMENT THIS PLAN:\nNever mind, build pipeline explodes.",
    "PLEASE IMPLEMENT THIS PLAN:\nNever mind, test runner freezes.",
    "PLEASE IMPLEMENT THIS PLAN:\nNever mind, build pipeline that crashed.",
    "PLEASE IMPLEMENT THIS PLAN:\nNever mind, test runner that timed out.",
    "PLEASE IMPLEMENT THIS PLAN:\nNever mind, patch validation which failed.",
    "PLEASE IMPLEMENT THIS PLAN:\nNever mind, update process because it failed.",
    "PLEASE IMPLEMENT THIS PLAN:\nReview only: build pipeline that crashed.",
    "PLEASE IMPLEMENT THIS PLAN:\nReview only: test runner that timed out.",
    "PLEASE IMPLEMENT THIS PLAN:\nKeep this task read-only: update process because it failed.",
    "PLEASE IMPLEMENT THIS PLAN:\nProposal only: patch validation which failed.",
    "PLEASE IMPLEMENT THIS PLAN:\nReview only: build pipeline.",
    "PLEASE IMPLEMENT THIS PLAN:\nProposal only: update process.",
    "PLEASE IMPLEMENT THIS PLAN:\nProposal only! Update process because it failed.",
    "PLEASE IMPLEMENT THIS PLAN:\nReview only? Build pipeline that crashed.",
    "PLEASE IMPLEMENT THIS PLAN:\nReview only -- build pipeline that crashed.",
    "PLEASE IMPLEMENT THIS PLAN:\nKeep this task read-only -- update process because it failed.",
    "PLEASE IMPLEMENT THIS PLAN:\nReview only — build pipeline that crashed.",
    "PLEASE IMPLEMENT THIS PLAN:\nProposal only – update process because it failed.",
    "PLEASE IMPLEMENT THIS PLAN:\nKeep this task read-only while I review the proposal.",
    "PLEASE IMPLEMENT THIS PLAN:\nKeep this read-only.",
    "PLEASE IMPLEMENT THIS PLAN:\nReview only.",
    "PLEASE IMPLEMENT THIS PLAN:\nDo not edit any files.",
    "PLEASE IMPLEMENT THIS PLAN:\nNo instruction changes.",
)


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
        self.assertIn("without renewed user approval", context.lower())

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

    def test_plan_implementation_predicates_share_directive_scoped_corpus(self):
        predicates = (
            hook.is_plan_implementation_prompt,
            plan_gap_hook.is_plan_implementation_prompt,
        )
        for predicate in predicates:
            for text in PLAN_IMPLEMENTATION_ACCEPTED:
                self.assertTrue(predicate(text), (predicate.__module__, text))
            for text in PLAN_IMPLEMENTATION_REJECTED:
                self.assertFalse(predicate(text), (predicate.__module__, text))

    def test_multiline_approved_plan_is_actionable_despite_scoped_non_goals(self):
        prompt = PLAN_IMPLEMENTATION_ACCEPTED[2]
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "approved-plan-session",
            "turn_id": "approved-plan-turn",
            "prompt": prompt,
        }
        result = hook.handle(payload)
        context = result["hookSpecificOutput"]["additionalContext"].lower()
        state = json.loads(
            hook.state_filename(
                "approved-plan-session", "approved-plan-turn", self.home
            ).read_text(encoding="utf-8")
        )
        self.assertTrue(state["requires_change"])
        self.assertIn("implement", context)
        self.assertNotIn("made the task read-only", context)

    def test_plan_gap_main_routes_multiline_acceptance_without_real_goal_mutation(self):
        for index, prompt in enumerate(PLAN_IMPLEMENTATION_ACCEPTED):
            calls = []
            payload = {
                "hook_event_name": "UserPromptSubmit",
                "session_id": f"accepted-session-{index}",
                "prompt": prompt,
            }
            with mock.patch.object(
                plan_gap_hook, "set_goal", side_effect=calls.append
            ), mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))):
                self.assertEqual(plan_gap_hook.main(), 0)
            self.assertEqual(calls, [f"accepted-session-{index}"], prompt)

        for prompt in PLAN_IMPLEMENTATION_REJECTED:
            calls = []
            payload = {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "rejected-session",
                "prompt": prompt,
            }
            with mock.patch.object(
                plan_gap_hook, "set_goal", side_effect=calls.append
            ), mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))):
                self.assertEqual(plan_gap_hook.main(), 0)
            self.assertEqual(calls, [], prompt)

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
            ("Review only applies to sol_advisor; update AGENTS.md.", True),
            ("No instruction changes to the original hierarchy; update AGENTS.md.", True),
            ("Do not edit any files in the original hierarchy; update AGENTS.md.", True),
            ("This request is read-only for app code; update AGENTS.md.", True),
            ("No code changes; update AGENTS.md.", True),
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

    def test_global_read_only_directives_remain_read_only(self):
        prompts = (
            "Please fix the instruction system, but this task is read-only.",
            "Please update AGENTS.md. This request is read only.",
            "Do not change any files; explain why the instruction system keeps failing.",
        )
        for index, prompt in enumerate(prompts):
            payload = {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "global-read-only-session",
                "turn_id": f"global-read-only-{index}",
                "prompt": prompt,
            }
            result = hook.handle(payload)
            self.assertTrue(hook.is_durable_correction_prompt(prompt), prompt)
            self.assertTrue(hook.explicitly_read_only(prompt), prompt)
            self.assertFalse(hook.requires_instruction_change(prompt), prompt)
            self.assertIn("hookSpecificOutput", result, prompt)
            self.assertIn(
                "read-only",
                result["hookSpecificOutput"]["additionalContext"].lower(),
                prompt,
            )
            state = json.loads(
                hook.state_filename(
                    "global-read-only-session",
                    f"global-read-only-{index}",
                    self.home,
                ).read_text(encoding="utf-8")
            )
            self.assertFalse(state["requires_change"], prompt)
            self.assertEqual(
                hook.handle({
                    "hook_event_name": "Stop",
                    "session_id": "global-read-only-session",
                    "turn_id": f"global-read-only-{index}",
                }),
                {},
                prompt,
            )

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

    def test_revise_then_approve_cannot_become_a_user_checkpoint(self):
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "revise-session",
            "turn_id": "revise-turn",
            "prompt": "Please fix the instruction system and update AGENTS.md.",
        }
        hook.handle(payload)
        blocked = hook.handle({
            "hook_event_name": "Stop",
            "session_id": "revise-session",
            "turn_id": "revise-turn",
            "last_assistant_message": (
                "Sol verdict: REVISE, then approve. Waiting for renewed user approval."
            ),
        })
        self.assertEqual(blocked.get("decision"), "block")
        self.assertIn("implement", blocked.get("reason", "").lower())

    def test_test_only_change_does_not_satisfy_instruction_stop_gate(self):
        skill = self.home / "skills" / "demo" / "SKILL.md"
        test_file = self.home / "skills" / "demo" / "scripts" / "test_policy.py"
        self_test_result = (
            self.home
            / "skills"
            / "demo"
            / "references"
            / "evaluation-self-test-results.json"
        )
        fixture = self.home / "skills" / "demo" / "fixtures" / "policy_cases.json"
        conftest = self.home / "skills" / "demo" / "scripts" / "conftest.py"
        test_file.parent.mkdir(parents=True)
        self_test_result.parent.mkdir(parents=True)
        fixture.parent.mkdir(parents=True)
        skill.write_text("---\nname: demo\ndescription: demo\n---\n", encoding="utf-8")
        test_file.write_text("assert True\n", encoding="utf-8")
        self_test_result.write_text('{"passed": true}\n', encoding="utf-8")
        fixture.write_text('{"case": "baseline"}\n', encoding="utf-8")
        conftest.write_text("VALUE = 'baseline'\n", encoding="utf-8")
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "test-only-session",
            "turn_id": "test-only-turn",
            "prompt": "Please fix this instruction behavior and update SKILL.md.",
        }
        hook.handle(payload)

        test_file.write_text("assert False\n", encoding="utf-8")
        self_test_result.write_text('{"passed": false}\n', encoding="utf-8")
        fixture.write_text('{"case": "changed"}\n', encoding="utf-8")
        conftest.write_text("VALUE = 'changed'\n", encoding="utf-8")
        blocked = hook.handle({
            "hook_event_name": "Stop",
            "session_id": "test-only-session",
            "turn_id": "test-only-turn",
        })
        self.assertEqual(blocked.get("decision"), "block")

        skill.write_text(
            "---\nname: demo\ndescription: corrected demo\n---\n", encoding="utf-8"
        )
        allowed = hook.handle({
            "hook_event_name": "Stop",
            "session_id": "test-only-session",
            "turn_id": "test-only-turn",
        })
        self.assertEqual(allowed, {})

    def test_test_artifact_filtering_is_relative_to_the_codex_home(self):
        nested_home = self.home / "tests" / "home"
        agents = nested_home / "AGENTS.md"
        hooks = nested_home / "hooks.json"
        skill = nested_home / "skills" / "demo" / "SKILL.md"
        fixture = nested_home / "skills" / "demo" / "tests" / "case.json"
        fixture.parent.mkdir(parents=True)
        agents.parent.mkdir(parents=True, exist_ok=True)
        skill.parent.mkdir(parents=True, exist_ok=True)
        agents.write_text("real instruction\n", encoding="utf-8")
        hooks.write_text("{}\n", encoding="utf-8")
        skill.write_text("---\nname: demo\ndescription: demo\n---\n", encoding="utf-8")
        fixture.write_text('{"test": true}\n', encoding="utf-8")

        discovered = {path.resolve() for path in hook.instruction_files(nested_home)}
        self.assertIn(agents.resolve(), discovered)
        self.assertIn(hooks.resolve(), discovered)
        self.assertIn(skill.resolve(), discovered)
        self.assertNotIn(fixture.resolve(), discovered)

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

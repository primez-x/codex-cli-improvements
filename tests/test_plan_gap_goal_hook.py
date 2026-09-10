from __future__ import annotations

import io
import json
import sys
import unittest
from importlib import util
from pathlib import Path
from unittest import mock


HOOK_PATH = Path(__file__).resolve().parents[1] / "hooks" / "plan_gap_goal_hook.py"


spec = util.spec_from_file_location("plan_gap_goal_hook", HOOK_PATH)
assert spec is not None
plan_gap_goal_hook = util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(plan_gap_goal_hook)


class PlanGapGoalHookTests(unittest.TestCase):
    def test_child_launch_preserves_rpc_and_parent_console(self) -> None:
        for platform, expected in (("nt", 0x08000000), ("posix", 0)):
            with self.subTest(platform=platform):
                process = mock.MagicMock()
                with (
                    mock.patch.object(plan_gap_goal_hook.os, "name", platform),
                    mock.patch.object(plan_gap_goal_hook.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True),
                    mock.patch.object(plan_gap_goal_hook, "find_codex", return_value="codex"),
                    mock.patch.object(plan_gap_goal_hook.subprocess, "Popen", return_value=process) as launch,
                    mock.patch.object(plan_gap_goal_hook.threading, "Thread"),
                    mock.patch.object(plan_gap_goal_hook, "wait_for_response", return_value={"result": {"goal": {"status": "active"}}}),
                    mock.patch.object(plan_gap_goal_hook, "log"),
                ):
                    plan_gap_goal_hook.set_goal("existing-thread")
                self.assertEqual(launch.call_args.args[0], ["codex", "app-server", "--stdio"])
                self.assertEqual(launch.call_args.kwargs["creationflags"], expected)
                for stream in ("stdin", "stdout"):
                    self.assertIs(launch.call_args.kwargs[stream], plan_gap_goal_hook.subprocess.PIPE)
                sent = [json.loads(call.args[0]) for call in process.stdin.write.call_args_list]
                self.assertEqual([item["method"] for item in sent], ["initialize", "initialized", "thread/goal/get"])
                process.terminate.assert_called_once()
                process.wait.assert_called_once_with(timeout=2)

    def run_hook(self, prompt: str) -> list[str]:
        payload = {"prompt": prompt, "session_id": "thread-123"}
        calls: list[str] = []

        def fake_set_goal(thread_id: str) -> None:
            calls.append(thread_id)

        with (
            mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))),
            mock.patch.object(plan_gap_goal_hook, "set_goal", fake_set_goal),
        ):
            self.assertEqual(plan_gap_goal_hook.main(), 0)

        return calls

    def test_all_supported_plan_acceptance_prompts_set_goal(self) -> None:
        prompts = (
            "Implement the plan",
            "Implement the plan.",
            "Yes implement the plan",
            "Yes implement the plan.",
            "Yes, implement the plan",
            "Yes, implement the plan.",
            "Yes implement this plan",
            "Yes implement this plan.",
            "Yes, implement this plan",
            "Yes, implement this plan.",
        )
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertEqual(self.run_hook(prompt), ["thread-123"])

    def test_non_acceptance_prompt_does_not_set_goal(self) -> None:
        self.assertEqual(self.run_hook("Please explain the plan first."), [])

    def test_inline_plan_body_sets_goal(self) -> None:
        self.assertEqual(self.run_hook("Implement the plan: add the regression tests."), ["thread-123"])

    def test_immediate_reversals_and_restrictions_do_not_set_goal(self) -> None:
        prompts = (
            "Implement the plan.\nDo not implement the plan because scope changed.",
            "Implement the plan.\nNo code changes until approved.",
            "Implement the plan.\nReview only -- do not edit files.",
        )
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertEqual(self.run_hook(prompt), [])

    def test_objective_requires_applicable_delivery_gates(self) -> None:
        objective = " ".join(plan_gap_goal_hook.OBJECTIVE.casefold().split())
        for phrase in (
            "delivery gates applicable under the active repository and project instructions",
            "commit, git push, or artifact upload do not substitute",
            "required build, install or deployment, read-back, or runtime verification",
            "keep the goal unfinished",
            "user-excluded or non-applicable gates do not block completion",
            "do not claim full delivery or live verification",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, objective)


if __name__ == "__main__":
    unittest.main()

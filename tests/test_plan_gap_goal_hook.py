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

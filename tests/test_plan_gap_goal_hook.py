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

    def test_existing_plan_acceptance_prompt_sets_goal(self) -> None:
        self.assertEqual(self.run_hook("Implement the plan."), ["thread-123"])

    def test_windows_client_plan_acceptance_prompt_sets_goal(self) -> None:
        self.assertEqual(self.run_hook("Yes, implement this plan"), ["thread-123"])

    def test_non_acceptance_prompt_does_not_set_goal(self) -> None:
        self.assertEqual(self.run_hook("Please explain the plan first."), [])


if __name__ == "__main__":
    unittest.main()

"""Check durable authority boundaries without printing private instructions."""
import os
import re
import unittest
from pathlib import Path


class GlobalAutonomyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(os.environ.get("CODEX_AUTONOMY_HOME") or os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        cls.rules = " ".join((root / "AGENTS.md").read_text(encoding="utf-8").lower().split())

    def require(self, pattern, label):
        self.assertTrue(re.search(pattern, self.rules) is not None, label)

    def test_explicit_action_and_read_only_scope_are_distinct(self):
        self.require(r"reported defect.*authorizes diagnosis and remediation", "Defect remediation authority is missing")
        self.require(r"honor explicit limits.*root cause only.*read-only.*no changes", "Explicit read-only limits are missing")
        self.require(r"answer, explain, review, and status requests remain read-only", "Review-only scope is missing")

    def test_skill_methodology_cannot_expand_or_withhold_authority(self):
        self.require(r"user instructions take precedence over skill guidelines", "Instruction precedence is missing")
        self.require(r"must not invent approval gates", "Methodology gate boundary is missing")
        self.require(r"reject or defer findings that expand scope", "Scope boundary is missing")

    def test_plan_acceptance_keeps_goal_and_gap_check(self):
        self.require(r"implement the plan.*plan-implementation gap goal", "Plan goal directive is missing")
        self.require(r"read the current goal", "Existing goal preservation is missing")
        self.require(r"checklist-based gap analysis", "Completion gap check is missing")

    def test_external_and_high_impact_actions_keep_their_own_authority(self):
        self.require(r"prs, merges, releases, deployments, and messages require explicit authorization", "External-action authority is missing")
        self.require(r"keep human approval for financial, legal, regulated, destructive", "High-impact authority is missing")
        self.require(r"unless the user has explicitly authorized the exact action", "Existing exact authorization is missing")

    def test_user_reported_resolution_requires_user_evidence(self):
        self.require(r"user-reported error.*until the user confirms later testing", "User-observed resolution boundary is missing")


if __name__ == "__main__":
    unittest.main()

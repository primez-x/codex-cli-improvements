import os
import re
import unittest
from pathlib import Path


class GlobalAutonomyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        cls.instructions = (codex_home / "AGENTS.md").read_text(encoding="utf-8")
        cls.normalized = " ".join(cls.instructions.lower().split())

    def test_issue_reports_authorize_end_to_end_remediation(self) -> None:
        self.assertIn(
            "reports a defect, failure, regression, undesired behavior, or broken workflow",
            self.normalized,
        )
        self.assertIn("diagnose and remediate it end-to-end", self.normalized)

    def test_diagnosis_is_read_only_only_when_explicit(self) -> None:
        self.assertIn("only treat diagnosis as read-only", self.normalized)
        for explicit_limit in (
            "research only",
            "root cause only",
            "debug only",
            "diagnosis only",
            "no code changes",
            "no code updates",
            "read-only",
            "do not change",
        ):
            self.assertIn(explicit_limit, self.normalized)
        self.assertIn(
            "conversational requests such as `diagnose`, `investigate`, `take a look`, `see what's going on`, or inspect a reported issue do not withhold authorization to fix it",
            self.normalized,
        )
        self.assertNotRegex(
            self.normalized,
            re.compile(r"treat requests to [^.]*diagnose[^.]* as read-only"),
        )

    def test_process_workflows_cannot_add_feedback_gates(self) -> None:
        self.assertIn(
            "must not add user approval, review, or feedback checkpoints",
            self.normalized,
        )
        self.assertIn("continue through implementation and verification", self.normalized)
        self.assertIn("valid in-scope review findings", self.normalized)
        self.assertIn("without renewed user approval", self.normalized)
        self.assertIn("new scope or authority", self.normalized)

    def test_leading_plan_acceptance_with_attached_body_authorizes_execution(self) -> None:
        self.assertIn("leading plan-acceptance directive", self.normalized)
        self.assertIn("attached plan", self.normalized)

    def test_autonomy_preserves_high_impact_authorization_boundaries(self) -> None:
        self.assertIn(
            "pull requests, merges, releases, and deployments remain separately authorized",
            self.normalized,
        )
        self.assertIn(
            "perform unrelated material external changes unless explicitly requested or clearly required by the named workflow",
            self.normalized,
        )
        self.assertIn(
            "keep human approval for financial, legal, regulated, destructive, or other high-impact actions unless the user has explicitly authorized the exact action",
            self.normalized,
        )


if __name__ == "__main__":
    unittest.main()

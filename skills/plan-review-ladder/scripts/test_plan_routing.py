from __future__ import annotations

from pathlib import Path
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]


class PlanRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8").lower()
        lenses = (
            SKILL_ROOT / "references" / "review-lenses.md"
        ).read_text(encoding="utf-8").lower()
        cls.skill = " ".join(skill.split())
        cls.lenses = " ".join(lenses.split())

    def test_root_and_model_effort_contract(self) -> None:
        for phrase in (
            "sol medium root",
            "`luna_coordinator`, high",
            "`terra_coordinator`, medium",
            "`sol_advisor`, max",
            "`sol_coordinator`, max",
            "`spark_scanner`, high",
            "`luna_scanner`, medium",
        ):
            self.assertIn(phrase, self.skill)

    def test_spark_is_evidence_only(self) -> None:
        self.assertNotIn("spark_coordinator", self.skill)
        self.assertNotIn("spark_worker", self.skill)
        self.assertIn("exact low-context evidence", self.skill)

    def test_adaptive_routes_are_explicit(self) -> None:
        for route in (
            "**standard**",
            "**expanded**",
            "**full**",
            "independent luna validation",
            "terra integration validation",
            "independent sol challenge",
        ):
            self.assertIn(route, self.skill)

    def test_candidate_plan_is_luna_owned(self) -> None:
        self.assertIn(
            "dispatch `luna_coordinator` with the evidence bundle",
            self.skill,
        )

    def test_plan_descendants_remain_read_only(self) -> None:
        self.assertIn("all descendants remain read-only", self.skill)
        self.assertIn(
            "depth 3 may use only terminal `spark_scanner` or `luna_scanner`",
            self.skill,
        )

    def test_review_lenses_cover_each_supervision_tier(self) -> None:
        for heading in (
            "### luna contract and completeness",
            "### terra integration and feasibility",
            "### sol adversarial risk",
            "## root residual-risk lens",
        ):
            self.assertIn(heading, self.lenses)

    def test_material_review_depth_means_coverage_not_agent_tree_depth(self) -> None:
        combined = self.skill + " " + self.lenses
        self.assertIn("coverage score `2`", combined)
        self.assertNotIn("primary reviewer at depth 2", combined)
        self.assertNotIn("responsible for a depth-2 review", combined)
        self.assertNotIn("category below depth 2", combined)

    def test_planned_artifacts_are_not_treated_as_missing_implementation(self) -> None:
        for phrase in (
            "existing authority",
            "planned new artifact",
            "implemented artifact",
            "absence before implementation is expected",
            "not a finding by itself",
        ):
            self.assertIn(phrase, self.skill + " " + self.lenses)

    def test_frozen_review_packet_has_identity_and_stage_budget(self) -> None:
        for phrase in (
            "`packet_id`",
            "`packet_sha256`",
            "`deadline_minutes`",
            "steer once",
            "do not automatically restart",
        ):
            self.assertIn(phrase, self.skill + " " + self.lenses)

    def test_timeout_caps_confidence_and_can_block_signoff(self) -> None:
        for phrase in (
            "`timed_out`",
            "confidence limit",
            "uniquely owns a critical category",
            "sign-off is blocked",
        ):
            self.assertIn(phrase, self.skill + " " + self.lenses)

    def test_stage_telemetry_is_evidence_bounded(self) -> None:
        for phrase in (
            "elapsed time",
            "child count",
            "token usage",
            "authoritative telemetry",
            "`unavailable`",
        ):
            self.assertIn(phrase, self.skill + " " + self.lenses)

    def test_packet_integrity_and_finite_stage_budgets_are_explicit(self) -> None:
        combined = self.skill + " " + self.lenses
        for phrase in (
            "canonical bytes",
            "observed_packet_sha256",
            "grace_minutes",
            "1..45",
            "1..5",
            "reviewer_profile",
            "terminal profiles",
            "sol_coordinator",
            "1..2",
            "frozen packet",
        ):
            self.assertIn(phrase, combined)
        self.assertNotIn("descendant_budget in `0..2`", combined)

    def test_full_route_requires_returning_sol_and_is_not_partial_full(self) -> None:
        combined = self.skill + " " + self.lenses
        self.assertIn("full is not complete without a required sol return", combined)
        self.assertIn("partial route", combined)
        self.assertIn("may not be labeled a partial full", combined)


if __name__ == "__main__":
    unittest.main()

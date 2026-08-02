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
        cls.combined = cls.skill + " " + cls.lenses

    def test_root_and_supported_profile_effort_contract(self) -> None:
        for phrase in (
            "sol medium root",
            "`spark_scanner`, xhigh",
            "`spark_worker`, xhigh",
            "`luna_scanner`, medium",
            "`luna_worker`, max",
            "`sol_worker`, xhigh",
            "`sol_advisor`, max",
        ):
            self.assertIn(phrase, self.skill)

        for retired in ("terra", "coordinator", "sol_coordinator"):
            self.assertNotIn(retired, self.combined)

    def test_spark_is_bounded_evidence_only(self) -> None:
        self.assertIn("spark_scanner", self.skill)
        self.assertIn("exact low-context evidence", self.skill)
        self.assertRegex(self.combined, r"fork_turns\s*=\s*[`\"]none[`\"]")
        for phrase in ("self-contained", "bounded", "anchor"):
            self.assertIn(phrase, self.combined)
        self.assertIn(
            "plan review dispatches only the read-only `spark_scanner`, "
            "`luna_scanner`, and `sol_advisor` profiles",
            self.skill,
        )
        self.assertIn("do not send broad discovery or synthesis to spark", self.skill)

    def test_routine_low_risk_review_routes_root_and_luna_scanner(self) -> None:
        for phrase in ("root", "luna_scanner", "routine", "low-risk"):
            self.assertIn(phrase, self.skill)
        self.assertIn("dispatch `luna_scanner`", self.skill)

    def test_sol_advisor_is_risk_triggered_and_optional_for_low_risk(self) -> None:
        for phrase in (
            "sol_advisor",
            "risk-triggered",
            "early",
            "final",
            "not mandatory",
        ):
            self.assertIn(phrase, self.skill)
        self.assertRegex(
            self.skill,
            r"low-risk[^.]*not mandatory|not mandatory[^.]*low-risk",
        )

    def test_plan_descendants_are_read_only_and_cannot_spawn(self) -> None:
        self.assertIn("all descendants remain read-only", self.skill)
        self.assertIn("depth 1", self.skill)
        self.assertNotIn("depth 2", self.skill)
        self.assertNotIn("depth 3", self.skill)
        self.assertIn("do not spawn", self.skill)

    def test_review_lenses_cover_luna_and_root_with_risk_advisor(self) -> None:
        for heading in (
            "### luna contract and completeness",
            "### sol adversarial risk",
            "## root residual-risk lens",
        ):
            self.assertIn(heading, self.lenses)
        self.assertNotIn("terra", self.lenses)
        self.assertNotIn("coordinator", self.lenses)

    def test_gate_only_sol_reviewer_is_rejected_for_plan_review(self) -> None:
        self.assertIn("sol_reviewer", self.combined)
        self.assertIn("not a plan-review route", self.combined)
        self.assertIn("packet validation must reject", self.combined)

    def test_planned_artifacts_are_not_treated_as_missing_implementation(self) -> None:
        for phrase in (
            "existing authority",
            "planned new artifact",
            "implemented artifact",
            "absence before implementation is expected",
            "not a finding by itself",
        ):
            self.assertIn(phrase, self.combined)

    def test_frozen_review_packet_has_identity_and_stage_budget(self) -> None:
        for phrase in (
            "`packet_id`",
            "`packet_sha256`",
            "`deadline_minutes`",
            "steer once",
            "do not automatically restart",
        ):
            self.assertIn(phrase, self.combined)

    def test_timeout_caps_confidence_and_can_block_signoff(self) -> None:
        for phrase in (
            "`timed_out`",
            "confidence limit",
            "uniquely owns a critical category",
            "sign-off is blocked",
        ):
            self.assertIn(phrase, self.combined)

    def test_stage_telemetry_is_evidence_bounded(self) -> None:
        for phrase in (
            "elapsed time",
            "child count",
            "token usage",
            "authoritative telemetry",
            "`unavailable`",
        ):
            self.assertIn(phrase, self.combined)

    def test_packet_integrity_and_zero_stage_budgets_are_explicit(self) -> None:
        for phrase in (
            "canonical bytes",
            "observed_packet_sha256",
            "grace_minutes",
            "1..45",
            "1..5",
            "reviewer_profile",
            "terminal profiles",
            "descendant_budget",
            "exactly `0`",
            "frozen packet",
        ):
            self.assertIn(phrase, self.combined)


if __name__ == "__main__":
    unittest.main()

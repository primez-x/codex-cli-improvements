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
            "astra low root",
            "configured routing matrix",
            "`spark_scanner`, xhigh",
            "`spark_worker`, xhigh",
            "`luna_scanner`, medium",
            "`luna_worker`, max",
            "`sol_fast_worker` (sol low)",
            "`astra_worker` (astra medium)",
            "`astra_advisor` (astra high)",
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
            "`luna_scanner`, and `astra_advisor` profiles",
            self.skill,
        )
        self.assertIn("do not send broad discovery or synthesis to spark", self.skill)

    def test_routine_low_risk_review_routes_root_and_luna_scanner(self) -> None:
        for phrase in ("root", "luna_scanner", "routine", "low-risk", "bounded"):
            self.assertIn(phrase, self.skill)
        self.assertIn("may produce the candidate directly", self.skill)

    def test_sol_advisor_is_risk_triggered_and_optional_for_low_risk(self) -> None:
        for phrase in (
            "astra_advisor",
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
            "### astra high adversarial risk",
            "## root residual-risk lens",
        ):
            self.assertIn(heading, self.lenses)
        self.assertNotIn("terra", self.lenses)
        self.assertNotIn("coordinator", self.lenses)

    def test_gate_only_sol_reviewer_is_rejected_for_plan_review(self) -> None:
        self.assertIn("astra_reviewer", self.combined)
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

    def test_auditable_replay_packet_has_identity_and_stage_budget(self) -> None:
        for phrase in (
            "`packet_id`",
            "`packet_sha256`",
            "`deadline_minutes`",
            "steer once",
            "do not automatically restart",
            "explicit auditable replay/evaluation mode",
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

    def test_reusable_instruction_system_review_preserves_authority_trace(self) -> None:
        for phrase in (
            "reusable instruction",
            "instruction-learning-loop",
            "concrete smallest proposal",
            "canonical-to-installed/runtime authority trace",
            "installer",
            "registration",
            "manifest",
            "drift evidence or explicit n/a",
            "immutable envelope",
            "final instruction-system plan",
            "material authority or implementation change",
            "refresh the selected astra high advisor review before sign-off",
            "already authorized",
            "never creates renewed user approval",
        ):
            self.assertIn(phrase, self.combined)
        self.assertIn("surface type alone does not force an advisor stage", self.skill)

    def test_routine_route_does_not_force_fresh_luna_or_replay_ceremony(self) -> None:
        self.assertIn("may remain root-direct", self.skill)
        self.assertNotIn("always dispatch a fresh `luna_scanner`", self.skill)
        self.assertNotIn("every packet freezes integer", self.skill)
        self.assertIn("ordinary planning", self.combined)
        self.assertNotIn("on timeout, steer once", self.combined)
        self.assertIn("in replay/evaluation mode, steer once", self.combined)


if __name__ == "__main__":
    unittest.main()

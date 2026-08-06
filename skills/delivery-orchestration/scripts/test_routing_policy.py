from __future__ import annotations

import os
from pathlib import Path
import tomllib
import unittest


CODEX_HOME = Path(
    os.environ.get("CODEX_ROUTING_HOME", Path.home() / ".codex")
).resolve()


def load_toml(path: Path) -> dict:
    with path.open("rb") as stream:
        return tomllib.load(stream)


GENERAL_ROUTING_MATRIX = {
    "spark_scanner": ("gpt-5.3-codex-spark", "xhigh"),
    "spark_worker": ("gpt-5.3-codex-spark", "xhigh"),
    "luna_scanner": ("gpt-5.6-luna", "low"),
    "luna_worker": ("gpt-5.6-luna", "medium"),
    "luna_orchestrator": ("gpt-5.6-luna", "max"),
    "sol_worker": ("gpt-5.6-sol", "high"),
    "sol_advisor": ("gpt-5.6-sol", "high"),
}
REVIEWER_PROFILE_NAME = "sol_reviewer"
REVIEWER_PROFILE = ("gpt-5.6-sol", "max")


class RoutingPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config_path = CODEX_HOME / "config.toml"
        cls.config = load_toml(cls.config_path)
        cls.agents = cls.config["agents"]

    def load_agent(self, name: str) -> dict:
        relative_path = self.agents[name]["config_file"]
        return load_toml((self.config_path.parent / relative_path).resolve())

    def test_root_and_untyped_subagent_defaults(self) -> None:
        self.assertEqual(self.config["model"], "gpt-5.6-luna")
        self.assertEqual(self.config["model_reasoning_effort"], "max")
        self.assertEqual(
            self.agents["default_subagent_model"], "gpt-5.6-luna"
        )
        self.assertEqual(
            self.agents["default_subagent_reasoning_effort"], "medium"
        )
        self.assertEqual(self.agents["max_depth"], 3)
        self.assertEqual(
            self.agents["max_concurrent_threads_per_session"], 64
        )

    def test_registered_model_effort_contract(self) -> None:
        self.assertNotIn(REVIEWER_PROFILE_NAME, GENERAL_ROUTING_MATRIX)
        registered = {
            name
            for name, value in self.agents.items()
            if isinstance(value, dict) and "config_file" in value
        }
        self.assertEqual(
            registered,
            set(GENERAL_ROUTING_MATRIX) | {REVIEWER_PROFILE_NAME},
        )
        self.assertEqual(
            self.agents[REVIEWER_PROFILE_NAME]["description"],
            "On-demand read-only Sol reviewer for root-prepared consequential delivery evidence packets.",
        )
        self.assertFalse(
            any("terra" in name or "coordinator" in name for name in registered)
        )
        self.assertIn("high", self.agents["sol_advisor"]["description"].lower())
        self.assertNotIn("max-effort", self.agents["sol_advisor"]["description"].lower())

        profile_files = {
            path.stem for path in (self.config_path.parent / "agents").glob("*.toml")
        }
        self.assertEqual(
            profile_files,
            set(GENERAL_ROUTING_MATRIX) | {REVIEWER_PROFILE_NAME},
        )

        for name, (model, effort) in GENERAL_ROUTING_MATRIX.items():
            with self.subTest(agent=name):
                agent = self.load_agent(name)
                self.assertEqual(agent["model"], model)
                self.assertEqual(agent["model_reasoning_effort"], effort)

    def test_every_profile_is_a_terminal_leaf(self) -> None:
        for name in ("spark_scanner", "spark_worker", "luna_scanner", "sol_worker", "sol_advisor"):
            with self.subTest(agent=name):
                instructions = self.load_agent(name)["developer_instructions"].lower()
                self.assertRegex(instructions, r"do not[^.\n]*spawn")

    def test_registered_profile_set_is_exact(self) -> None:
        expected = set(GENERAL_ROUTING_MATRIX) | {REVIEWER_PROFILE_NAME}
        registered = {
            name for name, value in self.agents.items()
            if isinstance(value, dict) and "config_file" in value
        }
        self.assertEqual(registered, expected)

    def test_canonical_topology_has_exact_depth_and_adjacency_contract(self) -> None:
        topology = (self.config_path.parent / "skills" / "delivery-orchestration" / "references" / "delegation-topology.md").read_text(encoding="utf-8").lower()
        self.assertIn("canonical exact adjacency/depth matrix", topology)
        self.assertIn("root creates d1 only", topology)
        self.assertIn("orchestrator", topology)
        self.assertIn("luna worker", topology)
        self.assertIn("d3", topology)
        self.assertIn("scanner-only", topology)
        self.assertIn("direct-parent", topology)
        # Sol identities are always root-routed terminal d1 leaves; they must
        # never occur in a non-root "may create" adjacency cell.
        for profile in ("sol worker", "sol advisor", "sol reviewer"):
            self.assertRegex(
                topology,
                rf"{profile}[^\n]*(?:root-routed|root only)[^\n]*d1[^\n]*terminal",
            )
            for line in topology.splitlines():
                if profile in line and "may create" in line:
                    self.fail(f"{profile} appears in a non-root may-create cell: {line}")

        # The canonical table is the sole source for these complete adjacency
        # rows. Each row names the allowed children and their next depth.
        for row in (
            "luna orchestrator | d1 | luna worker, luna scanner, spark worker, spark scanner | d2",
            "luna worker | d1 | spark worker, spark scanner, luna scanner | d2",
            "luna worker | d2 | spark scanner, luna scanner | d3",
        ):
            self.assertIn(row, topology)
        self.assertIn("all scanners | d1-d3 | terminal", topology)
        self.assertIn("spark worker | d1-d2 | terminal", topology)
        self.assertIn("d3 | scanner-only", topology)

    def test_on_demand_reviewer_profile_is_read_only_and_evidence_bound(self) -> None:
        reviewer = self.load_agent(REVIEWER_PROFILE_NAME)
        self.assertEqual(reviewer["name"], REVIEWER_PROFILE_NAME)
        self.assertEqual(
            (reviewer["model"], reviewer["model_reasoning_effort"]),
            REVIEWER_PROFILE,
        )
        self.assertEqual(reviewer["sandbox_mode"], "read-only")
        instructions = reviewer["developer_instructions"].lower()
        for phrase in (
            "operate only at depth 1",
            "do not spawn",
            "do not emit a receipt",
            "root-prepared evidence packet",
            "evidence anchors",
            "verdict",
        ):
            self.assertIn(phrase, instructions)
        self.assertRegex(instructions, r"do not[^.\n]*(?:edit|mutate)")

    def test_spark_packets_are_self_contained_bounded_and_not_broad(self) -> None:
        skill_root = self.config_path.parent / "skills" / "delivery-orchestration"
        topology = (skill_root / "references" / "delegation-topology.md").read_text(
            encoding="utf-8"
        ).lower()
        for name in ("spark_scanner", "spark_worker"):
            with self.subTest(agent=name):
                instructions = self.load_agent(name)["developer_instructions"].lower()
                self.assertIn("localized", instructions)
                self.assertIn("do not perform broad discovery", instructions)
                self.assertIn("do not perform synthesis", instructions)

        self.assertRegex(topology, r"fork_turns\s*=\s*[\"']none")
        self.assertIn("self-contained", topology)
        self.assertIn("bounded", topology)
        self.assertIn("anchor", topology)
        self.assertIn("128k", topology)
        self.assertIn("272k", topology)

    def test_luna_roles_cover_broad_discovery_and_default_implementation(self) -> None:
        scanner = self.load_agent("luna_scanner")["developer_instructions"].lower()
        for phrase in ("broad", "context-heavy", "read-only", "discovery"):
            self.assertIn(phrase, scanner)

        worker = self.load_agent("luna_worker")["developer_instructions"].lower()
        for phrase in ("default", "implementation", "read-write"):
            self.assertIn(phrase, worker)

    def test_luna_worker_d2_child_dispatch_is_explicit(self) -> None:
        worker = self.load_agent("luna_worker")["developer_instructions"].lower()
        self.assertIn(
            "only legal depth-3 children are exact `spark_scanner` and `luna_scanner`",
            worker,
        )
        self.assertIn("dispatch these only when they are assigned", worker)
        self.assertIn(
            "do not create any writer (`spark_worker` or `luna_worker`), `luna_orchestrator`, or any `sol_*` profile at depth 3",
            worker,
        )
        self.assertIn('fork_turns = "none"', worker)
        self.assertIn("fresh self-contained bounded packet with explicit anchors", worker)
        topology = (
            self.config_path.parent
            / "skills"
            / "delivery-orchestration"
            / "references"
            / "delegation-topology.md"
        ).read_text(encoding="utf-8").lower()
        self.assertIn("luna worker | d2 | spark scanner, luna scanner | d3", topology)
        self.assertIn("all scanners | d1-d3 | terminal", topology)

    def test_sol_roles_are_rare_and_terminal(self) -> None:
        worker = self.load_agent("sol_worker")["developer_instructions"].lower()
        for phrase in ("difficult", "implementation"):
            self.assertIn(phrase, worker)

        advisor = self.load_agent("sol_advisor")["developer_instructions"].lower()
        for phrase in ("consequential", "adversarial", "review"):
            self.assertIn(phrase, advisor)

    def test_delivery_skill_declares_the_routing_invariants(self) -> None:
        skill_root = self.config_path.parent / "skills" / "delivery-orchestration"
        skill = (skill_root / "SKILL.md").read_text(encoding="utf-8").lower()
        topology = (
            skill_root / "references" / "delegation-topology.md"
        ).read_text(encoding="utf-8").lower()
        flat_skill = " ".join(skill.split())
        flat_topology = " ".join(topology.split())

        for phrase in (
            "luna max root",
            "direct root path",
            "delegation overhead",
            "spark fast path",
            "luna is the default",
            "escalate the model",
            "root-routed independent review",
            "high-risk trigger",
            "privacy",
            "public-contract",
            "repeated failed verification",
            "reversible startup-setting changes",
            "optional review infrastructure fails",
            "only a required high-risk review failure blocks delivery",
        ):
            self.assertIn(phrase, flat_skill)
        self.assertRegex(flat_skill, r"root (?:directly )?coordinate")

        for row in (
            "| spark scanner | xhigh |",
            "| spark worker | xhigh |",
            "| luna scanner | low |",
            "| luna worker | medium |",
            "| luna orchestrator | max |",
            "| sol worker | high |",
            "| sol advisor | high |",
        ):
            self.assertIn(row, flat_topology)

        self.assertIn("depth 1", flat_topology)
        self.assertIn("depth 2", flat_topology)
        self.assertIn("depth 3", flat_topology)
        for stale in ("terra", "coordinator", "sol_coordinator"):
            self.assertNotIn(stale, flat_skill + " " + flat_topology)

    def test_delivery_skill_does_not_duplicate_stale_hierarchy_or_effort_policy(self) -> None:
        skill_root = self.config_path.parent / "skills" / "delivery-orchestration"
        skill = " ".join((skill_root / "SKILL.md").read_text(encoding="utf-8").lower().split())
        topology = " ".join((skill_root / "references" / "delegation-topology.md").read_text(encoding="utf-8").lower().split())
        for stale in (
            "configured sol low root",
            "terminal depth-1 leaves",
            "one to three active leaves",
            "configured ceiling of four",
            "max_concurrent_threads_per_session = 4",
            "every leaf reports directly to the root",
            "explicit zero descendant budget",
            "luna scanner`, medium",
            "luna worker`, max",
            "sol worker`, xhigh",
            "sol advisor`, max",
        ):
            self.assertNotIn(stale, skill)
        self.assertNotIn("model and effort matrix", skill)
        self.assertIn("canonical exact adjacency/depth matrix", topology)

    def test_coordination_contracts_and_recovery_are_explicit(self) -> None:
        skill_root = self.config_path.parent / "skills" / "delivery-orchestration"
        source = " ".join(
            (
                (skill_root / "SKILL.md").read_text(encoding="utf-8"),
                (skill_root / "references" / "delegation-topology.md").read_text(encoding="utf-8"),
            )
        ).lower()
        for contract, fields in {
            "work_assignment_v1": (
                "assignment id", "root-session", "owner", "direct return",
                "owned_paths", "owned resources", "permitted actions", "expected outcome", "checks",
            ),
            "work_return_v1": (
                "matching assignment id", "status", "changed paths", "changed resources",
                "checks", "background activity", "remaining risks",
            ),
            "advisor_request_v1": (
                "requester id", "decision", "risk", "options", "frozen evidence digest",
                "ownership", "child status", "requested response",
            ),
        }.items():
            self.assertIn(contract, source)
            for field in fields:
                self.assertIn(field, source)
        for phrase in (
            "reject old-session returns",
            "blocks overlapping writers",
            "workspace/shared-resource/task-owned-background-process audit",
            "unclear state unassigned",
            "same-agent resume",
            "explicit rehydration fallback",
            "elapsed time never kills healthy work",
            "query quiet agents",
            "interrupt only idle, unresponsive, or demonstrably stuck",
            "reconcile before reclaim",
        ):
            self.assertIn(phrase, source)

    def test_direct_root_path_is_bounded_and_gates_external_effects(self) -> None:
        skill = (
            CODEX_HOME / "skills" / "delivery-orchestration" / "SKILL.md"
        ).read_text(encoding="utf-8").lower()
        normalized = " ".join(skill.split())

        for phrase in (
            "one concern",
            "no discovery",
            "no conflicting authority",
            "external mutation is explicitly authorized",
            "exact target",
            "low-impact",
            "no unapproved or consequential external side effect",
            "one focused verification",
            "lossless rollback",
            "reclassify immediately",
        ):
            self.assertIn(phrase, normalized)

    def test_root_owned_advisor_checkpoint_contract(self) -> None:
        agents = (CODEX_HOME / "AGENTS.md").read_text(encoding="utf-8").lower()
        skill = (
            CODEX_HOME / "skills" / "delivery-orchestration" / "SKILL.md"
        ).read_text(encoding="utf-8").lower()
        advisor = self.load_agent("sol_advisor")["developer_instructions"].lower()
        combined = " ".join((agents + " " + skill + " " + advisor).split())

        for phrase in (
            "only the depth-0 root dispatches `sol_advisor`",
            "risk-triggered",
            "sibling handoff",
            "root owns disposition",
            "same-agent resume",
            "explicit rehydration fallback",
            "localized, low-risk",
            "user approval gate",
        ):
            self.assertIn(phrase, combined)

        for phrase in (
            "reconsult checkpoint",
            "final-plan checkpoint",
            "final-delivery checkpoint",
            "do not require implementation artifacts or executed tests",
            "actual applicable test, build, and runtime evidence",
        ):
            self.assertIn(phrase, advisor)
        self.assertRegex(advisor, r"do not[^.\n]*spawn")
        self.assertEqual(self.load_agent("sol_advisor")["sandbox_mode"], "read-only")

    def test_sol_advisor_returns_evidence_and_findings_without_self_disposition(self) -> None:
        advisor = self.load_agent("sol_advisor")["developer_instructions"].lower()
        self.assertIn("return findings and evidence only", advisor)
        self.assertIn("do not disposition", advisor)
        self.assertNotIn("accepted, rejected, or deferred", advisor)

    def test_delivery_skill_declares_root_dispositions_for_advisor_findings(self) -> None:
        skill = (
            CODEX_HOME / "skills" / "delivery-orchestration" / "SKILL.md"
        ).read_text(encoding="utf-8").lower()
        normalized_skill = " ".join(skill.split())
        self.assertIn("when an advisor packet is received, the root is the only party that dispositions each advisor finding as accepted, rejected, or deferred", normalized_skill)
        self.assertIn("primary evidence", normalized_skill)

    def test_git_backed_delivery_commits_and_pushes_safely_by_default(self) -> None:
        agents = (CODEX_HOME / "AGENTS.md").read_text(encoding="utf-8").lower()
        skill = (
            CODEX_HOME / "skills" / "delivery-orchestration" / "SKILL.md"
        ).read_text(encoding="utf-8").lower()
        combined = " ".join((agents + " " + skill).split())

        for phrase in (
            "standing terminal condition",
            "authorized implementation or remediation that changes a git repository",
            "existing task-aligned feature branch",
            "default, detached, mismatched, or unsafe branch",
            "`agent/<task-slug>`",
            "never force-push",
            "never push directly to the default branch",
            "ahead-of-upstream history",
            "explicit paths or hunks",
            "isolated worktree or clone",
            "local task-only commit",
            "remote-ref verification",
            "remote head must equal the local sha",
            "task commit must be an ancestor",
            "do not commit",
            "leave uncommitted",
            "no push",
            "commit only",
            "keep local",
            "pull requests, merges, releases, and deployments remain separately authorized",
            "subagents never commit, push",
        ):
            self.assertIn(phrase, combined)

        for blocker in (
            "authentication",
            "branch protection",
            "hooks",
            "non-fast-forward",
        ):
            self.assertIn(blocker, combined)

        self.assertNotRegex(
            combined,
            r"commit, push[^.]*only when explicitly authorized",
        )


if __name__ == "__main__":
    unittest.main()

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
        self.assertEqual(self.config["model"], "gpt-5.6-sol")
        self.assertEqual(self.config["model_reasoning_effort"], "medium")
        self.assertEqual(
            self.agents["default_subagent_model"], "gpt-5.6-luna"
        )
        self.assertEqual(
            self.agents["default_subagent_reasoning_effort"], "max"
        )
        self.assertEqual(self.agents["max_depth"], 1)
        self.assertEqual(
            self.agents["max_concurrent_threads_per_session"], 4
        )

    def test_registered_model_effort_contract(self) -> None:
        expected = {
            "spark_scanner": ("gpt-5.3-codex-spark", "xhigh"),
            "spark_worker": ("gpt-5.3-codex-spark", "xhigh"),
            "luna_scanner": ("gpt-5.6-luna", "medium"),
            "luna_worker": ("gpt-5.6-luna", "max"),
            "sol_worker": ("gpt-5.6-sol", "xhigh"),
            "sol_advisor": ("gpt-5.6-sol", "max"),
        }

        registered = {
            name
            for name, value in self.agents.items()
            if isinstance(value, dict) and "config_file" in value
        }
        self.assertEqual(registered, set(expected))
        self.assertFalse(
            any("terra" in name or "coordinator" in name for name in registered)
        )

        profile_files = {
            path.stem for path in (self.config_path.parent / "agents").glob("*.toml")
        }
        self.assertEqual(profile_files, set(expected))

        for name, (model, effort) in expected.items():
            with self.subTest(agent=name):
                agent = self.load_agent(name)
                self.assertEqual(agent["model"], model)
                self.assertEqual(agent["model_reasoning_effort"], effort)

    def test_every_profile_is_a_terminal_leaf(self) -> None:
        for name in (
            "spark_scanner",
            "spark_worker",
            "luna_scanner",
            "luna_worker",
            "sol_worker",
            "sol_advisor",
        ):
            with self.subTest(agent=name):
                instructions = self.load_agent(name)["developer_instructions"].lower()
                self.assertRegex(instructions, r"do not[^.\n]*spawn")

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
            "sol medium root",
            "spark fast path",
            "luna is the default",
            "escalate the model",
        ):
            self.assertIn(phrase, flat_skill)
        self.assertRegex(flat_skill, r"root (?:directly )?coordinate")

        for row in (
            "| spark scanner | xhigh |",
            "| spark worker | xhigh |",
            "| luna scanner | medium |",
            "| luna worker | max |",
            "| sol worker | xhigh |",
            "| sol advisor | max |",
        ):
            self.assertIn(row, flat_topology)

        self.assertIn("depth 1", flat_topology)
        self.assertNotIn("depth 2", flat_topology)
        self.assertNotIn("depth 3", flat_topology)
        for stale in ("terra", "coordinator", "sol_coordinator"):
            self.assertNotIn(stale, flat_skill + " " + flat_topology)

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
            "four or more substantive stages",
            "localized low-risk work",
            "accepted, rejected, or deferred",
            "user approval gate",
        ):
            self.assertIn(phrase, combined)

        for phrase in (
            "early checkpoint",
            "reconsult checkpoint",
            "final-plan checkpoint",
            "final-delivery checkpoint",
            "do not require implementation artifacts or executed tests",
            "actual applicable test, build, and runtime evidence",
        ):
            self.assertIn(phrase, advisor)
        self.assertRegex(advisor, r"do not[^.\n]*spawn")
        self.assertEqual(self.load_agent("sol_advisor")["sandbox_mode"], "read-only")

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
